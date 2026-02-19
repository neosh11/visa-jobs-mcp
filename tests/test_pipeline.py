from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from visa_jobs_mcp import pipeline


def test_discover_latest_dol_disclosure_urls_parses_page(monkeypatch: pytest.MonkeyPatch) -> None:
    html = """
    <html>
      <a href="/sites/dolgov/files/ETA/oflc/pdfs/LCA_Disclosure_Data_FY2026_Q1.xlsx">LCA</a>
      <a href="/sites/dolgov/files/ETA/oflc/pdfs/PERM_Disclosure_Data_FY2026_Q1.xlsx">PERM</a>
      <a href="/sites/dolgov/files/ETA/oflc/pdfs/LCA_Disclosure_Data_FY2025_Q4.xlsx">LCA old</a>
    </html>
    """

    class Resp:
        text = html

        def raise_for_status(self) -> None:
            return None

    monkeypatch.setattr(pipeline.requests, "get", lambda *args, **kwargs: Resp())

    result = pipeline.discover_latest_dol_disclosure_urls("https://www.dol.gov/agencies/eta/foreign-labor/performance")

    assert result["lca_latest_url"].endswith("LCA_Disclosure_Data_FY2026_Q1.xlsx")
    assert result["perm_latest_url"].endswith("PERM_Disclosure_Data_FY2026_Q1.xlsx")


def test_run_dol_pipeline_builds_canonical_csv(tmp_path: Path) -> None:
    lca_path = tmp_path / "lca.csv"
    perm_path = tmp_path / "perm.csv"
    out_path = tmp_path / "out" / "companies.csv"
    manifest_path = tmp_path / "pipeline" / "last_run.json"

    pd.DataFrame(
        {
            "EMPLOYER_NAME": ["Acme Inc.", "Acme Inc.", "Beta LLC"],
            "VISA_CLASS": ["H-1B", "E-3 Australian", "H-1B1 Chile"],
        }
    ).to_csv(lca_path, index=False)

    pd.DataFrame(
        {
            "EMPLOYER_NAME": ["Acme Inc.", "Gamma Corp"],
        }
    ).to_csv(perm_path, index=False)

    result = pipeline.run_dol_pipeline(
        output_path=str(out_path),
        lca_path_or_url=str(lca_path),
        perm_path_or_url=str(perm_path),
        raw_dir=str(tmp_path / "raw"),
        manifest_path=str(manifest_path),
    )

    assert result.rows_written == 3
    assert out_path.exists()
    assert manifest_path.exists()

    out_df = pd.read_csv(out_path)
    assert set(out_df.columns) == {
        "company_tier",
        "company_name",
        "h1b",
        "h1b1_chile",
        "h1b1_singapore",
        "e3_australian",
        "green_card",
        "email_1",
        "email_1_date",
        "contact_1",
        "contact_1_title",
        "contact_1_phone",
        "email_2",
        "email_2_date",
        "contact_2",
        "contact_2_title",
        "contact_2_phone",
        "email_3",
        "email_3_date",
        "contact_3",
        "contact_3_title",
        "contact_3_phone",
    }

    acme = out_df[out_df["company_name"] == "Acme Inc."].iloc[0]
    assert int(acme["h1b"]) == 1
    assert int(acme["e3_australian"]) == 1
    assert int(acme["green_card"]) == 1

    manifest = json.loads(manifest_path.read_text())
    assert manifest["rows_written"] == 3
    assert manifest["lca_employer_col"] == "EMPLOYER_NAME"


def test_run_dol_pipeline_supports_perm_emp_business_name(tmp_path: Path) -> None:
    lca_path = tmp_path / "lca.csv"
    perm_path = tmp_path / "perm.csv"
    out_path = tmp_path / "companies.csv"

    pd.DataFrame(
        {
            "EMPLOYER_NAME": ["Acme Inc."],
            "VISA_CLASS": ["H-1B"],
        }
    ).to_csv(lca_path, index=False)

    pd.DataFrame(
        {
            "EMP_BUSINESS_NAME": ["Beta LLC"],
        }
    ).to_csv(perm_path, index=False)

    result = pipeline.run_dol_pipeline(
        output_path=str(out_path),
        lca_path_or_url=str(lca_path),
        perm_path_or_url=str(perm_path),
        manifest_path=str(tmp_path / "manifest.json"),
    )

    assert result.perm_employer_col == "EMP_BUSINESS_NAME"
    out_df = pd.read_csv(out_path)
    assert "Beta LLC" in set(out_df["company_name"])


def test_run_dol_pipeline_strict_validation_fails_on_empty_output(tmp_path: Path) -> None:
    lca_path = tmp_path / "lca.csv"
    perm_path = tmp_path / "perm.csv"
    out_path = tmp_path / "companies.csv"

    pd.DataFrame({"EMPLOYER_NAME": [""]}).to_csv(lca_path, index=False)
    pd.DataFrame({"EMP_BUSINESS_NAME": [""]}).to_csv(perm_path, index=False)

    with pytest.raises(ValueError, match="Pipeline validation failed"):
        pipeline.run_dol_pipeline(
            output_path=str(out_path),
            lca_path_or_url=str(lca_path),
            perm_path_or_url=str(perm_path),
            manifest_path=str(tmp_path / "manifest.json"),
        )


def test_run_dol_pipeline_non_strict_allows_empty_output(tmp_path: Path) -> None:
    lca_path = tmp_path / "lca.csv"
    perm_path = tmp_path / "perm.csv"
    out_path = tmp_path / "companies.csv"

    pd.DataFrame({"EMPLOYER_NAME": [""]}).to_csv(lca_path, index=False)
    pd.DataFrame({"EMP_BUSINESS_NAME": [""]}).to_csv(perm_path, index=False)

    result = pipeline.run_dol_pipeline(
        output_path=str(out_path),
        lca_path_or_url=str(lca_path),
        perm_path_or_url=str(perm_path),
        manifest_path=str(tmp_path / "manifest.json"),
        strict_validation=False,
    )

    assert result.rows_written == 0
    assert result.quality_summary["validation"]["passed"] is False
    assert "No rows produced" in result.quality_summary["validation"]["errors"]
