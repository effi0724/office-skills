#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import fnmatch
import json
import subprocess
import sys
import time
from pathlib import Path, PurePosixPath
from typing import Any

LINEAR_KEY_CHARS = set("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-")


class SkillError(RuntimeError):
    """Domain-specific failure for friendly CLI exits."""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate Chinese weekly reports from GitHub commits.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    for command in ("validate-config", "preview-range", "generate-report"):
        subparser = subparsers.add_parser(command)
        subparser.add_argument("--config", required=True, help="Path to the JSON config file.")

    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        config_path = Path(args.config).resolve()
        raw_config = load_json(config_path)
        auth_user = get_authenticated_user()
        config = normalize_config(raw_config, auth_user)
        validate_config(config)
        repo_metas = get_repo_metas(config["repos"])
        hydrate_repo_defaults(config["repos"], repo_metas)

        if args.command == "validate-config":
            payload = {
                "status": "ok",
                "auth_user": auth_user,
                "config_path": str(config_path),
                "repositories": repo_metas,
            }
            print(json.dumps(payload, ensure_ascii=False, indent=2))
            return 0

        range_info = resolve_range(config["range"])
        records = collect_records(config["repos"], range_info)
        dataset = build_dataset(config, range_info, records, auth_user)

        if args.command == "preview-range":
            preview = {
                "status": "ok",
                "range": range_info,
                "configured_repo_count": dataset["meta"]["configured_repo_count"],
                "matched_repo_count": dataset["meta"]["matched_repo_count"],
                "matched_commit_count": len(records),
                "repositories": dataset["meta"]["repository_rollup"],
                "matched_commits": [
                    {
                        "repo": record["repo_label"],
                        "sha": record["short_sha"],
                        "subject": record["subject"],
                        "author": record["author_display"],
                        "scopes": record["display_scopes"],
                    }
                    for record in records[:20]
                ],
            }
            print(json.dumps(preview, ensure_ascii=False, indent=2))
            return 0

        output_dir = write_outputs(config, config_path, dataset)
        payload = {
            "status": "ok",
            "output_dir": str(output_dir),
            "files": {
                "summary": str(output_dir / "weekly-summary.md"),
                "report": str(output_dir / "weekly-report.md"),
                "source_data": str(output_dir / "source-data.json"),
            },
            "configured_repo_count": dataset["meta"]["configured_repo_count"],
            "matched_repo_count": dataset["meta"]["matched_repo_count"],
            "matched_commit_count": len(records),
            "matched_pr_count": dataset["meta"]["matched_pr_count"],
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0
    except SkillError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


def load_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise SkillError(f"config file not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise SkillError(f"invalid JSON in {path}: {exc}") from exc


def normalize_config(raw: dict[str, Any], auth_user: str) -> dict[str, Any]:
    global_filters = normalize_filters(raw.get("filters", {}), default_authors=[auth_user])

    return {
        "repos": normalize_repositories(raw, global_filters),
        "range": {
            "mode": str(raw.get("range", {}).get("mode", "")).strip() or "current_week",
            "start": str(raw.get("range", {}).get("start", "")).strip(),
            "end": str(raw.get("range", {}).get("end", "")).strip(),
            "base_sha": str(raw.get("range", {}).get("base_sha", "")).strip(),
            "head_sha": str(raw.get("range", {}).get("head_sha", "")).strip(),
        },
        "report": {
            "language": str(raw.get("report", {}).get("language", "")).strip() or "zh-CN",
            "style": str(raw.get("report", {}).get("style", "")).strip() or "manager",
            "output_dir": str(raw.get("report", {}).get("output_dir", "")).strip() or "outputs",
        },
    }


def normalize_repositories(raw: dict[str, Any], global_filters: dict[str, Any]) -> list[dict[str, Any]]:
    raw_repos = raw.get("repos")
    if raw_repos is None:
        raw_repo = raw.get("repo")
        raw_repos = [raw_repo] if isinstance(raw_repo, dict) else []

    repos: list[dict[str, Any]] = []
    for raw_repo in raw_repos if isinstance(raw_repos, list) else []:
        repo = raw_repo if isinstance(raw_repo, dict) else {}
        owner = str(repo.get("owner", "")).strip()
        name = str(repo.get("name", "")).strip()
        full_name = f"{owner}/{name}" if owner and name else ""
        alias = str(repo.get("alias", "")).strip()
        repo_filters = normalize_filters(repo.get("filters", {}), fallback=global_filters)
        repos.append(
            {
                "owner": owner,
                "name": name,
                "full_name": full_name,
                "alias": alias,
                "label": alias or full_name,
                "default_branch": str(repo.get("default_branch", "")).strip() or "main",
                "filters": repo_filters,
            }
        )
    return repos


def normalize_filters(raw_filters: Any, *, default_authors: list[str] | None = None, fallback: dict[str, Any] | None = None) -> dict[str, Any]:
    source = raw_filters if isinstance(raw_filters, dict) else {}
    base = fallback or {
        "authors": [author for author in (default_authors or []) if author],
        "include_paths": [],
        "exclude_paths": [],
        "exclude_merge_commits": True,
    }

    authors = normalize_string_list(source.get("authors")) if "authors" in source else list(base["authors"])
    if not authors and default_authors is not None:
        authors = [author for author in default_authors if author]
    if not authors and fallback is not None:
        authors = list(fallback["authors"])

    return {
        "authors": authors,
        "include_paths": normalize_string_list(source.get("include_paths")) if "include_paths" in source else list(base["include_paths"]),
        "exclude_paths": normalize_string_list(source.get("exclude_paths")) if "exclude_paths" in source else list(base["exclude_paths"]),
        "exclude_merge_commits": bool(source["exclude_merge_commits"]) if "exclude_merge_commits" in source else bool(base["exclude_merge_commits"]),
    }


def normalize_string_list(values: Any) -> list[str]:
    if not isinstance(values, list):
        return []
    return [str(value).strip() for value in values if str(value).strip()]


def validate_config(config: dict[str, Any]) -> None:
    repos = config["repos"]
    range_cfg = config["range"]
    report = config["report"]

    if not repos:
        raise SkillError("at least one repository is required via repos[] or legacy repo")

    seen = set()
    for repo in repos:
        if not repo["owner"] or not repo["name"]:
            raise SkillError("each repository requires owner and name")
        if repo["full_name"] in seen:
            raise SkillError(f"duplicate repository configured: {repo['full_name']}")
        seen.add(repo["full_name"])

    mode = range_cfg["mode"]
    if mode not in {"current_week", "date_range", "commit_compare"}:
        raise SkillError("range.mode must be one of current_week, date_range, commit_compare")
    if mode == "date_range" and (not range_cfg["start"] or not range_cfg["end"]):
        raise SkillError("range.start and range.end are required for date_range")
    if mode == "commit_compare" and (not range_cfg["base_sha"] or not range_cfg["head_sha"]):
        raise SkillError("range.base_sha and range.head_sha are required for commit_compare")
    if report["language"] != "zh-CN":
        raise SkillError("report.language must be zh-CN in v1")
    if report["style"] != "manager":
        raise SkillError("report.style must be manager in v1")


def get_authenticated_user() -> str:
    auth_status = subprocess.run(
        ["gh", "auth", "status"],
        capture_output=True,
        text=True,
        check=False,
    )
    try:
        user = gh_api_json("user")
    except SkillError as exc:
        details = (auth_status.stderr or auth_status.stdout or "").strip()
        if details:
            raise SkillError(
                "GitHub auth failed; run `gh auth login -h github.com -s repo,read:org` or export `GH_TOKEN`/`GITHUB_TOKEN`. "
                f"Details: {details or exc}"
            ) from exc
        raise SkillError(
            "GitHub auth failed; run `gh auth login -h github.com -s repo,read:org` or export `GH_TOKEN`/`GITHUB_TOKEN`."
        ) from exc

    login = str(user.get("login", "")).strip()
    if not login:
        raise SkillError("failed to resolve current GitHub user via `gh api user`")
    return login


def get_repo_metas(repos: list[dict[str, Any]]) -> list[dict[str, Any]]:
    repo_metas = []
    for repo in repos:
        payload = gh_api_json(f"repos/{repo['owner']}/{repo['name']}")
        repo_metas.append(
            {
                "full_name": payload.get("full_name", repo["full_name"]),
                "default_branch": payload.get("default_branch", repo["default_branch"]),
                "private": bool(payload.get("private", False)),
                "alias": repo["alias"],
                "label": repo["alias"] or payload.get("full_name", repo["full_name"]),
            }
        )
    return repo_metas


def hydrate_repo_defaults(repos: list[dict[str, Any]], repo_metas: list[dict[str, Any]]) -> None:
    meta_map = {item["full_name"]: item for item in repo_metas}
    for repo in repos:
        meta = meta_map.get(repo["full_name"])
        if not meta:
            continue
        repo["default_branch"] = meta["default_branch"]
        repo["label"] = repo["alias"] or meta["full_name"]


def gh_api_json(endpoint: str, *, params: dict[str, Any] | None = None, headers: list[str] | None = None) -> Any:
    command = ["gh", "api", "--method", "GET", endpoint]
    for header in headers or []:
        command.extend(["-H", header])
    for key, value in (params or {}).items():
        if value is None or value == "":
            continue
        command.extend(["-f", f"{key}={value}"])

    last_error = ""
    for attempt in range(3):
        result = subprocess.run(command, capture_output=True, text=True, check=False)
        if result.returncode == 0:
            payload = result.stdout.strip()
            if not payload:
                return None
            return json.loads(payload)

        last_error = (result.stderr or result.stdout or "").strip()
        if attempt == 2 or not is_transient_gh_error(last_error):
            raise SkillError(f"`{' '.join(command)}` failed: {last_error}")
        time.sleep(0.5 * (attempt + 1))

    raise SkillError(f"`{' '.join(command)}` failed: {last_error}")


def is_transient_gh_error(message: str) -> bool:
    lowered = message.lower()
    transient_markers = [
        "eof",
        "connection reset",
        "timeout",
        "tls handshake timeout",
        "temporary failure",
        "502",
        "503",
        "504",
    ]
    return any(marker in lowered for marker in transient_markers)


def resolve_range(range_cfg: dict[str, Any], now: dt.datetime | None = None) -> dict[str, Any]:
    local_now = now or dt.datetime.now().astimezone()
    mode = range_cfg["mode"]

    if mode == "current_week":
        week_start = (local_now - dt.timedelta(days=local_now.isoweekday() - 1)).replace(
            hour=0,
            minute=0,
            second=0,
            microsecond=0,
        )
        iso = week_start.isocalendar()
        return {
            "mode": mode,
            "label": f"{iso.year}-W{iso.week:02d}",
            "start_iso": to_github_iso(week_start),
            "end_iso": to_github_iso(local_now),
            "description": f"本周（{week_start.date()} 到 {local_now.date()}）",
            "base_sha": "",
            "head_sha": "",
        }

    if mode == "date_range":
        start = parse_datetime(range_cfg["start"], end_of_day=False)
        end = parse_datetime(range_cfg["end"], end_of_day=True)
        if end < start:
            raise SkillError("range.end must be later than range.start")
        if start.isocalendar()[:2] == end.isocalendar()[:2]:
            label = f"{start.isocalendar().year}-W{start.isocalendar().week:02d}"
        else:
            label = f"{start:%Y%m%d}-{end:%Y%m%d}"
        return {
            "mode": mode,
            "label": label,
            "start_iso": to_github_iso(start),
            "end_iso": to_github_iso(end),
            "description": f"日期范围（{start.isoformat()} 到 {end.isoformat()}）",
            "base_sha": "",
            "head_sha": "",
        }

    base_sha = range_cfg["base_sha"]
    head_sha = range_cfg["head_sha"]
    return {
        "mode": mode,
        "label": f"{base_sha[:7]}...{head_sha[:7]}",
        "start_iso": "",
        "end_iso": "",
        "description": f"commit compare（{base_sha[:7]}...{head_sha[:7]}）",
        "base_sha": base_sha,
        "head_sha": head_sha,
    }


def parse_datetime(value: str, *, end_of_day: bool) -> dt.datetime:
    if len(value) == 10:
        base = dt.datetime.fromisoformat(value)
        local_tz = dt.datetime.now().astimezone().tzinfo
        if end_of_day:
            return base.replace(hour=23, minute=59, second=59, microsecond=0, tzinfo=local_tz)
        return base.replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=local_tz)

    parsed = dt.datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.datetime.now().astimezone().tzinfo)
    return parsed


def to_github_iso(value: dt.datetime) -> str:
    return value.astimezone(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def collect_records(repos: list[dict[str, Any]], range_info: dict[str, Any]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    multi_repo = len(repos) > 1

    for repo in repos:
        shas = collect_shas(repo, range_info)
        for sha in shas:
            detail = gh_api_json(f"repos/{repo['owner']}/{repo['name']}/commits/{sha}")
            record = normalize_record(detail, repo, multi_repo=multi_repo)
            if not commit_matches_filters(record, repo["filters"]):
                continue
            record["pull_requests"] = fetch_associated_prs(repo, sha)
            record["linear_keys"] = sorted(extract_linear_keys(record))
            records.append(record)

    records.sort(key=lambda item: item["committed_at"], reverse=True)
    return records


def collect_shas(repo: dict[str, Any], range_info: dict[str, Any]) -> list[str]:
    if range_info["mode"] == "commit_compare":
        compare = gh_api_json(
            f"repos/{repo['owner']}/{repo['name']}/compare/{range_info['base_sha']}...{range_info['head_sha']}"
        )
        return [item["sha"] for item in compare.get("commits", [])]

    shas: list[str] = []
    page = 1
    while True:
        payload = gh_api_json(
            f"repos/{repo['owner']}/{repo['name']}/commits",
            params={
                "sha": repo["default_branch"],
                "since": range_info["start_iso"],
                "until": range_info["end_iso"],
                "per_page": 100,
                "page": page,
            },
        )
        if not payload:
            break
        shas.extend(item["sha"] for item in payload)
        if len(payload) < 100:
            break
        page += 1
    return shas


def normalize_record(detail: dict[str, Any], repo: dict[str, Any], *, multi_repo: bool) -> dict[str, Any]:
    commit_data = detail.get("commit", {})
    author = detail.get("author") or {}
    files = [item["filename"] for item in detail.get("files", [])]
    top_scopes = sorted({top_scope(path) for path in files})

    return {
        "repo_full_name": repo["full_name"],
        "repo_label": repo["label"],
        "repo_default_branch": repo["default_branch"],
        "sha": detail["sha"],
        "short_sha": detail["sha"][:7],
        "html_url": detail.get("html_url", ""),
        "subject": commit_subject(commit_data.get("message", "")),
        "body": commit_body(commit_data.get("message", "")),
        "author_display": author.get("login") or commit_data.get("author", {}).get("name", "unknown"),
        "author_login": author.get("login", ""),
        "author_email": commit_data.get("author", {}).get("email", ""),
        "authored_at": commit_data.get("author", {}).get("date", ""),
        "committed_at": commit_data.get("committer", {}).get("date", ""),
        "is_merge": len(detail.get("parents", [])) > 1 or commit_subject(commit_data.get("message", "")).lower().startswith("merge "),
        "files": files,
        "top_scopes": top_scopes,
        "display_scopes": [display_scope(repo["label"], scope, multi_repo=multi_repo) for scope in top_scopes],
        "stats": detail.get("stats", {}),
    }


def commit_subject(message: str) -> str:
    return message.splitlines()[0].strip() if message else "(no subject)"


def commit_body(message: str) -> str:
    lines = message.splitlines()
    return "\n".join(lines[1:]).strip() if len(lines) > 1 else ""


def top_scope(path: str) -> str:
    parts = PurePosixPath(path).parts
    if not parts:
        return "(repo-root)"
    if len(parts) == 1:
        return "(repo-root)"
    if parts[0] in {"apps", "packages", "services", "skills", "docs", "scripts"} and len(parts) > 1:
        return f"{parts[0]}/{parts[1]}"
    return parts[0]


def display_scope(repo_label: str, scope: str, *, multi_repo: bool) -> str:
    if not multi_repo:
        return scope
    return f"{repo_label}:{scope}"


def commit_matches_filters(record: dict[str, Any], filters: dict[str, Any]) -> bool:
    if filters["exclude_merge_commits"] and record["is_merge"]:
        return False
    if not author_matches(record, filters["authors"]):
        return False
    if not path_matches(record["files"], filters["include_paths"], filters["exclude_paths"]):
        return False
    return True


def author_matches(record: dict[str, Any], allowed: list[str]) -> bool:
    if not allowed:
        return True
    normalized = {value.lower() for value in allowed}
    candidates = {
        record["author_display"].lower(),
        record["author_login"].lower(),
        record["author_email"].lower(),
    }
    return any(candidate in normalized for candidate in candidates if candidate)


def path_matches(files: list[str], include_paths: list[str], exclude_paths: list[str]) -> bool:
    if not files:
        return not include_paths
    if include_paths and not any(any(fnmatch.fnmatch(path, pattern) for pattern in include_paths) for path in files):
        return False
    if exclude_paths and all(any(fnmatch.fnmatch(path, pattern) for pattern in exclude_paths) for path in files):
        return False
    return True


def fetch_associated_prs(repo: dict[str, Any], sha: str) -> list[dict[str, Any]]:
    try:
        payload = gh_api_json(
            f"repos/{repo['owner']}/{repo['name']}/commits/{sha}/pulls",
            headers=["Accept: application/vnd.github+json"],
        )
    except SkillError:
        return []

    if not isinstance(payload, list):
        return []
    return [
        {
            "number": item.get("number"),
            "title": item.get("title", ""),
            "body": item.get("body", "") or "",
            "html_url": item.get("html_url", ""),
        }
        for item in payload
    ]


def extract_linear_keys(record: dict[str, Any]) -> set[str]:
    buffer = "\n".join(
        [record["subject"], record["body"]]
        + [pull_request["title"] for pull_request in record["pull_requests"]]
        + [pull_request["body"] for pull_request in record["pull_requests"]]
    )

    tokens = set()
    current = []
    for char in buffer:
        if char in LINEAR_KEY_CHARS:
            current.append(char)
        else:
            token = "".join(current)
            if is_linear_key(token):
                tokens.add(token)
            current = []
    token = "".join(current)
    if is_linear_key(token):
        tokens.add(token)
    return tokens


def is_linear_key(token: str) -> bool:
    if "-" not in token or len(token) < 4:
        return False
    prefix, suffix = token.split("-", 1)
    return prefix.isupper() and suffix.isdigit()


def build_dataset(
    config: dict[str, Any],
    range_info: dict[str, Any],
    records: list[dict[str, Any]],
    auth_user: str,
) -> dict[str, Any]:
    repo_rollup = build_repo_rollup(config["repos"], records)
    unique_prs = collect_unique_prs(records)
    linear_keys = sorted({key for record in records for key in record["linear_keys"]})
    scopes = sorted({scope for record in records for scope in record["display_scopes"]})
    work_items = build_work_items(records)
    risks = build_risks(records, linear_keys, repo_rollup)
    next_steps = build_next_steps(records, linear_keys, repo_rollup)

    return {
        "meta": {
            "configured_repo_count": len(config["repos"]),
            "matched_repo_count": sum(1 for item in repo_rollup if item["matched_commit_count"] > 0),
            "configured_repositories": [repo["full_name"] for repo in config["repos"]],
            "range": range_info,
            "auth_user": auth_user,
            "matched_commit_count": len(records),
            "matched_pr_count": len(unique_prs),
            "matched_linear_keys": linear_keys,
            "scopes": scopes,
            "repository_rollup": repo_rollup,
        },
        "work_items": work_items,
        "business_impact": build_business_impact(records, repo_rollup, unique_prs, scopes),
        "risks": risks,
        "next_steps": next_steps,
        "commits": records,
        "pull_requests": unique_prs,
    }


def build_repo_rollup(configured_repos: list[dict[str, Any]], records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rollup = []
    for repo in configured_repos:
        repo_records = [record for record in records if record["repo_full_name"] == repo["full_name"]]
        repo_prs = collect_unique_prs(repo_records)
        scopes = sorted({scope for record in repo_records for scope in record["top_scopes"]})
        rollup.append(
            {
                "repo": repo["full_name"],
                "label": repo["label"],
                "default_branch": repo["default_branch"],
                "authors": repo["filters"]["authors"],
                "include_paths": repo["filters"]["include_paths"],
                "exclude_paths": repo["filters"]["exclude_paths"],
                "exclude_merge_commits": repo["filters"]["exclude_merge_commits"],
                "matched_commit_count": len(repo_records),
                "matched_pr_count": len(repo_prs),
                "scopes": scopes,
            }
        )
    return rollup


def collect_unique_prs(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    unique: dict[str, dict[str, Any]] = {}
    for record in records:
        for pull_request in record["pull_requests"]:
            key = pull_request["html_url"] or f"{record['repo_full_name']}#{pull_request['number'] or pull_request['title']}"
            if key in unique:
                continue
            unique[key] = {
                "repo": record["repo_label"],
                "repo_full_name": record["repo_full_name"],
                "number": pull_request["number"],
                "title": pull_request["title"],
                "body": pull_request["body"],
                "html_url": pull_request["html_url"],
            }
    return list(unique.values())


def build_work_items(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    items = []
    seen = set()
    for record in records:
        titles = [pull_request["title"] for pull_request in record["pull_requests"] if pull_request["title"]] or [record["subject"]]
        for title in titles:
            normalized = title.strip()
            key = f"{record['repo_full_name']}::{normalized.lower()}"
            if not normalized or key in seen:
                continue
            seen.add(key)
            items.append(
                {
                    "repo": record["repo_label"],
                    "title": normalized,
                    "scopes": record["display_scopes"],
                    "evidence": f"{record['repo_label']}@{record['short_sha']}",
                }
            )
            break
    return items[:12]


def build_business_impact(
    records: list[dict[str, Any]],
    repo_rollup: list[dict[str, Any]],
    unique_prs: list[dict[str, Any]],
    scopes: list[str],
) -> list[str]:
    if not records:
        return ["本范围内没有匹配到任何提交，暂时无法生成有效业务影响。"]

    active_repos = [item["label"] for item in repo_rollup if item["matched_commit_count"] > 0]
    impact = [
        f"本周覆盖 {len(active_repos)} 个仓库，共纳入 {len(records)} 个提交，主要涉及 {format_inline_list(scopes[:4]) or '待人工补充'}。",
    ]
    if len(active_repos) > 1:
        impact.append(f"本次汇总横跨 {format_inline_list(active_repos)}，适合做统一项目周报。")
    if unique_prs:
        impact.append(f"其中 {len(unique_prs)} 个工作项已能通过 GitHub PR 标题回溯，评审与交付链路较清晰。")
    else:
        impact.append("当前没有可关联的 GitHub PR，工作项回溯主要依赖 commit 标题。")

    docs_touched = any(any(path.endswith(".md") for path in record["files"]) for record in records)
    tests_touched = any(any("/test" in path or "/tests/" in path for path in record["files"]) for record in records)
    if docs_touched:
        impact.append("本周涉及文档沉淀，说明交付说明或使用方式已有同步更新。")
    if tests_touched:
        impact.append("本周包含测试相关改动，说明验证链路有同步推进。")
    return impact


def build_risks(records: list[dict[str, Any]], linear_keys: list[str], repo_rollup: list[dict[str, Any]]) -> list[str]:
    if not records:
        return ["过滤条件下没有命中提交，请先确认仓库列表、范围、作者和路径配置。"]

    risks = []
    if any(item["matched_commit_count"] == 0 for item in repo_rollup):
        risks.append("部分已配置仓库在本范围内没有命中提交，统一周报前需确认这些仓库是否应保留在本次统计内。")
    if any(not record["pull_requests"] for record in records):
        risks.append("部分提交没有关联 PR，后续回溯上下文时需要更多人工补充。")
    if not linear_keys:
        risks.append("当前 commit/PR 信息里没有识别到 Linear key，项目链路只能做弱关联。")
    code_without_tests = any(
        any(path.endswith((".py", ".ts", ".tsx", ".js", ".cpp", ".h", ".hpp")) for path in record["files"])
        and not any("/test" in path or "/tests/" in path for path in record["files"])
        for record in records
    )
    if code_without_tests:
        risks.append("存在代码改动但本次命中范围内未看到明显测试文件，建议人工确认验证情况。")
    if not risks:
        risks.append("从 commit 与 PR 信息中未识别到明确阻塞项；若存在外部依赖风险，请人工补充。")
    return risks


def build_next_steps(records: list[dict[str, Any]], linear_keys: list[str], repo_rollup: list[dict[str, Any]]) -> list[str]:
    if not records:
        return ["放宽过滤条件或切换范围后重新生成周报。"]

    steps = ["对本周产出补齐人工验收结论，确保周报里的结果能映射到实际交付状态。"]
    if len(repo_rollup) > 1:
        steps.append("确认多仓统一周报是否需要拆分成项目维度附件，避免摘要层级过深。")
    if any(not record["pull_requests"] for record in records):
        steps.append("为缺少关联 PR 的提交补齐评审链路，减少后续周报整理成本。")
    if not linear_keys:
        steps.append("后续提交建议带上 Linear key，便于项目周报自动关联任务。")
    steps.append("下周继续围绕已覆盖范围收敛文档、验证和待审事项。")
    return dedupe_preserve_order(steps)


def dedupe_preserve_order(values: list[str]) -> list[str]:
    seen = set()
    result = []
    for value in values:
        key = value.lower()
        if key in seen:
            continue
        seen.add(key)
        result.append(value)
    return result


def format_inline_list(values: list[str]) -> str:
    if not values:
        return ""
    if len(values) == 1:
        return f"`{values[0]}`"
    return "、".join(f"`{value}`" for value in values)


def format_repo_overview(repo_rollup: list[dict[str, Any]]) -> str:
    labels = [item["label"] for item in repo_rollup]
    if not labels:
        return "未配置"
    if len(labels) == 1:
        return f"`{labels[0]}`"
    return f"{len(labels)} 个（{format_inline_list(labels)}）"


def format_optional_paths(paths: list[str]) -> str:
    return format_inline_list(paths) or "未配置"


def write_outputs(config: dict[str, Any], config_path: Path, dataset: dict[str, Any]) -> Path:
    report_output_dir = config_path.parent / config["report"]["output_dir"]
    output_dir = report_output_dir / dataset["meta"]["range"]["label"]
    output_dir.mkdir(parents=True, exist_ok=True)

    (output_dir / "source-data.json").write_text(json.dumps(dataset, ensure_ascii=False, indent=2), encoding="utf-8")
    (output_dir / "weekly-summary.md").write_text(render_summary(dataset), encoding="utf-8")
    (output_dir / "weekly-report.md").write_text(render_report(dataset), encoding="utf-8")
    return output_dir


def render_summary(dataset: dict[str, Any]) -> str:
    meta = dataset["meta"]
    lines = [
        f"# {meta['range']['label']} 工作总结",
        "",
        f"- 仓库：{format_repo_overview(meta['repository_rollup'])}",
        f"- 范围：{meta['range']['description']}",
        f"- 命中仓库：{meta['matched_repo_count']} / {meta['configured_repo_count']}",
        f"- 命中提交：{meta['matched_commit_count']} 个",
        f"- 关联 PR：{meta['matched_pr_count']} 个",
        "",
        "## 仓库覆盖",
    ]
    lines.extend(render_repo_rollup_lines(meta["repository_rollup"]))
    lines.extend(
        [
            "",
            "## 本周完成",
        ]
    )
    lines.extend(f"- [{item['repo']}] {item['title']}（证据：`{item['evidence']}`）" for item in dataset["work_items"][:5])
    if not dataset["work_items"]:
        lines.append("- 本范围内没有可归纳的工作项。")

    lines.extend(
        [
            "",
            "## 业务影响",
        ]
    )
    lines.extend(f"- {item}" for item in dataset["business_impact"])
    lines.extend(
        [
            "",
            "## 风险/阻塞",
        ]
    )
    lines.extend(f"- {item}" for item in dataset["risks"])
    lines.extend(
        [
            "",
            "## 下周建议",
        ]
    )
    lines.extend(f"- {item}" for item in dataset["next_steps"])
    return "\n".join(lines).rstrip() + "\n"


def render_repo_rollup_lines(repo_rollup: list[dict[str, Any]]) -> list[str]:
    lines = []
    for item in repo_rollup:
        lines.append(
            f"- {item['label']}：{item['matched_commit_count']} 个提交 / {item['matched_pr_count']} 个 PR；作者过滤：{format_inline_list(item['authors']) or '未配置'}；include_paths：{format_optional_paths(item['include_paths'])}"
        )
    if not lines:
        lines.append("- 暂无仓库配置。")
    return lines


def render_report(dataset: dict[str, Any]) -> str:
    meta = dataset["meta"]
    lines = [
        f"# {meta['range']['label']} 周报",
        "",
        "## 范围概览",
        f"- 仓库：{format_repo_overview(meta['repository_rollup'])}",
        f"- 范围：{meta['range']['description']}",
        f"- 命中仓库：{meta['matched_repo_count']} / {meta['configured_repo_count']}",
        f"- 命中提交：{meta['matched_commit_count']} 个",
        f"- 关联 PR：{meta['matched_pr_count']} 个",
        f"- 识别到的 Linear keys：{format_inline_list(meta['matched_linear_keys']) or '无'}",
        "",
        "## 仓库覆盖",
    ]
    lines.extend(render_repo_rollup_lines(meta["repository_rollup"]))
    lines.extend(["", "## 完成事项"])
    lines.extend(
        f"- [{item['repo']}] {item['title']}；覆盖范围：{format_inline_list(item['scopes']) or '待人工补充'}；证据：`{item['evidence']}`"
        for item in dataset["work_items"]
    )
    if not dataset["work_items"]:
        lines.append("- 本范围内没有可归纳的完成事项。")

    lines.extend(["", "## 业务影响"])
    lines.extend(f"- {item}" for item in dataset["business_impact"])
    lines.extend(["", "## 涉及范围"])
    lines.extend(f"- `{scope}`" for scope in meta["scopes"])
    if not meta["scopes"]:
        lines.append("- 暂无范围聚合结果。")
    lines.extend(["", "## 风险/阻塞"])
    lines.extend(f"- {item}" for item in dataset["risks"])
    lines.extend(["", "## 下周建议"])
    lines.extend(f"- {item}" for item in dataset["next_steps"])
    lines.extend(["", "## 证据附录"])

    for record in dataset["commits"]:
        lines.append(
            f"- [{record['repo_label']}] `{record['short_sha']}` {record['subject']} | 作者：{record['author_display']} | 范围：{format_inline_list(record['display_scopes']) or '待人工补充'}"
        )
        if record["pull_requests"]:
            for pull_request in record["pull_requests"]:
                lines.append(f"  - PR：{pull_request['title']} ({pull_request['html_url']})")

    if not dataset["commits"]:
        lines.append("- 没有命中的提交。")

    return "\n".join(lines).rstrip() + "\n"


if __name__ == "__main__":
    raise SystemExit(main())
