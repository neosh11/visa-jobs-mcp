#!/usr/bin/env bash
set -euo pipefail

# Refresh vendored JobSpy snapshot from upstream GitHub source archive.
# Keeps provenance in third_party/jobspy/SNAPSHOT_SOURCE.md.

REPO="speedyapply/JobSpy"
REF="HEAD"
TARGET_DIR="third_party/jobspy"
DRY_RUN="false"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --repo)
      REPO="$2"
      shift 2
      ;;
    --ref)
      REF="$2"
      shift 2
      ;;
    --target)
      TARGET_DIR="$2"
      shift 2
      ;;
    --dry-run)
      DRY_RUN="true"
      shift
      ;;
    -h|--help)
      cat <<USAGE
Usage: scripts/refresh_jobspy_snapshot.sh [options]

Options:
  --repo <owner/repo>   Upstream repository (default: speedyapply/JobSpy)
  --ref <ref>           Git ref/sha/tag/branch (default: HEAD)
  --target <dir>        Target vendor directory (default: third_party/jobspy)
  --dry-run             Resolve and print actions without changing files
  -h, --help            Show this help
USAGE
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      exit 1
      ;;
  esac
done

if ! command -v git >/dev/null 2>&1; then
  echo "git is required" >&2
  exit 1
fi
if ! command -v curl >/dev/null 2>&1; then
  echo "curl is required" >&2
  exit 1
fi
if ! command -v tar >/dev/null 2>&1; then
  echo "tar is required" >&2
  exit 1
fi

REMOTE="https://github.com/${REPO}.git"

if [[ "$REF" == "HEAD" ]]; then
  SHA="$(git ls-remote "${REMOTE}" HEAD | awk '{print $1}')"
  REF_NAME="$(git ls-remote --symref "${REMOTE}" HEAD | awk '/^ref:/ {print $2}')"
else
  SHA="$(git ls-remote "${REMOTE}" "${REF}" | awk '{print $1}' | head -n1)"
  REF_NAME="$REF"
fi

if [[ -z "${SHA}" ]]; then
  echo "Failed to resolve ref '${REF}' for ${REPO}" >&2
  exit 1
fi

URL="https://codeload.github.com/${REPO}/tar.gz/${SHA}"
FETCHED_AT="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"

cat <<PLAN
Resolved upstream snapshot:
- repo: ${REPO}
- ref: ${REF_NAME}
- sha: ${SHA}
- archive: ${URL}
- target: ${TARGET_DIR}
PLAN

if [[ "$DRY_RUN" == "true" ]]; then
  exit 0
fi

TMP_ROOT="$(mktemp -d)"
ARCHIVE_PATH="${TMP_ROOT}/snapshot.tar.gz"
EXTRACT_DIR="${TMP_ROOT}/extract"
NEW_DIR="${TMP_ROOT}/new_jobspy"

mkdir -p "${EXTRACT_DIR}"
curl -L "${URL}" -o "${ARCHIVE_PATH}"
tar -xzf "${ARCHIVE_PATH}" -C "${EXTRACT_DIR}"

SRC_DIR="$(find "${EXTRACT_DIR}" -mindepth 1 -maxdepth 1 -type d | head -n1)"
if [[ -z "${SRC_DIR}" ]]; then
  echo "Failed to extract snapshot directory" >&2
  exit 1
fi

mv "${SRC_DIR}" "${NEW_DIR}"

# Ensure target parent exists.
TARGET_PARENT="$(dirname "${TARGET_DIR}")"
mkdir -p "${TARGET_PARENT}"

# Write provenance file in the new snapshot before swapping.
cat > "${NEW_DIR}/SNAPSHOT_SOURCE.md" <<META
# JobSpy Snapshot Provenance

This directory is a vendored snapshot of JobSpy for availability/supply-chain resilience.

- Upstream repository: https://github.com/${REPO}
- Snapshot commit: ${SHA}
- Snapshot ref: ${REF_NAME}
- Fetched at (UTC): ${FETCHED_AT}
- Acquisition method: GitHub source archive via codeload

Notes:
- This snapshot intentionally excludes .git history/metadata.
- Refresh by re-running scripts/refresh_jobspy_snapshot.sh.
META

BACKUP_DIR=""
if [[ -d "${TARGET_DIR}" ]]; then
  BACKUP_DIR="${TARGET_DIR}.bak.${FETCHED_AT//[:]/-}"
  mv "${TARGET_DIR}" "${BACKUP_DIR}"
fi

mv "${NEW_DIR}" "${TARGET_DIR}"

if [[ -n "${BACKUP_DIR}" && -d "${BACKUP_DIR}" ]]; then
  find "${BACKUP_DIR}" -type f -delete || true
  find "${BACKUP_DIR}" -type d -empty -delete || true
fi

# Cleanup temp files.
find "${TMP_ROOT}" -type f -delete || true
find "${TMP_ROOT}" -type d -empty -delete || true

echo "Updated ${TARGET_DIR} to ${SHA}"
