from __future__ import annotations

from pathlib import Path

import pandas as pd

from visa_jobs_mcp import server


def _write_dataset(path: Path) -> None:
    pd.DataFrame(
        [
            {
                "company_tier": "dol",
                "company_name": "Acme Inc.",
                "h1b": 3,
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


def test_find_jobs_filters_by_company_and_description(tmp_path: Path, monkeypatch) -> None:
    dataset = tmp_path / "companies.csv"
    _write_dataset(dataset)

    jobs_df = pd.DataFrame(
        [
            {
                "title": "Engineer I",
                "company": "Acme Inc.",
                "location": "Austin, TX",
                "site": "linkedin",
                "description": "Great role with strong mentorship.",
                "job_url": "https://example.com/1",
                "date_posted": "2026-02-18",
            },
            {
                "title": "Engineer II",
                "company": "Unknown Co",
                "location": "Austin, TX",
                "site": "indeed",
                "description": "This role offers visa sponsorship and H-1B support.",
                "job_url": "https://example.com/2",
                "date_posted": "2026-02-17",
            },
            {
                "title": "Engineer III",
                "company": "Acme Inc.",
                "location": "Austin, TX",
                "site": "glassdoor",
                "description": "No visa sponsorship available for this role.",
                "job_url": "https://example.com/3",
                "date_posted": "2026-02-16",
            },
            {
                "title": "Engineer IV",
                "company": "NoMatch LLC",
                "location": "Austin, TX",
                "site": "google",
                "description": "Standard posting text.",
                "job_url": "https://example.com/4",
                "date_posted": "2026-02-16",
            },
        ]
    )

    monkeypatch.setattr(server, "scrape_jobs", lambda **kwargs: jobs_df)
    monkeypatch.setattr(server, "_get_required_user_visa_types", lambda user_id: ["h1b", "green_card"])
    server._load_company_dataset.cache_clear()

    result = server.find_visa_sponsored_jobs(
        location="Austin, TX",
        job_title="software engineer",
        user_id="u1",
        dataset_path=str(dataset),
        results_wanted=20,
        max_returned=20,
    )

    assert result["stats"]["scraped_jobs"] == 4
    assert result["stats"]["accepted_jobs"] == 2
    accepted_urls = {j["job_url"] for j in result["jobs"]}
    assert accepted_urls == {"https://example.com/1", "https://example.com/2"}
    acme_job = [j for j in result["jobs"] if j["job_url"] == "https://example.com/1"][0]
    assert acme_job["employer_contacts"][0]["email"] == "jane@acme.com"


def test_find_jobs_require_description_signal(tmp_path: Path, monkeypatch) -> None:
    dataset = tmp_path / "companies.csv"
    _write_dataset(dataset)

    jobs_df = pd.DataFrame(
        [
            {
                "title": "Engineer I",
                "company": "Acme Inc.",
                "location": "Austin, TX",
                "site": "linkedin",
                "description": "Great role with no visa details.",
                "job_url": "https://example.com/1",
                "date_posted": "2026-02-18",
            },
            {
                "title": "Engineer II",
                "company": "Unknown Co",
                "location": "Austin, TX",
                "site": "indeed",
                "description": "We sponsor H-1B visas.",
                "job_url": "https://example.com/2",
                "date_posted": "2026-02-17",
            },
        ]
    )

    monkeypatch.setattr(server, "scrape_jobs", lambda **kwargs: jobs_df)
    monkeypatch.setattr(server, "_get_required_user_visa_types", lambda user_id: ["h1b", "green_card"])
    server._load_company_dataset.cache_clear()

    result = server.find_visa_sponsored_jobs(
        location="Austin, TX",
        job_title="software engineer",
        user_id="u1",
        dataset_path=str(dataset),
        require_description_signal=True,
    )

    assert result["stats"]["accepted_jobs"] == 1
    assert result["jobs"][0]["job_url"] == "https://example.com/2"


def test_find_jobs_auto_bootstraps_dataset_when_missing(tmp_path: Path, monkeypatch) -> None:
    dataset = tmp_path / "auto" / "companies.csv"
    jobs_df = pd.DataFrame(
        [
            {
                "title": "Engineer I",
                "company": "Acme Inc.",
                "location": "Austin, TX",
                "site": "linkedin",
                "description": "General role",
                "job_url": "https://example.com/1",
                "date_posted": "2026-02-18",
            }
        ]
    )

    def fake_pipeline(output_path: str, performance_url: str, **kwargs) -> None:
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        _write_dataset(Path(output_path))

    monkeypatch.setattr(server, "run_dol_pipeline", fake_pipeline)
    monkeypatch.setattr(server, "scrape_jobs", lambda **kwargs: jobs_df)
    monkeypatch.setattr(server, "_get_required_user_visa_types", lambda user_id: ["h1b", "green_card"])
    server._load_company_dataset.cache_clear()

    result = server.find_visa_sponsored_jobs(
        location="Austin, TX",
        job_title="software engineer",
        user_id="u1",
        dataset_path=str(dataset),
        max_returned=10,
    )

    assert dataset.exists()
    assert result["stats"]["accepted_jobs"] == 1
    assert result["jobs"][0]["job_url"] == "https://example.com/1"
