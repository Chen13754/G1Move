#!/usr/bin/env bash
# Ubuntu only. All downloads, builds, virtualenvs and caches stay in this project.
set -euo pipefail
PROJECT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
SDK_COMMIT=65691c8a8bc53b98d3976dba4dbf9d5d20b2e7f5
DDS_COMMIT=9995905bce6c4cf9f740d6438bbf7fcfd1c83dfd

if [[ "$(uname -s)" != Linux ]]; then
    echo "Real-robot setup requires Ubuntu. Mock mode needs only Python >= 3.10." >&2
    exit 1
fi
for command in git cmake cc c++ make; do
    command -v "$command" >/dev/null || { echo "Required system tool is missing: $command" >&2; exit 1; }
done
if [[ -e "$PROJECT_DIR/.venv" && ! -x "$PROJECT_DIR/.venv/bin/python" ]]; then
    echo "Existing .venv is not a Linux virtual environment. Use a fresh project copy on Ubuntu." >&2
    exit 1
fi

unset PYTHONPATH PYTHONHOME PIP_TARGET PIP_PREFIX PIP_USER PIP_ROOT
mkdir -p "$PROJECT_DIR/.deps" "$PROJECT_DIR/.cache/pip" "$PROJECT_DIR/.cache/uv" "$PROJECT_DIR/.cache/tmp"
export XDG_CACHE_HOME="$PROJECT_DIR/.cache"
export PIP_CACHE_DIR="$PROJECT_DIR/.cache/pip"
export UV_CACHE_DIR="$PROJECT_DIR/.cache/uv"
export TMPDIR="$PROJECT_DIR/.cache/tmp"
export PYTHONNOUSERSITE=1
export PIP_DISABLE_PIP_VERSION_CHECK=1
export PIP_CONFIG_FILE=/dev/null

# Prefer the project/system interpreter over an activated Conda environment.
if [[ -n "${G1MOVE_PYTHON:-}" ]]; then
    SETUP_PYTHON="$G1MOVE_PYTHON"
elif [[ -x "$PROJECT_DIR/.venv/bin/python" ]]; then
    SETUP_PYTHON="$PROJECT_DIR/.venv/bin/python"
elif [[ -x /usr/bin/python3 ]]; then
    SETUP_PYTHON=/usr/bin/python3
else
    SETUP_PYTHON=python3
fi
"$SETUP_PYTHON" -c 'import sys; assert (3, 10) <= sys.version_info[:2] <= (3, 12), "Set G1MOVE_PYTHON to Python 3.10-3.12 for the pinned Unitree dependencies"'

# Bootstrap before downloading/building DDS so Python issues fail early.
if [[ ! -x "$PROJECT_DIR/.venv/bin/python" ]]; then
    if "$SETUP_PYTHON" -c 'import venv, ensurepip' 2>/dev/null; then
        "$SETUP_PYTHON" -m venv "$PROJECT_DIR/.venv"
    elif command -v uv >/dev/null; then
        uv --no-config venv --no-project --python "$SETUP_PYTHON" --no-managed-python --no-python-downloads --seed "$PROJECT_DIR/.venv"
    else
        echo "Selected Python lacks venv/ensurepip, and uv is unavailable. Provide an existing project .venv with pip; no system packages were installed." >&2
        exit 1
    fi
fi
VENV_PYTHON="$PROJECT_DIR/.venv/bin/python"
"$VENV_PYTHON" -c 'import sys; assert (3, 10) <= sys.version_info[:2] <= (3, 12); assert sys.prefix != sys.base_prefix, ".venv must be a virtual environment"'
"$VENV_PYTHON" -m pip --version
export PIP_REQUIRE_VIRTUALENV=true
"$VENV_PYTHON" -m pip install 'pip==25.0.1' 'setuptools==75.8.0' 'wheel==0.45.1'

checkout_source() {
    local url="$1" commit="$2" directory="$3" current
    if [[ ! -d "$directory/.git" ]]; then
        if [[ -e "$directory" ]]; then
            echo "Will not overwrite an existing non-Git directory: $directory" >&2
            return 1
        fi
        git init "$directory"
        git -C "$directory" remote add origin "$url"
    fi
    if [[ "$(git -C "$directory" remote get-url origin)" != "$url" ]]; then
        echo "Unexpected repository at $directory; leaving it unchanged." >&2
        return 1
    fi
    current="$(git -C "$directory" rev-parse --verify HEAD 2>/dev/null || true)"
    if [[ -n "$current" && "$current" != "$commit" ]]; then
        echo "Unexpected source revision in $directory; leaving it unchanged." >&2
        return 1
    fi
    git -C "$directory" diff --quiet
    git -C "$directory" diff --cached --quiet
    if [[ "$current" != "$commit" ]]; then
        git -C "$directory" fetch --depth 1 origin "$commit"
        git -C "$directory" checkout --detach "$commit"
    fi
}

checkout_source https://github.com/eclipse-cyclonedds/cyclonedds.git "$DDS_COMMIT" "$PROJECT_DIR/.deps/cyclonedds"
checkout_source https://github.com/unitreerobotics/unitree_sdk2_python.git "$SDK_COMMIT" "$PROJECT_DIR/.deps/unitree_sdk2_python"

# CycloneDDS 0.10.2 passes the full 256-byte buffer size after advancing the
# destination pointer in its trace-mask formatter. Ubuntu's fortified snprintf
# aborts at domain creation. Keep the pinned checkout pristine and backport the
# remaining-capacity fix into a derived source tree; retain compiler hardening.
"$VENV_PYTHON" - "$PROJECT_DIR" <<'PY_DDS_PATCH'
from pathlib import Path
import shutil
import sys
root = Path(sys.argv[1])
shutil.copytree(root / ".deps/cyclonedds", root / ".deps/cyclonedds-patched",
                dirs_exist_ok=True, ignore=shutil.ignore_patterns(".git"))
PY_DDS_PATCH
git -C "$PROJECT_DIR/.deps/cyclonedds-patched" apply --check "$PROJECT_DIR/scripts/patches/cyclonedds-0.10.2-snprintf.patch"
git -C "$PROJECT_DIR/.deps/cyclonedds-patched" apply "$PROJECT_DIR/scripts/patches/cyclonedds-0.10.2-snprintf.patch"

cmake -S "$PROJECT_DIR/.deps/cyclonedds-patched" -B "$PROJECT_DIR/.deps/cyclonedds-patched-build" \
    -DCMAKE_BUILD_TYPE=Release -DBUILD_EXAMPLES=OFF -DBUILD_TESTING=OFF \
    -DCMAKE_INSTALL_PREFIX="$PROJECT_DIR/.deps/cyclonedds-install"
cmake --build "$PROJECT_DIR/.deps/cyclonedds-patched-build" --parallel 2
cmake --install "$PROJECT_DIR/.deps/cyclonedds-patched-build"

export CYCLONEDDS_HOME="$PROJECT_DIR/.deps/cyclonedds-install"
export LD_LIBRARY_PATH="$CYCLONEDDS_HOME/lib:$CYCLONEDDS_HOME/lib64${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
"$VENV_PYTHON" -m pip install -r "$PROJECT_DIR/requirements-unitree.txt"
"$VENV_PYTHON" "$PROJECT_DIR/scripts/prepare_sdk_local.py" "$PROJECT_DIR"
"$VENV_PYTHON" -m pip install --no-deps --no-build-isolation -e "$PROJECT_DIR/.deps/unitree_sdk2_python-local" -e "$PROJECT_DIR"
"$VENV_PYTHON" -m pip check
"$VENV_PYTHON" -m pip freeze --all > "$PROJECT_DIR/.deps/installed-requirements.txt"
# Import only: do not initialize DDS or issue robot commands during setup.
"$VENV_PYTHON" -c 'from unitree_sdk2py.g1.loco.g1_loco_client import LocoClient; import g1_move; print("SDK imports OK; no robot connection was opened.")'
echo "Setup complete. Start with: bash scripts/run.sh --backend mock --mock-fast move forward 1"
