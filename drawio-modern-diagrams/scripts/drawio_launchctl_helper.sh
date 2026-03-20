#!/bin/bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage:
  drawio_launchctl_helper.sh probe [--timeout <seconds>]
  drawio_launchctl_helper.sh export --drawio-bin <path> --input <file> --out-dir <dir> --format <fmt> [--timeout <seconds>]
EOF
}

print_kv() {
  local key="$1"
  local value="$2"
  printf '%s=%s\n' "$key" "$value"
}

flatten_file() {
  local file_path="$1"
  if [[ ! -f "$file_path" ]]; then
    return 0
  fi
  tr '\n' ' ' <"$file_path" | sed 's/[[:space:]]\+/ /g; s/^ //; s/ $//'
}

mtime_seconds() {
  local target="$1"
  if stat -f '%m' "$target" >/dev/null 2>&1; then
    stat -f '%m' "$target"
  else
    stat -c '%Y' "$target"
  fi
}

submit_job() {
  local label="$1"
  local stdout_path="$2"
  local stderr_path="$3"
  shift 3
  /bin/launchctl submit -l "$label" -o "$stdout_path" -e "$stderr_path" -- "$@"
}

run_probe() {
  local timeout=5
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --timeout)
        timeout="$2"
        shift 2
        ;;
      *)
        usage
        return 2
        ;;
    esac
  done

  if [[ "$(uname -s)" != "Darwin" ]]; then
    print_kv status error
    print_kv reason "launchctl helper is only available on macOS"
    return 1
  fi

  if ! command -v launchctl >/dev/null 2>&1; then
    print_kv status error
    print_kv reason "launchctl command not found"
    return 1
  fi

  local probe_dir
  probe_dir="$(mktemp -d -t drawio-helper)"
  local stdout_path="$probe_dir/stdout.log"
  local stderr_path="$probe_dir/stderr.log"
  local label="ai.openclaw.drawio.probe.$RANDOM$RANDOM"

  if ! submit_job "$label" "$stdout_path" "$stderr_path" /bin/echo helper-ready; then
    print_kv status error
    print_kv stdout_log "$stdout_path"
    print_kv stderr_log "$stderr_path"
    print_kv reason "launchctl submit failed"
    return 1
  fi

  local deadline=$((SECONDS + timeout))
  while (( SECONDS <= deadline )); do
    if [[ -f "$stdout_path" ]] && grep -q 'helper-ready' "$stdout_path"; then
      print_kv status ok
      print_kv executor launchctl
      print_kv stdout_log "$stdout_path"
      print_kv stderr_log "$stderr_path"
      print_kv reason "launchctl helper is available"
      return 0
    fi
    sleep 1
  done

  local reason="launchctl probe timed out"
  if [[ -f "$stderr_path" ]] && [[ -s "$stderr_path" ]]; then
    reason="$(flatten_file "$stderr_path")"
  fi

  print_kv status error
  print_kv executor launchctl
  print_kv stdout_log "$stdout_path"
  print_kv stderr_log "$stderr_path"
  print_kv reason "$reason"
  return 1
}

run_export() {
  local drawio_bin=""
  local input=""
  local out_dir=""
  local format=""
  local timeout=30

  while [[ $# -gt 0 ]]; do
    case "$1" in
      --drawio-bin)
        drawio_bin="$2"
        shift 2
        ;;
      --input)
        input="$2"
        shift 2
        ;;
      --out-dir)
        out_dir="$2"
        shift 2
        ;;
      --format)
        format="$2"
        shift 2
        ;;
      --timeout)
        timeout="$2"
        shift 2
        ;;
      *)
        usage
        return 2
        ;;
    esac
  done

  if [[ "$(uname -s)" != "Darwin" ]]; then
    print_kv status error
    print_kv reason "launchctl helper is only available on macOS"
    return 1
  fi

  if [[ -z "$drawio_bin" || -z "$input" || -z "$out_dir" || -z "$format" ]]; then
    usage
    return 2
  fi

  if [[ ! -x "$drawio_bin" ]]; then
    print_kv status error
    print_kv reason "draw.io binary is not executable: $drawio_bin"
    return 1
  fi

  if [[ ! -f "$input" ]]; then
    print_kv status error
    print_kv reason "input file not found: $input"
    return 1
  fi

  mkdir -p "$out_dir"

  local stem
  stem="$(basename "$input")"
  stem="${stem%.*}"
  local output_path="$out_dir/$stem.$format"
  local stdout_path="$out_dir/.drawio-helper-$stem-$format.stdout"
  local stderr_path="$out_dir/.drawio-helper-$stem-$format.stderr"
  local label="ai.openclaw.drawio.export.$RANDOM$RANDOM"
  local input_mtime
  input_mtime="$(mtime_seconds "$input")"

  if ! submit_job "$label" "$stdout_path" "$stderr_path" "$drawio_bin" -x -f "$format" -o "$out_dir" "$input"; then
    print_kv status error
    print_kv output "$output_path"
    print_kv stdout_log "$stdout_path"
    print_kv stderr_log "$stderr_path"
    print_kv reason "launchctl submit failed"
    return 1
  fi

  local deadline=$((SECONDS + timeout))
  while (( SECONDS <= deadline )); do
    if [[ -f "$output_path" ]]; then
      local output_mtime
      output_mtime="$(mtime_seconds "$output_path")"
      if (( output_mtime >= input_mtime )); then
        print_kv status ok
        print_kv executor launchctl
        print_kv output "$output_path"
        print_kv stdout_log "$stdout_path"
        print_kv stderr_log "$stderr_path"
        print_kv reason "export completed"
        return 0
      fi
    fi
    sleep 1
  done

  local reason="draw.io export did not finish before timeout"
  if [[ -f "$stderr_path" ]] && [[ -s "$stderr_path" ]]; then
    reason="$(flatten_file "$stderr_path")"
  elif [[ -f "$stdout_path" ]] && [[ -s "$stdout_path" ]]; then
    reason="$(flatten_file "$stdout_path")"
  fi

  print_kv status error
  print_kv executor launchctl
  print_kv output "$output_path"
  print_kv stdout_log "$stdout_path"
  print_kv stderr_log "$stderr_path"
  print_kv reason "$reason"
  return 1
}

subcommand="${1:-}"
if [[ -z "$subcommand" ]]; then
  usage
  exit 2
fi
shift

case "$subcommand" in
  probe)
    run_probe "$@"
    ;;
  export)
    run_export "$@"
    ;;
  *)
    usage
    exit 2
    ;;
esac
