#!/usr/bin/env bash
set -euo pipefail

REPO="${VISA_JOBS_MCP_REPO:-neosh11/visa-jobs-mcp}"
VERSION="${VISA_JOBS_MCP_VERSION:-}"
PREFIX="${VISA_JOBS_MCP_PREFIX:-}"
DOWNLOADER=""

usage() {
  cat <<'USAGE'
Install visa-jobs-mcp from GitHub release assets.

Usage:
  install.sh [--version X.Y.Z|latest|stable] [--prefix /path] [--repo owner/repo]

Env overrides:
  VISA_JOBS_MCP_VERSION
  VISA_JOBS_MCP_PREFIX
  VISA_JOBS_MCP_REPO
USAGE
}

download_file() {
  local url="$1"
  local output="$2"
  if [[ "${DOWNLOADER}" == "curl" ]]; then
    curl -fsSL "${url}" -o "${output}"
  else
    wget -q "${url}" -O "${output}"
  fi
}

download_text() {
  local url="$1"
  local output=""
  if [[ "${DOWNLOADER}" == "curl" ]]; then
    output="$(curl -fsSL "${url}")"
  else
    output="$(wget -q "${url}" -O -)"
  fi
  printf '%s' "${output}"
}

resolve_latest_tag() {
  local response=""
  local tag=""
  response="$(download_text "https://api.github.com/repos/${REPO}/releases/latest")"
  tag="$(printf '%s' "${response}" | sed -n 's/.*"tag_name":[[:space:]]*"\([^"]*\)".*/\1/p' | head -n1)"
  if [[ -z "${tag}" ]]; then
    echo "Failed to determine latest release tag for ${REPO}" >&2
    exit 1
  fi
  printf '%s' "${tag}"
}

resolve_platform() {
  local os=""
  local arch=""
  os="$(uname -s)"
  arch="$(uname -m)"

  case "${os}" in
    Darwin)
      if [[ "${arch}" == "x86_64" ]] && [[ "$(sysctl -n sysctl.proc_translated 2>/dev/null || true)" == "1" ]]; then
        arch="arm64"
      fi
      case "${arch}" in
        arm64) printf '%s' "macos-arm64" ;;
        x86_64) printf '%s' "macos-x86_64" ;;
        *)
          echo "Unsupported macOS architecture: ${arch}" >&2
          exit 1
          ;;
      esac
      ;;
    Linux)
      case "${arch}" in
        x86_64|amd64) printf '%s' "linux-x86_64" ;;
        arm64|aarch64) printf '%s' "linux-arm64" ;;
        *)
          echo "Unsupported Linux architecture: ${arch}" >&2
          exit 1
          ;;
      esac
      ;;
    *)
      echo "Unsupported OS: ${os}" >&2
      exit 1
      ;;
  esac
}

read_expected_sha() {
  local sha_file="$1"
  local expected=""
  expected="$(awk 'NF {print $1; exit}' "${sha_file}")"
  if [[ -z "${expected}" || ! "${expected}" =~ ^[a-f0-9A-F]{64}$ ]]; then
    echo "Invalid checksum file format: ${sha_file}" >&2
    exit 1
  fi
  printf '%s' "${expected}" | tr '[:upper:]' '[:lower:]'
}

compute_sha() {
  local file="$1"
  if command -v sha256sum >/dev/null 2>&1; then
    sha256sum "${file}" | awk '{print $1}'
  elif command -v shasum >/dev/null 2>&1; then
    shasum -a 256 "${file}" | awk '{print $1}'
  else
    echo "sha256sum or shasum is required" >&2
    exit 1
  fi
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --version)
      VERSION="${2:-}"
      shift 2
      ;;
    --prefix)
      PREFIX="${2:-}"
      shift 2
      ;;
    --repo)
      REPO="${2:-}"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage >&2
      exit 1
      ;;
  esac
done

if command -v curl >/dev/null 2>&1; then
  DOWNLOADER="curl"
elif command -v wget >/dev/null 2>&1; then
  DOWNLOADER="wget"
else
  echo "curl or wget is required" >&2
  exit 1
fi

if ! command -v tar >/dev/null 2>&1; then
  echo "tar is required" >&2
  exit 1
fi
if ! command -v install >/dev/null 2>&1; then
  echo "install is required" >&2
  exit 1
fi

if [[ -z "${VERSION}" || "${VERSION}" == "latest" || "${VERSION}" == "stable" ]]; then
  VERSION="$(resolve_latest_tag)"
fi
VERSION="${VERSION#v}"
if [[ ! "${VERSION}" =~ ^[0-9]+\.[0-9]+\.[0-9]+([-.][A-Za-z0-9._-]+)?$ ]]; then
  echo "Invalid version: ${VERSION}" >&2
  exit 1
fi

PLATFORM="$(resolve_platform)"

if [[ -z "${PREFIX}" ]]; then
  if [[ -d "/opt/homebrew/bin" && -w "/opt/homebrew/bin" ]]; then
    PREFIX="/opt/homebrew"
  elif [[ -w "/usr/local/bin" ]]; then
    PREFIX="/usr/local"
  else
    PREFIX="${HOME}/.local"
  fi
fi

ASSET="visa-jobs-mcp-v${VERSION}-${PLATFORM}.tar.gz"
ASSET_URL="https://github.com/${REPO}/releases/download/v${VERSION}/${ASSET}"
SHA_URL="${ASSET_URL}.sha256"

TMP_DIR="$(mktemp -d)"
cleanup() {
  rm -rf "${TMP_DIR}"
}
trap cleanup EXIT

ARCHIVE_PATH="${TMP_DIR}/${ASSET}"
SHA_PATH="${ARCHIVE_PATH}.sha256"

echo "Downloading ${ASSET_URL}"
if ! download_file "${ASSET_URL}" "${ARCHIVE_PATH}"; then
  echo "Failed to download ${ASSET}. Release may not have this platform yet." >&2
  exit 1
fi

echo "Downloading ${SHA_URL}"
if ! download_file "${SHA_URL}" "${SHA_PATH}"; then
  echo "Failed to download checksum file for ${ASSET}." >&2
  exit 1
fi

EXPECTED_SHA="$(read_expected_sha "${SHA_PATH}")"
ACTUAL_SHA="$(compute_sha "${ARCHIVE_PATH}")"
ACTUAL_SHA="$(printf '%s' "${ACTUAL_SHA}" | tr '[:upper:]' '[:lower:]')"
if [[ "${ACTUAL_SHA}" != "${EXPECTED_SHA}" ]]; then
  echo "Checksum verification failed for ${ASSET}." >&2
  echo "Expected: ${EXPECTED_SHA}" >&2
  echo "Actual:   ${ACTUAL_SHA}" >&2
  exit 1
fi

tar -xzf "${ARCHIVE_PATH}" -C "${TMP_DIR}"

PACKAGE_ROOT="${TMP_DIR}"
if [[ ! -f "${PACKAGE_ROOT}/visa-jobs-mcp" && -d "${PACKAGE_ROOT}/visa-jobs-mcp" ]]; then
  PACKAGE_ROOT="${PACKAGE_ROOT}/visa-jobs-mcp"
fi
if [[ ! -f "${PACKAGE_ROOT}/visa-jobs-mcp" ]]; then
  echo "Archive missing visa-jobs-mcp binary." >&2
  exit 1
fi
if [[ ! -f "${PACKAGE_ROOT}/data/companies.csv" ]]; then
  echo "Archive missing data/companies.csv." >&2
  exit 1
fi

BIN_DIR="${PREFIX}/bin"
SHARE_DIR="${PREFIX}/share/visa-jobs-mcp/data"

NEED_SUDO=0
if [[ ! -w "${PREFIX}" ]]; then
  NEED_SUDO=1
fi

run_cmd() {
  if [[ ${NEED_SUDO} -eq 1 ]]; then
    sudo "$@"
  else
    "$@"
  fi
}

run_cmd mkdir -p "${BIN_DIR}" "${SHARE_DIR}"
run_cmd install -m 0755 "${PACKAGE_ROOT}/visa-jobs-mcp" "${BIN_DIR}/visa-jobs-mcp"
run_cmd install -m 0644 "${PACKAGE_ROOT}/data/companies.csv" "${SHARE_DIR}/companies.csv"

echo
echo "Installed visa-jobs-mcp ${VERSION}"
echo "Binary: ${BIN_DIR}/visa-jobs-mcp"
echo "Dataset: ${SHARE_DIR}/companies.csv"
echo
if ! command -v visa-jobs-mcp >/dev/null 2>&1; then
  echo "Add ${BIN_DIR} to PATH, then reopen your shell."
fi
echo "Register in Codex:"
echo "  codex mcp add visa-jobs-mcp --env VISA_JOB_SITES=linkedin -- ${BIN_DIR}/visa-jobs-mcp"
