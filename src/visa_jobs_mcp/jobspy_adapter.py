from __future__ import annotations

import sys
from pathlib import Path

VENDORED_JOBSPY_ROOT = Path(__file__).resolve().parents[2] / "third_party" / "jobspy"

# Prefer vendored source so runtime does not depend on upstream repository availability.
if VENDORED_JOBSPY_ROOT.exists():
    sys.path.insert(0, str(VENDORED_JOBSPY_ROOT))
    JOBSPY_SOURCE = "vendored"
else:
    JOBSPY_SOURCE = "installed"

try:
    from jobspy import scrape_jobs
except ImportError as exc:  # pragma: no cover
    raise RuntimeError(
        "JobSpy import failed. Ensure vendored source exists at third_party/jobspy "
        "or install python-jobspy."
    ) from exc

