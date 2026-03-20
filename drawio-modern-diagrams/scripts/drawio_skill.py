#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from drawio_xml import repair_drawio_file


def skill_root() -> Path:
    return Path(__file__).resolve().parents[1]


def load_config() -> dict[str, Any]:
    config_path = skill_root() / "config.json"
    return json.loads(config_path.read_text(encoding="utf-8"))


def resolve_path(relative_path: str) -> Path:
    return skill_root() / relative_path


def normalize_out_dir(out_dir: str | None, config: dict[str, Any]) -> Path:
    if out_dir:
        return Path(out_dir).expanduser().resolve()
    return (skill_root() / config["paths"]["outputs_dir"]).resolve()


def get_profiles(config: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return config.get("styles", {}).get("profiles", {})


def unique_strings(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        if not value or value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def validate_input_path(input_path: Path) -> Path:
    resolved = input_path.expanduser().resolve()
    if not resolved.exists():
        raise SystemExit(f"Input file not found: {resolved}")
    return resolved


def prepare_input_path(input_path: Path) -> tuple[Path, dict[str, Any]]:
    resolved = validate_input_path(input_path)
    try:
        sanitization = repair_drawio_file(resolved)
    except ValueError as exc:
        raise SystemExit(f"Invalid draw.io file: {exc}") from exc
    return resolved, sanitization


def parse_formats(raw_formats: str | None, config: dict[str, Any]) -> list[str]:
    formats = [item.strip().lower() for item in (raw_formats or "").split(",") if item.strip()]
    if not formats:
        formats = list(config["exports"]["default_formats"])

    known_formats = set(config["exports"]["command_templates"])
    unknown_formats = [fmt for fmt in formats if fmt not in known_formats]
    if unknown_formats:
        allowed = ", ".join(sorted(known_formats))
        invalid = ", ".join(unknown_formats)
        raise SystemExit(f"Unknown export formats: {invalid}. Allowed formats: {allowed}")

    return list(dict.fromkeys(formats))


def ensure_inspect_format(formats: list[str], config: dict[str, Any]) -> tuple[list[str], list[str]]:
    required_review = bool(config["quality"].get("require_png_review", True))
    inspect_format = config["exports"]["inspect_format"]
    if not required_review or inspect_format in formats:
        return formats, []
    return formats + [inspect_format], [inspect_format]


def detect_host_platform() -> str:
    if sys.platform.startswith("win"):
        return "windows"
    if sys.platform == "darwin":
        return "macos"
    if sys.platform.startswith("linux"):
        return "linux"
    return sys.platform


def get_windows_drawio_path_templates(config: dict[str, Any]) -> list[str]:
    runtime = config.get("runtime", {})
    configured = runtime.get("windows_drawio_path_templates")
    if configured:
        return list(configured)
    return [
        r"%ProgramW6432%\draw.io\draw.io.exe",
        r"%ProgramW6432%\draw.io\Draw.io.exe",
        r"%ProgramW6432%\diagrams.net\draw.io.exe",
        r"%ProgramW6432%\diagrams.net\diagrams.net.exe",
        r"%ProgramFiles%\draw.io\draw.io.exe",
        r"%ProgramFiles%\draw.io\Draw.io.exe",
        r"%ProgramFiles%\diagrams.net\draw.io.exe",
        r"%ProgramFiles%\diagrams.net\diagrams.net.exe",
        r"%ProgramFiles(x86)%\draw.io\draw.io.exe",
        r"%ProgramFiles(x86)%\Draw.io\Draw.io.exe",
        r"%ProgramFiles(x86)%\diagrams.net\draw.io.exe",
        r"%ProgramFiles(x86)%\diagrams.net\diagrams.net.exe",
        r"%LocalAppData%\Programs\draw.io\draw.io.exe",
        r"%LocalAppData%\Programs\Draw.io\Draw.io.exe",
        r"%LocalAppData%\Programs\diagrams.net\draw.io.exe",
        r"%LocalAppData%\Programs\diagrams.net\diagrams.net.exe",
        r"%LocalAppData%\draw.io\draw.io.exe",
        r"%LocalAppData%\diagrams.net\diagrams.net.exe",
    ]


def expand_windows_drawio_path_templates(config: dict[str, Any]) -> list[str]:
    variables = ("ProgramW6432", "ProgramFiles", "ProgramFiles(x86)", "LocalAppData")
    candidates: list[str] = []

    for template in get_windows_drawio_path_templates(config):
        expanded = template
        unresolved = False
        for variable in variables:
            placeholder = f"%{variable}%"
            if placeholder not in expanded:
                continue
            value = os.environ.get(variable)
            if not value:
                unresolved = True
                break
            expanded = expanded.replace(placeholder, value)
        if unresolved or "%" in expanded:
            continue
        candidates.append(expanded)

    return unique_strings(candidates)


def get_drawio_candidates(config: dict[str, Any], target_platform: str | None = None) -> list[str]:
    platform_name = target_platform or detect_host_platform()
    runtime = config.get("runtime", {})
    configured = runtime.get("drawio_bin")
    candidates: list[str] = []

    if platform_name == "windows":
        if configured and not configured.startswith("/"):
            candidates.append(configured)
        candidates.extend(expand_windows_drawio_path_templates(config))
        candidates.extend(runtime.get("drawio_candidates", []))
        candidates.extend(
            [
                "drawio.exe",
                "draw.io.exe",
                "diagrams.net.exe",
                "drawio",
                "diagrams.net",
            ]
        )
    else:
        if configured:
            candidates.append(configured)
        candidates.extend(runtime.get("drawio_candidates", []))
        candidates.extend(
            [
                "drawio",
                "draw.io",
                "diagrams.net",
                "diagramsnet",
            ]
        )

    return unique_strings(candidates)


def resolve_drawio_candidate(candidate: str) -> str | None:
    expanded = Path(candidate).expanduser()
    if expanded.is_file() and os.access(expanded, os.X_OK):
        return str(expanded)

    resolved = shutil.which(candidate)
    if resolved:
        return resolved
    return None


def normalize_command_shell(shell: str | None, host_platform: str) -> str:
    if shell and shell != "auto":
        return shell
    if host_platform == "windows":
        return "powershell"
    return "posix"


def infer_target_platform(host_platform: str, command_shell: str) -> str:
    if command_shell in {"powershell", "cmd"}:
        return "windows"
    return host_platform


def is_windows_style_command(command: str) -> bool:
    if len(command) >= 2 and command[1] == ":":
        return True
    return "\\" in command or command.lower().endswith(".exe")


def quote_for_powershell(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def render_command_for_shell(parts: list[str], command_shell: str) -> str:
    if command_shell == "cmd":
        return subprocess.list2cmdline(parts)
    if command_shell == "powershell":
        executable, *arguments = parts
        rendered_args = " ".join(quote_for_powershell(part) for part in arguments)
        rendered_executable = quote_for_powershell(executable)
        if rendered_args:
            return f"& {rendered_executable} {rendered_args}"
        return f"& {rendered_executable}"
    return " ".join(shlex.quote(part) for part in parts)


def build_drawio_probe_result(
    *,
    requested: str | None,
    resolved: str | None,
    found: bool,
    runnable: bool,
    returncode: int | None,
    stdout: str = "",
    stderr: str = "",
    reason: str = "",
) -> dict[str, Any]:
    return {
        "requested": requested,
        "resolved": resolved,
        "found": found,
        "runnable": runnable,
        "returncode": returncode,
        "stdout": stdout,
        "stderr": stderr,
        "reason": reason,
        "platform": sys.platform,
    }


def probe_drawio_command(config: dict[str, Any], requested: str, resolved: str) -> dict[str, Any]:
    runtime = config.get("runtime", {})
    probe_args = runtime.get("drawio_probe_args", ["--help"])
    probe_timeout = float(runtime.get("drawio_probe_timeout_sec", 15))

    try:
        proc = subprocess.run(
            [resolved, *probe_args],
            check=False,
            capture_output=True,
            text=True,
            timeout=probe_timeout,
        )
    except subprocess.TimeoutExpired as exc:
        return build_drawio_probe_result(
            requested=requested,
            resolved=resolved,
            found=True,
            runnable=False,
            returncode=None,
            stdout=(exc.stdout or "").strip(),
            stderr=(exc.stderr or "").strip(),
            reason=f"draw.io probe timed out after {probe_timeout:.0f}s",
        )
    except OSError as exc:
        return build_drawio_probe_result(
            requested=requested,
            resolved=resolved,
            found=True,
            runnable=False,
            returncode=None,
            reason=f"draw.io probe failed: {exc}",
        )

    stdout = proc.stdout.strip()
    stderr = proc.stderr.strip()
    if proc.returncode == 0:
        return build_drawio_probe_result(
            requested=requested,
            resolved=resolved,
            found=True,
            runnable=True,
            returncode=proc.returncode,
            stdout=stdout,
            stderr=stderr,
            reason="draw.io CLI is runnable in the current environment.",
        )

    if sys.platform == "darwin" and proc.returncode == -6:
        reason = (
            "draw.io CLI was found, but the macOS wrapper aborts when launched from Python "
            "in the current environment."
        )
    elif stderr:
        reason = stderr
    elif stdout:
        reason = stdout
    else:
        reason = f"draw.io probe exited with code {proc.returncode}"

    return build_drawio_probe_result(
        requested=requested,
        resolved=resolved,
        found=True,
        runnable=False,
        returncode=proc.returncode,
        stdout=stdout,
        stderr=stderr,
        reason=reason,
    )


def detect_drawio_runtime(config: dict[str, Any]) -> dict[str, Any]:
    first_found: dict[str, Any] | None = None
    host_platform = detect_host_platform()
    for candidate in get_drawio_candidates(config, target_platform=host_platform):
        resolved = resolve_drawio_candidate(candidate)
        if not resolved:
            continue

        probe = probe_drawio_command(config, candidate, resolved)
        if probe["runnable"]:
            return probe
        if first_found is None:
            first_found = probe

    if first_found is not None:
        return first_found

    requested = config.get("runtime", {}).get("drawio_bin")
    return build_drawio_probe_result(
        requested=requested,
        resolved=None,
        found=False,
        runnable=False,
        returncode=None,
        reason=(
            "No runnable draw.io CLI was found. Render will stay in source-only mode "
            "and skip PNG/SVG export."
        ),
    )


def resolve_helper_executor(config: dict[str, Any]) -> str | None:
    helper = config.get("runtime", {}).get("helper_executor")
    if not helper:
        return None

    helper_path = Path(helper).expanduser()
    if not helper_path.is_absolute():
        helper_path = resolve_path(helper)

    if helper_path.is_file() and os.access(helper_path, os.X_OK):
        return str(helper_path)
    return None


def parse_key_value_output(raw: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for line in raw.splitlines():
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        result[key.strip()] = value.strip()
    return result


def probe_helper_executor(config: dict[str, Any]) -> dict[str, Any]:
    host_platform = detect_host_platform()
    helper = resolve_helper_executor(config)
    if not helper:
        return {
            "available": False,
            "helper": None,
            "returncode": None,
            "reason": "No helper executor is configured or the helper script is not executable.",
        }

    if host_platform != "macos":
        return {
            "available": False,
            "helper": helper,
            "returncode": None,
            "reason": "The launchctl helper is only applicable on macOS.",
        }

    timeout = int(config.get("runtime", {}).get("helper_probe_timeout_sec", 5))
    proc = subprocess.run(
        [helper, "probe", "--timeout", str(timeout)],
        check=False,
        capture_output=True,
        text=True,
    )
    payload = parse_key_value_output(proc.stdout)
    available = proc.returncode == 0 and payload.get("status") == "ok"
    reason = payload.get("reason") or proc.stderr.strip() or proc.stdout.strip() or "helper probe failed"
    return {
        "available": available,
        "helper": helper,
        "returncode": proc.returncode,
        "reason": reason,
        "stdout": proc.stdout.strip(),
        "stderr": proc.stderr.strip(),
        "details": payload,
    }


def resolve_profile(config: dict[str, Any], preset: str | None, diagram_type: str | None) -> tuple[str, dict[str, Any]]:
    profiles = get_profiles(config)
    if preset:
        if preset not in profiles:
            raise SystemExit(f"Unknown preset: {preset}")
        return preset, profiles[preset]

    diagram_key = (diagram_type or "").strip().lower()
    if diagram_key:
        mapped = config.get("styles", {}).get("diagram_type_defaults", {}).get(diagram_key)
        if mapped and mapped in profiles:
            return mapped, profiles[mapped]

    default_profile = config.get("styles", {}).get("default_profile")
    if default_profile and default_profile in profiles:
        return default_profile, profiles[default_profile]

    fallback_template = config["paths"]["template"]
    return "default", {"label": "Default", "template": fallback_template, "diagram_types": [], "summary": "Fallback template"}


def profile_template_path(config: dict[str, Any], preset: str | None, diagram_type: str | None) -> tuple[str, dict[str, Any], Path]:
    profile_name, profile = resolve_profile(config, preset, diagram_type)
    template = profile.get("template", config["paths"]["template"])
    return profile_name, profile, resolve_path(template)


def export_command_parts(drawio_command: str, out_dir: Path, input_path: Path, fmt: str) -> list[str]:
    return [
        drawio_command,
        "-x",
        "-f",
        fmt,
        "-o",
        str(out_dir),
        str(input_path),
    ]


def resolve_drawio_command_hint(
    config: dict[str, Any],
    runtime: dict[str, Any],
    *,
    host_platform: str,
    target_platform: str,
) -> str:
    resolved = runtime.get("resolved")
    if resolved and target_platform == host_platform:
        return resolved
    if resolved and target_platform == "windows" and is_windows_style_command(resolved):
        return resolved

    first_generic: str | None = None
    for candidate in get_drawio_candidates(config, target_platform=target_platform):
        if target_platform == "windows" and candidate.startswith("/"):
            continue
        if target_platform != "windows" and is_windows_style_command(candidate):
            continue
        if target_platform == "windows":
            if is_windows_style_command(candidate):
                return candidate
            if first_generic is None:
                first_generic = candidate
            continue
        return candidate

    if target_platform == "windows":
        return first_generic or "drawio.exe"
    return "drawio"


def command_copy_template(args: argparse.Namespace) -> int:
    config = load_config()
    profile_name, profile, source = profile_template_path(config, args.preset, args.diagram_type)
    target = Path(args.output).expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)
    if args.json:
        print(
            json.dumps(
                {
                    "preset": profile_name,
                    "label": profile.get("label", profile_name),
                    "template": str(source),
                    "output": str(target),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    else:
        print(f"Preset: {profile_name}")
        print(f"Template: {source}")
        print(target)
    return 0


def build_export_commands(
    input_path: Path,
    out_dir: Path,
    config: dict[str, Any],
    formats: list[str],
    drawio_command: str | None = None,
    command_shell: str = "posix",
) -> list[str]:
    drawio_bin = drawio_command or config["runtime"]["drawio_bin"]
    commands: list[str] = []
    for fmt in formats:
        commands.append(
            render_command_for_shell(
                export_command_parts(drawio_bin, out_dir, input_path, fmt),
                command_shell,
            )
        )
    return commands


def export_path_for_format(input_path: Path, out_dir: Path, fmt: str) -> Path:
    return out_dir / f"{input_path.stem}.{fmt}"


def export_asset_status(input_path: Path, out_dir: Path, fmt: str) -> dict[str, Any]:
    output_path = export_path_for_format(input_path, out_dir, fmt)
    exists = output_path.exists()
    input_mtime = input_path.stat().st_mtime
    is_fresh = exists and output_path.stat().st_mtime + 1e-6 >= input_mtime
    return {
        "format": fmt,
        "path": str(output_path),
        "exists": exists,
        "is_fresh": is_fresh,
        "is_stale": exists and not is_fresh,
    }


def collect_export_asset_statuses(
    input_path: Path,
    out_dir: Path,
    formats: list[str],
) -> dict[str, dict[str, Any]]:
    return {fmt: export_asset_status(input_path, out_dir, fmt) for fmt in formats}


def run_export(
    input_path: Path,
    out_dir: Path,
    drawio_command: str,
    formats: list[str],
) -> list[dict[str, Any]]:
    out_dir.mkdir(parents=True, exist_ok=True)

    results: list[dict[str, Any]] = []
    for fmt in formats:
        command = export_command_parts(drawio_command, out_dir, input_path, fmt)
        proc = subprocess.run(command, check=False, capture_output=True, text=True)
        asset_status = export_asset_status(input_path, out_dir, fmt)
        results.append(
            {
                "format": fmt,
                "output": str(export_path_for_format(input_path, out_dir, fmt)),
                "command": render_command_for_shell(command, "posix"),
                "returncode": proc.returncode,
                "stdout": proc.stdout.strip(),
                "stderr": proc.stderr.strip(),
                "output_exists": asset_status["exists"],
                "output_fresh": asset_status["is_fresh"],
                "succeeded": proc.returncode == 0 or asset_status["is_fresh"],
            }
        )
    return results


def run_export_with_helper(
    input_path: Path,
    out_dir: Path,
    helper_path: str,
    drawio_command: str,
    formats: list[str],
    config: dict[str, Any],
) -> list[dict[str, Any]]:
    out_dir.mkdir(parents=True, exist_ok=True)
    timeout = int(config.get("runtime", {}).get("helper_export_timeout_sec", 30))

    results: list[dict[str, Any]] = []
    for fmt in formats:
        helper_command = [
            helper_path,
            "export",
            "--drawio-bin",
            drawio_command,
            "--input",
            str(input_path),
            "--out-dir",
            str(out_dir),
            "--format",
            fmt,
            "--timeout",
            str(timeout),
        ]
        proc = subprocess.run(helper_command, check=False, capture_output=True, text=True)
        payload = parse_key_value_output(proc.stdout)
        asset_status = export_asset_status(input_path, out_dir, fmt)
        results.append(
            {
                "format": fmt,
                "output": payload.get("output", str(export_path_for_format(input_path, out_dir, fmt))),
                "command": " ".join(shlex.quote(part) for part in helper_command),
                "executor": "helper",
                "returncode": proc.returncode,
                "stdout": proc.stdout.strip(),
                "stderr": proc.stderr.strip(),
                "helper_reason": payload.get("reason", ""),
                "helper_details": payload,
                "output_exists": asset_status["exists"],
                "output_fresh": asset_status["is_fresh"],
                "succeeded": proc.returncode == 0 and asset_status["is_fresh"],
            }
        )
    return results


def command_export_commands(args: argparse.Namespace) -> int:
    config = load_config()
    input_path, sanitization = prepare_input_path(Path(args.input))
    out_dir = normalize_out_dir(args.out_dir, config)
    formats = parse_formats(args.formats, config)
    host_platform = detect_host_platform()
    command_shell = normalize_command_shell(args.shell, host_platform)
    target_platform = infer_target_platform(host_platform, command_shell)
    runtime = detect_drawio_runtime(config)
    command_hint = resolve_drawio_command_hint(
        config,
        runtime,
        host_platform=host_platform,
        target_platform=target_platform,
    )

    commands = build_export_commands(
        input_path,
        out_dir,
        config,
        formats,
        drawio_command=command_hint,
        command_shell=command_shell,
    )
    if args.json:
        print(
            json.dumps(
                {
                    "input": str(input_path),
                    "out_dir": str(out_dir),
                    "input_sanitization": sanitization,
                    "host_platform": host_platform,
                    "target_platform": target_platform,
                    "command_shell": command_shell,
                    "drawio_runtime": runtime,
                    "drawio_command_hint": command_hint,
                    "commands": commands,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    else:
        print(f"Host platform: {host_platform}")
        print(f"Target platform: {target_platform}")
        print(f"Command shell: {command_shell}")
        print(f"Draw.io command hint: {command_hint}")
        if sanitization["changed"]:
            print("Note: Input file was sanitized before command generation.")
            if sanitization["backup_path"]:
                print(f"Note: Backup saved to {sanitization['backup_path']}")
            for reason in sanitization["reasons"]:
                print(f"Note: {reason}")
        if target_platform != host_platform:
            print("Note: export commands were generated for a different target shell/platform than the current host.")
        elif not runtime["runnable"]:
            print(f"Note: {runtime['reason']}")
        for command in commands:
            print(command)
    return 0


def run_lint(input_path: Path, config: dict[str, Any]) -> dict[str, Any]:
    lint_script = resolve_path(config["paths"]["lint_script"])
    try:
        proc = subprocess.run(
            [sys.executable, str(lint_script), str(input_path), "--json"],
            check=True,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or exc.stdout).strip() or "draw.io lint failed"
        raise SystemExit(detail) from exc
    return json.loads(proc.stdout)


def build_qa_report(
    input_path: Path,
    out_dir: Path,
    config: dict[str, Any],
    lint_report: dict[str, Any],
    report_formats: list[str],
    required_formats: list[str],
) -> dict[str, Any]:
    issue_count = int(lint_report.get("issue_count", 0))
    max_allowed = int(config["quality"]["max_allowed_lint_issues"])
    asset_statuses = collect_export_asset_statuses(input_path, out_dir, report_formats)

    inspect_format = config["exports"]["inspect_format"]
    inspect_status = asset_statuses.get(inspect_format) or export_asset_status(input_path, out_dir, inspect_format)
    required_missing = [fmt for fmt in required_formats if not asset_statuses[fmt]["exists"]]
    required_stale = [fmt for fmt in required_formats if asset_statuses[fmt]["is_stale"]]
    manual_review_required = bool(config["quality"].get("require_png_review", True))
    manual_review_pending = manual_review_required and not inspect_status["exists"]
    manual_review_stale = manual_review_required and inspect_status["exists"] and not inspect_status["is_fresh"]
    should_fix = (
        issue_count > max_allowed
        or bool(required_missing)
        or bool(required_stale)
        or manual_review_pending
        or manual_review_stale
    )

    return {
        "input": str(input_path),
        "lint_page_count": int(lint_report.get("page_count", 0)),
        "lint_pages": lint_report.get("pages", []),
        "lint_issue_count": issue_count,
        "lint_issues": lint_report.get("issues", []),
        "inspect_image": inspect_status["path"],
        "inspect_image_exists": inspect_status["exists"],
        "inspect_image_fresh": inspect_status["is_fresh"],
        "export_assets": asset_statuses,
        "required_formats": required_formats,
        "missing_required_exports": required_missing,
        "stale_required_exports": required_stale,
        "manual_review_required": manual_review_required,
        "manual_review_pending": manual_review_pending,
        "manual_review_stale": manual_review_stale,
        "manual_checklist": config["quality"]["manual_checklist"],
        "should_fix": should_fix,
    }


def command_list_profiles(args: argparse.Namespace) -> int:
    config = load_config()
    profiles = get_profiles(config)
    if args.json:
        print(json.dumps(profiles, ensure_ascii=False, indent=2))
        return 0

    for name, profile in profiles.items():
        diagram_types = ", ".join(profile.get("diagram_types", []))
        print(f"{name}: {profile.get('label', name)}")
        print(f"  summary: {profile.get('summary', '')}")
        print(f"  template: {resolve_path(profile.get('template', config['paths']['template']))}")
        print(f"  diagram types: {diagram_types}")
    return 0


def command_show_profile(args: argparse.Namespace) -> int:
    config = load_config()
    profile_name, profile = resolve_profile(config, args.preset, args.diagram_type)
    payload = {
        "preset": profile_name,
        "label": profile.get("label", profile_name),
        "summary": profile.get("summary", ""),
        "template": str(resolve_path(profile.get("template", config["paths"]["template"]))),
        "diagram_types": profile.get("diagram_types", []),
        "background": profile.get("background"),
        "surface": profile.get("surface"),
        "title_color": profile.get("title_color"),
        "body_color": profile.get("body_color"),
        "accent_palette": profile.get("accent_palette", []),
        "node_shape": profile.get("node_shape"),
        "corner_radius": profile.get("corner_radius"),
        "stroke_style": profile.get("stroke_style"),
        "shadow": profile.get("shadow"),
        "connector_style": profile.get("connector_style"),
        "text_density": profile.get("text_density"),
        "image_style_fields": config.get("styles", {}).get("image_style_fields", []),
    }

    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(f"Preset: {payload['preset']}")
        print(f"Label: {payload['label']}")
        print(f"Summary: {payload['summary']}")
        print(f"Template: {payload['template']}")
        print(f"Diagram types: {', '.join(payload['diagram_types'])}")
        print("Visual contract:")
        print(f"- Background: {payload['background']}")
        print(f"- Surface: {payload['surface']}")
        print(f"- Title color: {payload['title_color']}")
        print(f"- Body color: {payload['body_color']}")
        print(f"- Accent palette: {', '.join(payload['accent_palette'])}")
        print(f"- Node shape: {payload['node_shape']}")
        print(f"- Corner radius: {payload['corner_radius']}")
        print(f"- Stroke style: {payload['stroke_style']}")
        print(f"- Shadow: {payload['shadow']}")
        print(f"- Connector style: {payload['connector_style']}")
        print(f"- Text density: {payload['text_density']}")
        print("Reference image extraction fields:")
        for field in payload["image_style_fields"]:
            print(f"- {field}")
    return 0


def command_qa_report(args: argparse.Namespace) -> int:
    config = load_config()
    input_path, sanitization = prepare_input_path(Path(args.input))
    out_dir = normalize_out_dir(args.out_dir, config)
    parsed_formats = parse_formats(args.formats, config) if args.formats else None
    report_formats = parsed_formats or list(config["exports"]["default_formats"])
    inspect_format = config["exports"]["inspect_format"]
    if inspect_format not in report_formats:
        report_formats.append(inspect_format)
    required_formats = parsed_formats or [inspect_format]
    lint_report = run_lint(input_path, config)
    report = build_qa_report(input_path, out_dir, config, lint_report, report_formats, required_formats)
    report["input_sanitization"] = sanitization

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(f"Input: {report['input']}")
        if sanitization["changed"]:
            print("Input sanitization:")
            if sanitization["backup_path"]:
                print(f"- Backup: {sanitization['backup_path']}")
            for reason in sanitization["reasons"]:
                print(f"- {reason}")
        print(f"Lint pages: {report['lint_page_count']}")
        print(f"Inspect image: {report['inspect_image']}")
        print(f"Inspect image exists: {report['inspect_image_exists']}")
        print(f"Inspect image fresh: {report['inspect_image_fresh']}")
        print(f"Lint issues: {report['lint_issue_count']}")
        for issue in report["lint_issues"]:
            page_label = ""
            if "page_index" in issue:
                page_label = f"Page {issue['page_index']}"
                if issue.get("page_name"):
                    page_label += f" ({issue['page_name']}) "
            target = f" -> {issue['target_id']}" if "target_id" in issue else ""
            print(f"- [{issue['type']}] {page_label}{issue['cell_id']}{target}: {issue['message']}")
        if report["missing_required_exports"]:
            print(f"Missing required exports: {', '.join(report['missing_required_exports'])}")
        if report["stale_required_exports"]:
            print(f"Stale required exports: {', '.join(report['stale_required_exports'])}")
        if report["manual_review_pending"]:
            print("Manual review pending: inspect PNG is missing.")
        if report["manual_review_stale"]:
            print("Manual review pending: inspect PNG is stale.")
        print("Export assets:")
        for fmt in report["export_assets"]:
            asset = report["export_assets"][fmt]
            print(
                f"- {fmt}: {asset['path']} "
                f"(exists={asset['exists']}, fresh={asset['is_fresh']})"
            )
        print("Manual checklist:")
        for item in report["manual_checklist"]:
            print(f"- {item}")
        print(f"Should fix: {report['should_fix']}")

    return 1 if args.strict and report["should_fix"] else 0


def command_render(args: argparse.Namespace) -> int:
    config = load_config()
    input_path, sanitization = prepare_input_path(Path(args.input))
    out_dir = normalize_out_dir(args.out_dir, config)
    host_platform = detect_host_platform()
    drawio_runtime = detect_drawio_runtime(config)
    helper_runtime = probe_helper_executor(config)
    requested_formats = parse_formats(args.formats, config)
    lint_report = run_lint(input_path, config)
    render_mode = "source-only"
    executor = "none"
    final_formats: list[str] = []
    qa_formats: list[str] = []
    qa_required_formats: list[str] = []
    auto_added_formats: list[str] = []
    exports: list[dict[str, Any]] = []
    export_failures: list[dict[str, Any]] = []
    notes: list[str] = []

    if drawio_runtime["runnable"] and drawio_runtime["resolved"]:
        final_formats, auto_added_formats = ensure_inspect_format(requested_formats, config)
        qa_formats = list(final_formats)
        qa_required_formats = list(final_formats)
        executor = "direct"
        render_mode = "export-failed"
        exports = run_export(input_path, out_dir, drawio_runtime["resolved"], final_formats)
        export_failures = [item for item in exports if not item["succeeded"]]
        if not export_failures:
            render_mode = "exported"
        notes.append(drawio_runtime["reason"])
    elif (
        helper_runtime["available"]
        and drawio_runtime.get("resolved")
        and drawio_runtime.get("found")
    ):
        final_formats, auto_added_formats = ensure_inspect_format(requested_formats, config)
        qa_formats = list(final_formats)
        qa_required_formats = list(final_formats)
        executor = "helper"
        render_mode = "export-failed"
        exports = run_export_with_helper(
            input_path,
            out_dir,
            helper_runtime["helper"],
            drawio_runtime["resolved"],
            final_formats,
            config,
        )
        export_failures = [item for item in exports if not item["succeeded"]]
        if not export_failures:
            render_mode = "exported"
        notes.append("Using launchctl helper to export draw.io outside the Python process tree.")
    else:
        qa_formats, qa_auto_added = ensure_inspect_format(requested_formats, config)
        qa_required_formats = list(qa_formats)
        if qa_auto_added:
            auto_added_formats = qa_auto_added
        notes.append(drawio_runtime["reason"])
        if helper_runtime["reason"]:
            notes.append(helper_runtime["reason"])
        notes.append(
            "Source-only mode is enabled. The skill will return the .drawio file and skip PNG/SVG export."
        )
        notes.append(
            "QA stays pending in source-only mode until the requested export artifacts, including the PNG review image, are available and fresh."
        )

    qa_report = build_qa_report(
        input_path,
        out_dir,
        config,
        lint_report,
        qa_formats,
        qa_required_formats,
    )

    report = {
        "input": str(input_path),
        "out_dir": str(out_dir),
        "input_sanitization": sanitization,
        "host_platform": host_platform,
        "mode": render_mode,
        "executor": executor,
        "source_file": str(input_path),
        "drawio_runtime": drawio_runtime,
        "helper_runtime": helper_runtime,
        "requested_formats": requested_formats,
        "rendered_formats": final_formats,
        "auto_added_formats": auto_added_formats,
        "exports": exports,
        "fallback_commands": (
            build_export_commands(
                input_path,
                out_dir,
                config,
                requested_formats,
                drawio_command=drawio_runtime["resolved"] or config["runtime"]["drawio_bin"],
            )
            if drawio_runtime["resolved"]
            else []
        ),
        "notes": notes,
        "qa": qa_report,
    }

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(f"Input: {report['input']}")
        print(f"Out dir: {report['out_dir']}")
        if sanitization["changed"]:
            print("Input sanitization:")
            if sanitization["backup_path"]:
                print(f"- Backup: {sanitization['backup_path']}")
            for reason in sanitization["reasons"]:
                print(f"- {reason}")
        print(f"Host platform: {report['host_platform']}")
        print(f"Mode: {report['mode']}")
        print(f"Executor: {report['executor']}")
        print(f"Source file: {report['source_file']}")
        if drawio_runtime["resolved"]:
            print(f"Draw.io command: {drawio_runtime['resolved']}")
        else:
            print("Draw.io command: not found")
        print(f"Draw.io runnable here: {drawio_runtime['runnable']}")
        if helper_runtime.get("helper"):
            print(f"Helper executor: {helper_runtime['helper']}")
        print(f"Helper available here: {helper_runtime.get('available', False)}")
        if report["rendered_formats"]:
            print(f"Rendered formats: {', '.join(report['rendered_formats'])}")
        if report["auto_added_formats"]:
            print(
                "Auto-added formats for QA review: "
                + ", ".join(report["auto_added_formats"])
            )
        for note in report["notes"]:
            print(f"Note: {note}")
        if report["exports"]:
            print("Export results:")
            for item in report["exports"]:
                status = "ok" if item["succeeded"] else f"failed ({item['returncode']})"
                print(f"- [{item['format']}] {status}: {item['output']}")
                if item["stdout"]:
                    print(f"  stdout: {item['stdout']}")
                if item["stderr"]:
                    print(f"  stderr: {item['stderr']}")
        elif report["mode"] != "source-only" and report["fallback_commands"]:
            print("Suggested export commands:")
            for command in report["fallback_commands"]:
                print(f"- {command}")
        print("QA summary:")
        print(f"- Lint pages: {qa_report['lint_page_count']}")
        print(f"- Inspect image exists: {qa_report['inspect_image_exists']}")
        print(f"- Inspect image fresh: {qa_report['inspect_image_fresh']}")
        print(f"- Lint issues: {qa_report['lint_issue_count']}")
        if qa_report["missing_required_exports"]:
            print(f"- Missing required exports: {', '.join(qa_report['missing_required_exports'])}")
        if qa_report["stale_required_exports"]:
            print(f"- Stale required exports: {', '.join(qa_report['stale_required_exports'])}")
        if qa_report["manual_review_pending"]:
            print("- Manual review pending: inspect PNG is missing")
        if qa_report["manual_review_stale"]:
            print("- Manual review pending: inspect PNG is stale")
        print(f"- Should fix: {qa_report['should_fix']}")

    if export_failures:
        return 1
    return 1 if args.strict and qa_report["should_fix"] else 0


def command_sanitize_input(args: argparse.Namespace) -> int:
    input_path, sanitization = prepare_input_path(Path(args.input))
    payload = {
        "input": str(input_path),
        "input_sanitization": sanitization,
    }
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(f"Input: {payload['input']}")
        print(f"Sanitized: {sanitization['changed']}")
        if sanitization["backup_path"]:
            print(f"Backup: {sanitization['backup_path']}")
        if sanitization["reasons"]:
            print("Reasons:")
            for reason in sanitization["reasons"]:
                print(f"- {reason}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Utilities for the draw.io modern diagrams skill."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    list_profiles = subparsers.add_parser("list-profiles", help="List bundled style presets")
    list_profiles.add_argument("--json", action="store_true", help="Emit JSON")
    list_profiles.set_defaults(func=command_list_profiles)

    show_profile = subparsers.add_parser("show-profile", help="Show one bundled style preset")
    show_profile.add_argument("--preset", help="Preset name from config.json")
    show_profile.add_argument("--diagram-type", help="Diagram type to resolve via defaults")
    show_profile.add_argument("--json", action="store_true", help="Emit JSON")
    show_profile.set_defaults(func=command_show_profile)

    copy_template = subparsers.add_parser("copy-template", help="Copy a bundled template")
    copy_template.add_argument("--output", required=True, help="Where to write the copied .drawio file")
    copy_template.add_argument("--preset", help="Preset name from config.json")
    copy_template.add_argument("--diagram-type", help="Diagram type to resolve via defaults")
    copy_template.add_argument("--json", action="store_true", help="Emit JSON")
    copy_template.set_defaults(func=command_copy_template)

    sanitize_input = subparsers.add_parser(
        "sanitize-input",
        help="Repair accidental leading or trailing non-draw.io content in a .drawio file",
    )
    sanitize_input.add_argument("--input", required=True, help="Path to the .drawio file")
    sanitize_input.add_argument("--json", action="store_true", help="Emit JSON")
    sanitize_input.set_defaults(func=command_sanitize_input)

    export_commands = subparsers.add_parser("export-commands", help="Print raw draw.io export commands")
    export_commands.add_argument("--input", required=True, help="Path to the .drawio file")
    export_commands.add_argument("--out-dir", help="Directory where exported files should go")
    export_commands.add_argument("--formats", help="Comma-separated formats, defaults to config.json")
    export_commands.add_argument(
        "--shell",
        choices=("auto", "posix", "powershell", "cmd"),
        default="auto",
        help="Command shell style. auto uses PowerShell on Windows and POSIX shells elsewhere.",
    )
    export_commands.add_argument("--json", action="store_true", help="Emit JSON")
    export_commands.set_defaults(func=command_export_commands)

    qa_report = subparsers.add_parser("qa-report", help="Summarize lint result and exported image presence")
    qa_report.add_argument("--input", required=True, help="Path to the .drawio file")
    qa_report.add_argument("--out-dir", help="Directory where exported files should exist")
    qa_report.add_argument("--formats", help="Comma-separated formats to require as fresh exports")
    qa_report.add_argument("--json", action="store_true", help="Emit JSON")
    qa_report.add_argument("--strict", action="store_true", help="Exit 1 when the diagram still needs fixes")
    qa_report.set_defaults(func=command_qa_report)

    render = subparsers.add_parser("render", help="Export via draw.io CLI and run QA in one step")
    render.add_argument("--input", required=True, help="Path to the .drawio file")
    render.add_argument("--out-dir", help="Directory where exported files should go")
    render.add_argument("--formats", help="Comma-separated formats, defaults to config.json")
    render.add_argument("--json", action="store_true", help="Emit JSON")
    render.add_argument("--strict", action="store_true", help="Exit 1 when QA still needs fixes")
    render.set_defaults(func=command_render)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
