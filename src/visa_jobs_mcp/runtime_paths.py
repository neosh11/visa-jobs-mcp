from __future__ import annotations

import os
import sys
from pathlib import Path

DEFAULT_CANONICAL_DATASET_PATH = "data/companies.csv"


def default_dataset_path() -> str:
    """Default writable dataset path for source/dev workflows."""
    explicit = os.getenv("VISA_COMPANY_DATASET_PATH", "").strip()
    if explicit:
        return explicit
    return DEFAULT_CANONICAL_DATASET_PATH


def _candidate_runtime_dataset_paths(relative_path: str = DEFAULT_CANONICAL_DATASET_PATH) -> list[Path]:
    candidates: list[Path] = []

    # Current working directory (source/dev usage).
    candidates.append(Path(relative_path))

    # Repository/package-root relative fallback when running from source tree.
    candidates.append(Path(__file__).resolve().parents[2] / relative_path)

    # PyInstaller onefile extraction root.
    meipass = getattr(sys, "_MEIPASS", "")
    if meipass:
        candidates.append(Path(meipass) / relative_path)

    # PyInstaller onedir executable sibling path.
    executable = getattr(sys, "executable", "")
    if executable:
        candidates.append(Path(executable).resolve().parent / relative_path)

    deduped: list[Path] = []
    seen: set[str] = set()
    for path in candidates:
        key = str(path.resolve()) if path.is_absolute() else str(path)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(path)
    return deduped


def resolve_runtime_dataset_path(relative_path: str = DEFAULT_CANONICAL_DATASET_PATH) -> str:
    """Resolve readable dataset path, preferring explicit env then bundled copies."""
    explicit = os.getenv("VISA_COMPANY_DATASET_PATH", "").strip()
    if explicit:
        return explicit

    for candidate in _candidate_runtime_dataset_paths(relative_path):
        if candidate.exists():
            return str(candidate)

    return relative_path
