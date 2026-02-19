#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

PYTHON_BIN="${PYTHON_BIN:-python3}"
VERSION="${VERSION:-$($PYTHON_BIN - <<'PY'
import tomllib
from pathlib import Path

data = tomllib.loads(Path('pyproject.toml').read_text(encoding='utf-8'))
print(data['project']['version'])
PY
)}"

OS_NAME="$(uname -s | tr '[:upper:]' '[:lower:]')"
ARCH="$(uname -m)"
case "$OS_NAME" in
  darwin)
    PLATFORM="macos-${ARCH}"
    ;;
  linux)
    PLATFORM="linux-${ARCH}"
    ;;
  *)
    echo "Unsupported OS: ${OS_NAME}" >&2
    exit 1
    ;;
esac

BUILD_ROOT="$ROOT_DIR/build/pyinstaller"
DIST_ROOT="$ROOT_DIR/dist/bin"
RELEASE_ROOT="$ROOT_DIR/dist/release"

rm -rf "$BUILD_ROOT" "$DIST_ROOT"
mkdir -p "$BUILD_ROOT/wrappers" "$DIST_ROOT" "$RELEASE_ROOT"

"$PYTHON_BIN" -m pip install --upgrade pip
"$PYTHON_BIN" -m pip install -e .
"$PYTHON_BIN" -m pip install pyinstaller

build_entrypoint() {
  local exe_name="$1"
  local module_path="$2"
  local wrapper="$BUILD_ROOT/wrappers/${exe_name}.py"

  cat > "$wrapper" <<PY
from visa_jobs_mcp.${module_path} import main

if __name__ == "__main__":
    main()
PY

  "$PYTHON_BIN" -m PyInstaller \
    --noconfirm \
    --clean \
    --onefile \
    --collect-all visa_jobs_mcp \
    --collect-all jobspy \
    --collect-all tls_client \
    --name "$exe_name" \
    --distpath "$DIST_ROOT" \
    --workpath "$BUILD_ROOT/work-${exe_name}" \
    --specpath "$BUILD_ROOT/spec" \
    "$wrapper"
}

build_entrypoint "visa-jobs-mcp" "server"
build_entrypoint "visa-jobs-pipeline" "pipeline_cli"
build_entrypoint "visa-jobs-setup" "setup_cli"
build_entrypoint "visa-jobs-doctor" "doctor_cli"

ARTIFACT="visa-jobs-mcp-v${VERSION}-${PLATFORM}.tar.gz"
tar -czf "$RELEASE_ROOT/$ARTIFACT" \
  -C "$DIST_ROOT" \
  visa-jobs-mcp visa-jobs-pipeline visa-jobs-setup visa-jobs-doctor
shasum -a 256 "$RELEASE_ROOT/$ARTIFACT" > "$RELEASE_ROOT/$ARTIFACT.sha256"

echo "Built release artifacts:"
ls -lh "$RELEASE_ROOT"
