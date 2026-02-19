from __future__ import annotations

from visa_jobs_mcp import pipeline


def test_default_dataset_path_prefers_env(monkeypatch) -> None:
    monkeypatch.setenv("VISA_COMPANY_DATASET_PATH", "/custom/path.csv")
    assert pipeline.default_dataset_path() == "/custom/path.csv"


def test_default_dataset_path_uses_canonical_default(monkeypatch) -> None:
    monkeypatch.delenv("VISA_COMPANY_DATASET_PATH", raising=False)
    assert pipeline.default_dataset_path() == "data/companies.csv"
