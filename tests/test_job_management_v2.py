from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from visa_jobs_mcp import server


@pytest.fixture(autouse=True)
def _isolated_paths(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(server, "DEFAULT_USER_PREFS_PATH", str(tmp_path / "user_preferences.json"))
    monkeypatch.setattr(server, "DEFAULT_USER_BLOB_PATH", str(tmp_path / "user_memory_blob.json"))
    monkeypatch.setattr(server, "DEFAULT_SEARCH_SESSION_PATH", str(tmp_path / "search_sessions.json"))
    monkeypatch.setattr(server, "DEFAULT_SAVED_JOBS_PATH", str(tmp_path / "saved_jobs.json"))
    monkeypatch.setattr(server, "DEFAULT_IGNORED_JOBS_PATH", str(tmp_path / "ignored_jobs.json"))
    monkeypatch.setattr(server, "DEFAULT_DOL_MANIFEST_PATH", str(tmp_path / "pipeline_manifest.json"))
    monkeypatch.setattr(server, "DEFAULT_JOB_DB_PATH", str(tmp_path / "job_management.db"))
    server._JOB_DB_READY_PATHS.clear()


def _write_dataset(path: Path) -> None:
    pd.DataFrame(
        [
            {
                "company_tier": "dol",
                "company_name": "Acme Inc.",
                "h1b": 6,
                "h1b1_chile": 0,
                "h1b1_singapore": 0,
                "e3_australian": 1,
                "green_card": 2,
                "email_1": "jane@acme.com",
                "email_1_date": "",
                "contact_1": "Jane Doe",
                "contact_1_title": "Immigration Manager",
                "contact_1_phone": "555-123-4567",
                "email_2": "",
                "email_2_date": "",
                "contact_2": "",
                "contact_2_title": "",
                "contact_2_phone": "",
                "email_3": "",
                "email_3_date": "",
                "contact_3": "",
                "contact_3_title": "",
                "contact_3_phone": "",
            }
        ]
    ).to_csv(path, index=False)


def test_mark_job_applied_and_stage_listing(tmp_path: Path, monkeypatch) -> None:
    dataset = tmp_path / "companies.csv"
    _write_dataset(dataset)
    server.set_user_preferences(user_id="u1", preferred_visa_types=["h1b"])
    server._load_company_dataset.cache_clear()

    monkeypatch.setattr(
        server,
        "scrape_jobs",
        lambda **kwargs: pd.DataFrame(
            [
                {
                    "title": "Software Engineer",
                    "company": "Acme Inc.",
                    "location": "New York, NY",
                    "site": "linkedin",
                    "description": "General role text",
                    "job_url": "https://example.com/applied-1",
                    "date_posted": "2026-02-19",
                }
            ]
        ),
    )

    search = server.find_visa_sponsored_jobs(
        location="New York, NY",
        job_title="software engineer",
        user_id="u1",
        dataset_path=str(dataset),
    )
    result_id = search["jobs"][0]["result_id"]

    marked = server.mark_job_applied(user_id="u1", result_id=result_id, note="Submitted today")
    assert marked["job"]["stage"] == "applied"
    assert marked["job"]["applied_at_utc"]

    listed = server.list_jobs_by_stage(user_id="u1", stage="applied")
    assert listed["total_jobs"] == 1
    assert listed["jobs"][0]["job_url"] == "https://example.com/applied-1"

    summary = server.get_job_pipeline_summary(user_id="u1")
    assert summary["stage_counts"]["applied"] == 1


def test_update_stage_and_add_job_note(tmp_path: Path) -> None:
    server.save_job_for_later(
        user_id="u1",
        job_url="https://example.com/job-2",
        title="SE2",
        company="Acme",
    )

    updated = server.update_job_stage(
        user_id="u1",
        job_url="https://example.com/job-2",
        stage="interview",
        note="Recruiter screen scheduled",
    )
    assert updated["job"]["stage"] == "interview"

    noted = server.add_job_note(
        user_id="u1",
        job_url="https://example.com/job-2",
        note="Round 1 complete",
    )
    assert "Round 1 complete" in noted["job"]["note"]

    stage_jobs = server.list_jobs_by_stage(user_id="u1", stage="interview")
    assert stage_jobs["total_jobs"] == 1

    events = server.list_recent_job_events(user_id="u1", limit=10)
    reasons = [event["reason"] for event in events["events"]]
    assert "update_job_stage" in reasons
    assert "note_added" in reasons


def test_json_migration_into_job_management_db(tmp_path: Path) -> None:
    saved_path = Path(server.DEFAULT_SAVED_JOBS_PATH)
    ignored_path = Path(server.DEFAULT_IGNORED_JOBS_PATH)
    saved_path.parent.mkdir(parents=True, exist_ok=True)
    ignored_path.parent.mkdir(parents=True, exist_ok=True)

    saved_data = {
        "users": {
            "u1": {
                "next_id": 2,
                "jobs": [
                    {
                        "id": 1,
                        "job_url": "https://example.com/migrate-saved",
                        "title": "SE",
                        "company": "Acme",
                        "location": "NY",
                        "site": "linkedin",
                        "note": "saved note",
                        "source_session_id": "",
                        "saved_at_utc": "2026-02-19T00:00:00Z",
                        "updated_at_utc": "2026-02-19T00:00:00Z",
                    }
                ],
            }
        }
    }
    ignored_data = {
        "users": {
            "u1": {
                "next_id": 2,
                "jobs": [
                    {
                        "id": 1,
                        "job_url": "https://example.com/migrate-ignored",
                        "reason": "not relevant",
                        "source": "",
                        "ignored_at_utc": "2026-02-19T00:00:00Z",
                        "updated_at_utc": "2026-02-19T00:00:00Z",
                    }
                ],
            }
        }
    }
    saved_path.write_text(json.dumps(saved_data), encoding="utf-8")
    ignored_path.write_text(json.dumps(ignored_data), encoding="utf-8")

    summary = server.get_job_pipeline_summary(user_id="u1")
    assert summary["stage_counts"]["saved"] == 1
    assert summary["stage_counts"]["ignored"] == 1


def test_delete_user_data_clears_job_management_records() -> None:
    server.save_job_for_later(user_id="u1", job_url="https://example.com/delete-1", title="SE")
    server.mark_job_applied(user_id="u1", job_url="https://example.com/delete-1", note="applied")

    exported = server.export_user_data(user_id="u1")
    assert exported["counts"]["job_management_jobs"] == 1
    assert exported["counts"]["job_management_applications"] == 1

    deleted = server.delete_user_data(user_id="u1", confirm=True)
    assert deleted["deleted"]["job_management_jobs"] == 1
    assert deleted["deleted"]["job_management_applications"] == 1

    summary = server.get_job_pipeline_summary(user_id="u1")
    assert summary["total_tracked_jobs"] == 0
