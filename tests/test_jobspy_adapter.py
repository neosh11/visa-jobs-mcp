from __future__ import annotations

from visa_jobs_mcp import jobspy_adapter


def test_jobspy_adapter_prefers_vendored_when_available() -> None:
    if jobspy_adapter.VENDORED_JOBSPY_ROOT.exists():
        assert jobspy_adapter.JOBSPY_SOURCE == "vendored"
    else:
        assert jobspy_adapter.JOBSPY_SOURCE == "installed"
