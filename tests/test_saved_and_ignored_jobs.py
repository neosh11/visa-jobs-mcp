from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from visa_jobs_mcp import server


@pytest.fixture(autouse=True)
def _isolated_stores(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(server, "DEFAULT_SAVED_JOBS_PATH", str(tmp_path / "saved_jobs.json"))
    monkeypatch.setattr(server, "DEFAULT_IGNORED_JOBS_PATH", str(tmp_path / "ignored_jobs.json"))
    monkeypatch.setattr(server, "DEFAULT_IGNORED_COMPANIES_PATH", str(tmp_path / "ignored_companies.json"))
    monkeypatch.setattr(server, "DEFAULT_SEARCH_SESSION_PATH", str(tmp_path / "search_sessions.json"))
    monkeypatch.setattr(server, "DEFAULT_SEARCH_RUNS_PATH", str(tmp_path / "search_runs.json"))
    monkeypatch.setattr(server, "DEFAULT_JOB_DB_PATH", str(tmp_path / "job_management.db"))


def _write_dataset(path: Path) -> None:
    pd.DataFrame(
        [
            {
                "company_tier": "dol",
                "company_name": "Acme Inc.",
                "h1b": 5,
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


def test_save_list_delete_saved_jobs_upsert() -> None:
    save1 = server.save_job_for_later(
        user_id="u1",
        job_url="https://example.com/job-1",
        title="SE1",
        company="Acme",
        note="high priority",
    )
    assert save1["action"] == "saved_new"
    assert save1["saved_job"]["id"] == 1

    save2 = server.save_job_for_later(
        user_id="u1",
        job_url="https://example.com/job-1",
        note="updated note",
    )
    assert save2["action"] == "updated_existing"
    assert save2["saved_job"]["id"] == 1
    assert save2["total_saved_jobs"] == 1
    assert save2["saved_job"]["note"] == "updated note"

    listed = server.list_saved_jobs(user_id="u1")
    assert listed["total_saved_jobs"] == 1
    assert listed["jobs"][0]["job_url"] == "https://example.com/job-1"

    deleted = server.delete_saved_job(user_id="u1", saved_job_id=1)
    assert deleted["deleted"] is True
    assert deleted["total_saved_jobs"] == 0


def test_ignore_jobs_filters_search_results(tmp_path: Path, monkeypatch) -> None:
    dataset = tmp_path / "companies.csv"
    _write_dataset(dataset)

    monkeypatch.setattr(server, "_load_user_prefs", lambda path="": {"u1": {"preferred_visa_types": ["h1b"]}})

    jobs_df = pd.DataFrame(
        [
            {
                "title": "SE1",
                "company": "Acme Inc.",
                "location": "New York, NY",
                "site": "linkedin",
                "description": "General role",
                "job_url": "https://example.com/a",
                "date_posted": "2026-02-18",
            },
            {
                "title": "SE2",
                "company": "Acme Inc.",
                "location": "New York, NY",
                "site": "linkedin",
                "description": "General role",
                "job_url": "https://example.com/b",
                "date_posted": "2026-02-18",
            },
        ]
    )
    monkeypatch.setattr(server, "scrape_jobs", lambda **kwargs: jobs_df)
    server._load_company_dataset.cache_clear()

    ignored = server.ignore_job(user_id="u1", job_url="https://example.com/a", reason="already applied")
    assert ignored["action"] == "ignored_new"

    res = server.find_visa_sponsored_jobs(
        location="New York, NY",
        job_title="software engineer",
        user_id="u1",
        dataset_path=str(dataset),
        max_returned=10,
    )

    urls = [job["job_url"] for job in res["jobs"]]
    assert urls == ["https://example.com/b"]
    assert res["stats"]["ignored_filtered_count"] == 1
    assert res["agent_guidance"]["ignore_job_tool"] == "ignore_job"

    ignored_list = server.list_ignored_jobs(user_id="u1")
    assert ignored_list["total_ignored_jobs"] == 1
    assert ignored_list["jobs"][0]["job_url"] == "https://example.com/a"

    unignored = server.unignore_job(user_id="u1", ignored_job_id=1)
    assert unignored["deleted"] is True
    assert unignored["total_ignored_jobs"] == 0


def test_ignore_companies_filters_search_results(tmp_path: Path, monkeypatch) -> None:
    dataset = tmp_path / "companies.csv"
    pd.DataFrame(
        [
            {
                "company_tier": "dol",
                "company_name": "Acme Inc.",
                "h1b": 5,
                "h1b1_chile": 0,
                "h1b1_singapore": 0,
                "e3_australian": 0,
                "green_card": 0,
            },
            {
                "company_tier": "dol",
                "company_name": "Beta Systems",
                "h1b": 2,
                "h1b1_chile": 0,
                "h1b1_singapore": 0,
                "e3_australian": 0,
                "green_card": 0,
            },
        ]
    ).to_csv(dataset, index=False)
    monkeypatch.setattr(server, "_load_user_prefs", lambda path="": {"u1": {"preferred_visa_types": ["h1b"]}})
    monkeypatch.setattr(
        server,
        "scrape_jobs",
        lambda **kwargs: pd.DataFrame(
            [
                {
                    "title": "SE1",
                    "company": "Acme Inc.",
                    "location": "New York, NY",
                    "site": "linkedin",
                    "description": "General role",
                    "job_url": "https://example.com/a",
                    "date_posted": "2026-02-18",
                },
                {
                    "title": "SE2",
                    "company": "Beta Systems",
                    "location": "New York, NY",
                    "site": "linkedin",
                    "description": "General role",
                    "job_url": "https://example.com/b",
                    "date_posted": "2026-02-18",
                },
                {
                    "title": "SE3",
                    "company": "Acme, Inc.",
                    "location": "New York, NY",
                    "site": "linkedin",
                    "description": "General role",
                    "job_url": "https://example.com/c",
                    "date_posted": "2026-02-18",
                },
            ]
        ),
    )
    server._load_company_dataset.cache_clear()

    first = server.find_visa_sponsored_jobs(
        location="New York, NY",
        job_title="software engineer",
        user_id="u1",
        dataset_path=str(dataset),
        max_returned=10,
    )
    assert {job["company"] for job in first["jobs"]} == {"Acme Inc.", "Beta Systems", "Acme, Inc."}

    ignored = server.ignore_company(user_id="u1", result_id=first["jobs"][0]["result_id"], reason="not a fit")
    assert ignored["action"] == "ignored_new"
    assert ignored["ignored_company"]["normalized_company"] == "acme"

    second = server.find_visa_sponsored_jobs(
        location="New York, NY",
        job_title="software engineer",
        user_id="u1",
        dataset_path=str(dataset),
        max_returned=10,
    )
    assert [job["job_url"] for job in second["jobs"]] == ["https://example.com/b"]
    assert second["stats"]["ignored_company_filtered_count"] == 2
    assert second["agent_guidance"]["ignore_company_tool"] == "ignore_company"

    listed = server.list_ignored_companies(user_id="u1")
    assert listed["total_ignored_companies"] == 1
    ignored_company_id = listed["companies"][0]["id"]

    unignored = server.unignore_company(user_id="u1", ignored_company_id=ignored_company_id)
    assert unignored["deleted"] is True
    assert unignored["total_ignored_companies"] == 0
