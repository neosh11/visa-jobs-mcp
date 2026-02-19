#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

PYTHON_BIN="${PYTHON_BIN:-python3}"
VERSION="${1:-$("$PYTHON_BIN" - <<'PY'
import tomllib
from pathlib import Path

data = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))
print(data["project"]["version"])
PY
)}"
TAG="v${VERSION}"
if ! git diff --quiet || ! git diff --cached --quiet; then
  echo "Working tree is not clean. Commit/stash changes before tagging." >&2
  exit 1
fi

if git rev-parse --verify --quiet "$TAG" >/dev/null; then
  echo "Tag ${TAG} already exists." >&2
  exit 1
fi

if [ -x ".venv/bin/python" ]; then
  .venv/bin/python -m pytest -q
else
  python3 -m pytest -q
fi

git push origin main
git tag -a "$TAG" -m "Release ${TAG}"
git push origin "$TAG"

echo "Pushed ${TAG}."
echo "GitHub Actions will build/upload release binaries from .github/workflows/build-release-binaries.yml"
