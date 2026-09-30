#!/usr/bin/env bash
set -euo pipefail
PROJECT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
unset PYTHONPATH PYTHONHOME
mkdir -p "$PROJECT_DIR/.cache/tmp"
export XDG_CACHE_HOME="$PROJECT_DIR/.cache"
export PIP_CACHE_DIR="$PROJECT_DIR/.cache/pip"
export UV_CACHE_DIR="$PROJECT_DIR/.cache/uv"
export TMPDIR="$PROJECT_DIR/.cache/tmp"
if [[ ! -x "$PROJECT_DIR/.venv/bin/python" ]]; then
    echo "Create a project .venv first; see README.md." >&2
    exit 1
fi
if [[ -d "$PROJECT_DIR/.deps/cyclonedds-install" ]]; then
    export CYCLONEDDS_HOME="$PROJECT_DIR/.deps/cyclonedds-install"
    export LD_LIBRARY_PATH="$CYCLONEDDS_HOME/lib:$CYCLONEDDS_HOME/lib64${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
fi
export PYTHONNOUSERSITE=1
cd -- "$PROJECT_DIR"
exec "$PROJECT_DIR/.venv/bin/python" -m g1_move "$@"
