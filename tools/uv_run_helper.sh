#!/usr/bin/env bash
set -euo pipefail

if [ "$#" -lt 1 ]; then
  echo "usage: uv_run_helper.sh <helper.py> [args ...]" >&2
  exit 2
fi

script_dir="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
runtime_dir="$script_dir/uv-runtime"
helper_path="$1"
shift

if ! command -v uv >/dev/null 2>&1; then
  echo "ERROR: uv is required to run ARIS Python helpers." >&2
  exit 127
fi

if [ ! -f "$runtime_dir/pyproject.toml" ] || [ ! -f "$runtime_dir/uv.lock" ]; then
  echo "ERROR: ARIS uv runtime is not locked: $runtime_dir" >&2
  echo "Run: uv lock --project \"$runtime_dir\"" >&2
  exit 2
fi

if [ ! -f "$helper_path" ]; then
  echo "ERROR: ARIS helper not found: $helper_path" >&2
  exit 2
fi

if [ -z "${UV_CACHE_DIR:-}" ]; then
  export UV_CACHE_DIR="$runtime_dir/.uv-cache"
fi

exec uv run --project "$runtime_dir" --frozen python "$helper_path" "$@"
