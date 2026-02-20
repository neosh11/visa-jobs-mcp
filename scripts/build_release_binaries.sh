#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

GO_BIN="${GO_BIN:-go}"
VERSION="${VERSION:-}"
TARGET_GOOS="${TARGET_GOOS:-}"
TARGET_GOARCH="${TARGET_GOARCH:-}"
TARGET_PLATFORM="${TARGET_PLATFORM:-}"

if [[ -z "${VERSION}" ]]; then
  if git describe --tags --exact-match >/dev/null 2>&1; then
    TAG="$(git describe --tags --exact-match)"
    VERSION="${TAG#v}"
  else
    VERSION="0.0.0-dev"
  fi
fi

host_to_goarch() {
  local host_arch="$1"
  case "${host_arch}" in
    x86_64|amd64)
      echo "amd64"
      ;;
    arm64|aarch64)
      echo "arm64"
      ;;
    *)
      echo ""
      ;;
  esac
}

infer_platform_name() {
  local goos="$1"
  local goarch="$2"
  case "${goos}/${goarch}" in
    darwin/arm64)
      echo "macos-arm64"
      ;;
    darwin/amd64)
      echo "macos-x86_64"
      ;;
    linux/arm64)
      echo "linux-arm64"
      ;;
    linux/amd64)
      echo "linux-x86_64"
      ;;
    windows/arm64)
      echo "windows-arm64"
      ;;
    windows/amd64)
      echo "windows-x86_64"
      ;;
    *)
      echo "${goos}-${goarch}"
      ;;
  esac
}

if [[ -z "${TARGET_GOOS}" || -z "${TARGET_GOARCH}" ]]; then
  HOST_OS="$(uname -s | tr '[:upper:]' '[:lower:]')"
  HOST_ARCH="$(uname -m)"
  HOST_GOARCH="$(host_to_goarch "${HOST_ARCH}")"
  if [[ -z "${HOST_GOARCH}" ]]; then
    echo "Unsupported host architecture: ${HOST_ARCH}" >&2
    exit 1
  fi
  case "${HOST_OS}" in
    darwin*)
      TARGET_GOOS="darwin"
      TARGET_GOARCH="${HOST_GOARCH}"
      ;;
    linux*)
      TARGET_GOOS="linux"
      TARGET_GOARCH="${HOST_GOARCH}"
      ;;
    mingw*|msys*|cygwin*)
      TARGET_GOOS="windows"
      TARGET_GOARCH="${HOST_GOARCH}"
      ;;
    *)
      echo "Unsupported host OS: ${HOST_OS}" >&2
      exit 1
      ;;
  esac
fi

if [[ -z "${TARGET_PLATFORM}" ]]; then
  TARGET_PLATFORM="$(infer_platform_name "${TARGET_GOOS}" "${TARGET_GOARCH}")"
fi

DATASET_FILE="$ROOT_DIR/data/companies.csv"
if [[ ! -f "${DATASET_FILE}" ]]; then
  echo "Missing dataset file: ${DATASET_FILE}" >&2
  echo "Run the pipeline first to produce data/companies.csv." >&2
  exit 1
fi

BUILD_ROOT="$ROOT_DIR/build/go"
DIST_ROOT="$ROOT_DIR/dist/bin"
PACKAGE_ROOT="$ROOT_DIR/dist/package"
RELEASE_ROOT="$ROOT_DIR/dist/release"
BIN_NAME="visa-jobs-mcp"
if [[ "${TARGET_GOOS}" == "windows" ]]; then
  BIN_NAME="visa-jobs-mcp.exe"
fi

write_sha256() {
  local input_file="$1"
  local output_file="$2"
  if command -v shasum >/dev/null 2>&1; then
    shasum -a 256 "${input_file}" > "${output_file}"
  else
    sha256sum "${input_file}" > "${output_file}"
  fi
}

rm -rf "$BUILD_ROOT" "$DIST_ROOT" "$PACKAGE_ROOT" "$RELEASE_ROOT"
mkdir -p "$BUILD_ROOT" "$DIST_ROOT" "$PACKAGE_ROOT/data" "$RELEASE_ROOT"

LDFLAGS="-s -w -X main.version=${VERSION} -X github.com/neosh11/visa-jobs-mcp/internal/mcp.Version=${VERSION}"
CGO_ENABLED=0 GOOS="${TARGET_GOOS}" GOARCH="${TARGET_GOARCH}" \
  "${GO_BIN}" build -trimpath -ldflags "${LDFLAGS}" -o "$DIST_ROOT/${BIN_NAME}" ./cmd/visa-jobs-mcp

if [[ "${TARGET_GOOS}" == "$("${GO_BIN}" env GOOS)" && "${TARGET_GOARCH}" == "$("${GO_BIN}" env GOARCH)" ]]; then
  "$DIST_ROOT/${BIN_NAME}" --version >/dev/null
fi

cp "$DIST_ROOT/${BIN_NAME}" "$PACKAGE_ROOT/${BIN_NAME}"
cp "$DATASET_FILE" "$PACKAGE_ROOT/data/companies.csv"
if [[ -f "$ROOT_DIR/LICENSE" ]]; then
  cp "$ROOT_DIR/LICENSE" "$PACKAGE_ROOT/LICENSE"
fi

ARTIFACT="visa-jobs-mcp-v${VERSION}-${TARGET_PLATFORM}.tar.gz"
tar -czf "$RELEASE_ROOT/$ARTIFACT" -C "$PACKAGE_ROOT" .
write_sha256 "$RELEASE_ROOT/$ARTIFACT" "$RELEASE_ROOT/$ARTIFACT.sha256"

if [[ "${TARGET_GOOS}" == "windows" ]]; then
  ZIP_ARTIFACT="visa-jobs-mcp-v${VERSION}-${TARGET_PLATFORM}.zip"
  python3 - <<'PY' "$PACKAGE_ROOT" "$RELEASE_ROOT/$ZIP_ARTIFACT"
import pathlib
import sys
import zipfile

package_root = pathlib.Path(sys.argv[1])
zip_path = pathlib.Path(sys.argv[2])

with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
    for path in package_root.rglob("*"):
        if path.is_file():
            zf.write(path, path.relative_to(package_root))
PY
  write_sha256 "$RELEASE_ROOT/$ZIP_ARTIFACT" "$RELEASE_ROOT/$ZIP_ARTIFACT.sha256"
fi

echo "Built release artifacts:"
ls -lh "$RELEASE_ROOT"
