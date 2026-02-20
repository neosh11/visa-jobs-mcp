#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

GO_BIN="${GO_BIN:-go}"
VERSION="${VERSION:-}"

if [[ -z "${VERSION}" ]]; then
  if git describe --tags --exact-match >/dev/null 2>&1; then
    TAG="$(git describe --tags --exact-match)"
    VERSION="${TAG#v}"
  else
    VERSION="0.0.0-dev"
  fi
fi

HOST_OS="$(uname -s | tr '[:upper:]' '[:lower:]')"
HOST_ARCH="$(uname -m)"

GOOS=""
GOARCH=""
PLATFORM=""
case "${HOST_OS}" in
  darwin)
    GOOS="darwin"
    case "${HOST_ARCH}" in
      arm64)
        GOARCH="arm64"
        PLATFORM="macos-arm64"
        ;;
      x86_64)
        GOARCH="amd64"
        PLATFORM="macos-x86_64"
        ;;
      *)
        echo "Unsupported darwin architecture: ${HOST_ARCH}" >&2
        exit 1
        ;;
    esac
    ;;
  linux)
    GOOS="linux"
    case "${HOST_ARCH}" in
      aarch64|arm64)
        GOARCH="arm64"
        PLATFORM="linux-arm64"
        ;;
      x86_64)
        GOARCH="amd64"
        PLATFORM="linux-x86_64"
        ;;
      *)
        echo "Unsupported linux architecture: ${HOST_ARCH}" >&2
        exit 1
        ;;
    esac
    ;;
  *)
    echo "Unsupported OS: ${HOST_OS}" >&2
    exit 1
    ;;
esac

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

rm -rf "$BUILD_ROOT" "$DIST_ROOT" "$PACKAGE_ROOT" "$RELEASE_ROOT"
mkdir -p "$BUILD_ROOT" "$DIST_ROOT" "$PACKAGE_ROOT/data" "$RELEASE_ROOT"

LDFLAGS="-s -w -X main.version=${VERSION}"
CGO_ENABLED=0 GOOS="${GOOS}" GOARCH="${GOARCH}" \
  "${GO_BIN}" build -trimpath -ldflags "${LDFLAGS}" -o "$DIST_ROOT/visa-jobs-mcp" ./cmd/visa-jobs-mcp

if [[ "${GOOS}" == "$("${GO_BIN}" env GOOS)" && "${GOARCH}" == "$("${GO_BIN}" env GOARCH)" ]]; then
  "$DIST_ROOT/visa-jobs-mcp" --version >/dev/null
fi

cp "$DIST_ROOT/visa-jobs-mcp" "$PACKAGE_ROOT/visa-jobs-mcp"
cp "$DATASET_FILE" "$PACKAGE_ROOT/data/companies.csv"
if [[ -f "$ROOT_DIR/LICENSE" ]]; then
  cp "$ROOT_DIR/LICENSE" "$PACKAGE_ROOT/LICENSE"
fi

ARTIFACT="visa-jobs-mcp-v${VERSION}-${PLATFORM}.tar.gz"
tar -czf "$RELEASE_ROOT/$ARTIFACT" -C "$PACKAGE_ROOT" .

if command -v shasum >/dev/null 2>&1; then
  shasum -a 256 "$RELEASE_ROOT/$ARTIFACT" > "$RELEASE_ROOT/$ARTIFACT.sha256"
else
  sha256sum "$RELEASE_ROOT/$ARTIFACT" > "$RELEASE_ROOT/$ARTIFACT.sha256"
fi

echo "Built release artifacts:"
ls -lh "$RELEASE_ROOT"
