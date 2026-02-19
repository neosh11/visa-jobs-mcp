from __future__ import annotations

import json
from pathlib import Path

import pytest

from visa_jobs_mcp import doctor_cli, server, setup_cli


@pytest.fixture(autouse=True)
def _isolate_paths(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(server, "DEFAULT_USER_PREFS_PATH", str(tmp_path / "user_preferences.json"))
    monkeypatch.setattr(server, "DEFAULT_USER_BLOB_PATH", str(tmp_path / "user_memory_blob.json"))
    monkeypatch.setattr(server, "DEFAULT_SEARCH_SESSION_PATH", str(tmp_path / "search_sessions.json"))
    monkeypatch.setattr(server, "DEFAULT_SAVED_JOBS_PATH", str(tmp_path / "saved_jobs.json"))
    monkeypatch.setattr(server, "DEFAULT_IGNORED_JOBS_PATH", str(tmp_path / "ignored_jobs.json"))
    monkeypatch.setattr(server, "DEFAULT_DOL_MANIFEST_PATH", str(tmp_path / "pipeline_manifest.json"))


def test_setup_cli_non_interactive(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        "sys.argv",
        [
            "visa-jobs-setup",
            "--non-interactive",
            "--user-id",
            "alice",
            "--visa-types",
            "h1b,green_card",
            "--days-remaining",
            "30",
            "--work-modes",
            "remote,hybrid",
            "--willing-to-relocate",
            "yes",
        ],
    )

    setup_cli.main()
    out = capsys.readouterr().out
    payload = json.loads(out)
    assert payload["status"] == "ok"
    assert payload["preferences"]["preferred_visa_types"] == ["green_card", "h1b"]
    assert payload["constraints"]["days_remaining"] == 30
    assert payload["constraints"]["work_modes"] == ["hybrid", "remote"]
    assert payload["constraints"]["willing_to_relocate"] is True


def test_doctor_cli_reports_checks(monkeypatch, tmp_path: Path, capsys) -> None:
    dataset = tmp_path / "companies.csv"
    dataset.write_text(
        "company_tier,company_name,h1b,h1b1_chile,h1b1_singapore,e3_australian,green_card\n",
        encoding="utf-8",
    )
    manifest = {
        "run_at_utc": "2026-02-18T00:00:00Z",
        "output_path": str(dataset),
        "rows_written": 0,
    }
    Path(server.DEFAULT_DOL_MANIFEST_PATH).write_text(json.dumps(manifest), encoding="utf-8")
    server.set_user_preferences(user_id="alice", preferred_visa_types=["h1b"])

    monkeypatch.setattr(
        "sys.argv",
        [
            "visa-jobs-doctor",
            "--user-id",
            "alice",
            "--dataset-path",
            str(dataset),
            "--manifest-path",
            str(Path(server.DEFAULT_DOL_MANIFEST_PATH)),
        ],
    )

    doctor_cli.main()
    out = capsys.readouterr().out
    payload = json.loads(out)
    assert "checks" in payload
    check_names = {c["name"] for c in payload["checks"]}
    assert "dataset_exists" in check_names
    assert "manifest_exists" in check_names
    assert "user_ready_for_search" in check_names
