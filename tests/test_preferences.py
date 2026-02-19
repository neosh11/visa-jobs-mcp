from __future__ import annotations

from pathlib import Path

import pandas as pd

from visa_jobs_mcp import server


def test_set_and_get_user_preferences(monkeypatch) -> None:
    store = {}

    def fake_load(path: str = ""):
        return dict(store)

    def fake_save(data, path: str = ""):
        store.clear()
        store.update(data)

    monkeypatch.setattr(server, "_load_user_prefs", fake_load)
    monkeypatch.setattr(server, "_save_user_prefs", fake_save)

    set_res = server.set_user_preferences(
        user_id="u1",
        preferred_visa_types=["H-1B", "green card"],
    )
    assert set_res["preferences"]["preferred_visa_types"] == ["green_card", "h1b"]

    get_res = server.get_user_preferences("u1")
    assert get_res["preferences"]["preferred_visa_types"] == ["green_card", "h1b"]


def test_find_jobs_applies_saved_visa_preference(tmp_path: Path, monkeypatch) -> None:
    dataset = tmp_path / "companies.csv"
    pd.DataFrame(
        [
            {
                "company_tier": "dol",
                "company_name": "Acme Inc.",
                "h1b": 0,
                "h1b1_chile": 0,
                "h1b1_singapore": 0,
                "e3_australian": 0,
                "green_card": 3,
                "email_1": "a@acme.com",
                "email_1_date": "",
                "contact_1": "A",
                "contact_1_title": "Immigration",
                "contact_1_phone": "111",
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
            },
            {
                "company_tier": "dol",
                "company_name": "Beta Inc.",
                "h1b": 2,
                "h1b1_chile": 0,
                "h1b1_singapore": 0,
                "e3_australian": 0,
                "green_card": 0,
                "email_1": "b@beta.com",
                "email_1_date": "",
                "contact_1": "B",
                "contact_1_title": "Immigration",
                "contact_1_phone": "222",
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
            },
        ]
    ).to_csv(dataset, index=False)

    monkeypatch.setattr(server, "_load_user_prefs", lambda path="": {"u1": {"preferred_visa_types": ["h1b"]}})
    jobs_df = pd.DataFrame(
        [
            {
                "title": "SE1",
                "company": "Acme Inc.",
                "location": "New York, NY",
                "site": "linkedin",
                "description": "General role",
                "job_url": "https://example.com/acme",
                "date_posted": "2026-02-18",
            },
            {
                "title": "SE2",
                "company": "Beta Inc.",
                "location": "New York, NY",
                "site": "linkedin",
                "description": "General role",
                "job_url": "https://example.com/beta",
                "date_posted": "2026-02-18",
            },
        ]
    )
    monkeypatch.setattr(server, "scrape_jobs", lambda **kwargs: jobs_df)
    server._load_company_dataset.cache_clear()

    res = server.find_visa_sponsored_jobs(
        location="New York, NY",
        job_title="software engineer",
        dataset_path=str(dataset),
        user_id="u1",
    )

    urls = [j["job_url"] for j in res["jobs"]]
    assert urls == ["https://example.com/beta"]
    assert res["jobs"][0]["matches_user_visa_preferences"] is True
    assert "H-1B" in res["jobs"][0]["visas_sponsored"]


def test_find_jobs_errors_when_user_preferences_missing(tmp_path: Path, monkeypatch) -> None:
    dataset = tmp_path / "companies.csv"
    pd.DataFrame(
        [
            {
                "company_tier": "dol",
                "company_name": "Acme Inc.",
                "h1b": 1,
                "h1b1_chile": 0,
                "h1b1_singapore": 0,
                "e3_australian": 0,
                "green_card": 0,
                "email_1": "",
                "email_1_date": "",
                "contact_1": "",
                "contact_1_title": "",
                "contact_1_phone": "",
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
    ).to_csv(dataset, index=False)
    monkeypatch.setattr(server, "_load_user_prefs", lambda path="": {})
    monkeypatch.setattr(server, "scrape_jobs", lambda **kwargs: pd.DataFrame([]))

    try:
        server.find_visa_sponsored_jobs(
            location="New York, NY",
            job_title="software engineer",
            user_id="missing",
            dataset_path=str(dataset),
        )
        assert False, "Expected ValueError when preferences are missing"
    except ValueError as e:
        assert "set_user_preferences" in str(e)
