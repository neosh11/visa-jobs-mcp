from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from visa_jobs_mcp import server


@pytest.fixture(autouse=True)
def _isolated_search_session_store(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(server, "DEFAULT_USER_BLOB_PATH", str(tmp_path / "user_memory_blob.json"))
    monkeypatch.setattr(server, "DEFAULT_USER_PREFS_PATH", str(tmp_path / "user_preferences.json"))
    monkeypatch.setattr(server, "DEFAULT_DOL_MANIFEST_PATH", str(tmp_path / "pipeline_manifest.json"))
    monkeypatch.setattr(server, "DEFAULT_SEARCH_SESSION_PATH", str(tmp_path / "search_sessions.json"))
    monkeypatch.setattr(server, "DEFAULT_SAVED_JOBS_PATH", str(tmp_path / "saved_jobs.json"))
    monkeypatch.setattr(server, "DEFAULT_IGNORED_JOBS_PATH", str(tmp_path / "ignored_jobs.json"))
    monkeypatch.setattr(server, "DEFAULT_JOB_DB_PATH", str(tmp_path / "job_management.db"))


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
    assert acme_job["confidence_score"] > 0.5
    assert any("Matches requested visa type" in reason for reason in acme_job["eligibility_reasons"])


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


def test_get_mcp_capabilities_exposes_agent_contract() -> None:
    caps = server.get_mcp_capabilities()
    assert caps["capabilities_schema_version"] == "1.1.0"
    assert caps["confidence_model_version"] == server.CONFIDENCE_MODEL_VERSION
    assert caps["design_decisions"]["llm_runtime_inside_mcp"] is False
    assert caps["design_decisions"]["llm_api_keys_required_by_mcp"] is False
    assert caps["design_decisions"]["free_forever"] is True
    assert caps["design_decisions"]["license"] == "MIT"
    assert caps["design_decisions"]["data_not_shared_or_sold"] is True
    assert caps["design_decisions"]["no_fake_reviews_or_bot_marketing"] is True
    assert caps["design_decisions"]["first_class_job_management"] is True
    assert caps["design_decisions"]["strict_user_visa_match"] is True
    assert caps["design_decisions"]["rate_limit_backoff_retries"] is True
    assert caps["defaults"]["search_session_ttl_seconds"] == 21600
    assert caps["defaults"]["max_search_sessions_per_user"] == server.DEFAULT_MAX_SEARCH_SESSIONS_PER_USER
    assert caps["defaults"]["rate_limit_retry_window_seconds"] == 180
    tool_names = {t["name"] for t in caps["tools"]}
    assert "find_visa_sponsored_jobs" in tool_names
    assert "get_user_readiness" in tool_names
    assert "save_job_for_later" in tool_names
    assert "ignore_job" in tool_names
    assert "set_user_constraints" in tool_names
    assert "clear_search_session" in tool_names
    assert "export_user_data" in tool_names
    assert "delete_user_data" in tool_names
    assert "mark_job_applied" in tool_names
    assert "update_job_stage" in tool_names
    assert "list_jobs_by_stage" in tool_names
    assert "add_job_note" in tool_names
    assert "list_recent_job_events" in tool_names
    assert "get_job_pipeline_summary" in tool_names
    assert "get_best_contact_strategy" in tool_names
    assert "generate_outreach_message" in tool_names
    assert "get_mcp_capabilities" not in tool_names  # list is intentional core user-facing tools
    assert "pagination_contract" in caps


def test_find_jobs_auto_expands_scan_for_later_pages(tmp_path: Path, monkeypatch) -> None:
    dataset = tmp_path / "companies.csv"
    _write_dataset(dataset)
    monkeypatch.setattr(server, "_get_required_user_visa_types", lambda user_id: ["h1b"])
    server._load_company_dataset.cache_clear()

    calls: list[int] = []

    def fake_scrape_jobs(**kwargs):
        wanted = int(kwargs["results_wanted"])
        calls.append(wanted)
        rows = []
        for i in range(wanted):
            rows.append(
                {
                    "title": f"Engineer {i}",
                    "company": "Acme Inc." if i % 8 == 0 else f"Other {i}",
                    "location": "Austin, TX",
                    "site": "linkedin",
                    "description": "General role text.",
                    "job_url": f"https://example.com/{i}",
                    "date_posted": "2026-02-18",
                }
            )
        return pd.DataFrame(rows)

    monkeypatch.setattr(server, "scrape_jobs", fake_scrape_jobs)

    result = server.find_visa_sponsored_jobs(
        location="Austin, TX",
        job_title="software engineer",
        user_id="u1",
        dataset_path=str(dataset),
        results_wanted=20,
        max_returned=10,
        offset=10,
        auto_expand_scan=True,
        scan_multiplier=1,
        max_scan_results=160,
    )

    assert calls == [20, 40, 80, 160]
    assert result["stats"]["scan_attempts"] == 4
    assert result["stats"]["scraped_jobs"] == 160
    assert result["pagination"]["accepted_jobs_total"] == 20
    assert result["pagination"]["returned_jobs"] == 10
    assert result["pagination"]["has_next_page"] is False
    assert result["pagination"]["next_offset"] is None
    assert result["jobs"][0]["job_url"] == "https://example.com/80"


def test_find_jobs_reuses_session_cache_for_follow_up_page(tmp_path: Path, monkeypatch) -> None:
    dataset = tmp_path / "companies.csv"
    _write_dataset(dataset)
    monkeypatch.setattr(server, "_get_required_user_visa_types", lambda user_id: ["h1b"])
    server._load_company_dataset.cache_clear()

    call_count = {"value": 0}

    def fake_scrape_jobs(**kwargs):
        call_count["value"] += 1
        wanted = int(kwargs["results_wanted"])
        rows = []
        for i in range(wanted):
            rows.append(
                {
                    "title": f"Engineer {i}",
                    "company": "Acme Inc." if i % 2 == 0 else f"Other {i}",
                    "location": "Austin, TX",
                    "site": "linkedin",
                    "description": "General role text.",
                    "job_url": f"https://example.com/{i}",
                    "date_posted": "2026-02-18",
                }
            )
        return pd.DataFrame(rows)

    monkeypatch.setattr(server, "scrape_jobs", fake_scrape_jobs)

    page1 = server.find_visa_sponsored_jobs(
        location="Austin, TX",
        job_title="software engineer",
        user_id="u1",
        dataset_path=str(dataset),
        results_wanted=20,
        max_returned=5,
        offset=0,
        auto_expand_scan=False,
    )
    assert call_count["value"] == 1
    assert page1["stats"]["cache_hit"] is False
    sid = page1["search_session"]["session_id"]
    assert sid

    page2 = server.find_visa_sponsored_jobs(
        location="Austin, TX",
        job_title="software engineer",
        user_id="u1",
        dataset_path=str(dataset),
        results_wanted=20,
        max_returned=5,
        offset=5,
        session_id=sid,
        auto_expand_scan=False,
    )
    assert call_count["value"] == 1
    assert page2["stats"]["cache_hit"] is True
    assert page2["search_session"]["reused_session"] is True
    assert len(page2["jobs"]) == 5


def test_find_jobs_rejects_session_id_when_query_changes(tmp_path: Path, monkeypatch) -> None:
    dataset = tmp_path / "companies.csv"
    _write_dataset(dataset)
    monkeypatch.setattr(server, "_get_required_user_visa_types", lambda user_id: ["h1b"])
    monkeypatch.setattr(
        server,
        "scrape_jobs",
        lambda **kwargs: pd.DataFrame(
            [
                {
                    "title": "Engineer 1",
                    "company": "Acme Inc.",
                    "location": "Austin, TX",
                    "site": "linkedin",
                    "description": "General role text.",
                    "job_url": "https://example.com/1",
                    "date_posted": "2026-02-18",
                }
            ]
        ),
    )
    server._load_company_dataset.cache_clear()

    page1 = server.find_visa_sponsored_jobs(
        location="Austin, TX",
        job_title="software engineer",
        user_id="u1",
        dataset_path=str(dataset),
    )
    sid = page1["search_session"]["session_id"]

    try:
        server.find_visa_sponsored_jobs(
            location="New York, NY",
            job_title="software engineer",
            user_id="u1",
            dataset_path=str(dataset),
            session_id=sid,
        )
        assert False, "Expected ValueError for mismatched session query"
    except ValueError as e:
        assert "does not match this query" in str(e)


def test_find_jobs_retries_rate_limit_then_succeeds(tmp_path: Path, monkeypatch) -> None:
    dataset = tmp_path / "companies.csv"
    _write_dataset(dataset)
    monkeypatch.setattr(server, "_get_required_user_visa_types", lambda user_id: ["h1b"])
    server._load_company_dataset.cache_clear()

    calls = {"n": 0}
    sleeps: list[float] = []

    def flaky_scrape_jobs(**kwargs):
        calls["n"] += 1
        if calls["n"] <= 2:
            raise RuntimeError("429 Too Many Requests")
        return pd.DataFrame(
            [
                {
                    "title": "SE1",
                    "company": "Acme Inc.",
                    "location": "Austin, TX",
                    "site": "linkedin",
                    "description": "General role text",
                    "job_url": "https://example.com/ok",
                    "date_posted": "2026-02-18",
                }
            ]
        )

    monkeypatch.setattr(server, "scrape_jobs", flaky_scrape_jobs)
    monkeypatch.setattr(server.time, "sleep", lambda seconds: sleeps.append(seconds))
    monkeypatch.setattr(server, "DEFAULT_RATE_LIMIT_RETRY_WINDOW_SECONDS", 180)
    monkeypatch.setattr(server, "DEFAULT_RATE_LIMIT_INITIAL_BACKOFF_SECONDS", 2)
    monkeypatch.setattr(server, "DEFAULT_RATE_LIMIT_MAX_BACKOFF_SECONDS", 30)

    result = server.find_visa_sponsored_jobs(
        location="Austin, TX",
        job_title="software engineer",
        user_id="u1",
        dataset_path=str(dataset),
        max_returned=10,
    )

    assert calls["n"] == 3
    assert sleeps == [2.0, 4.0]
    assert result["stats"]["rate_limit_retry_attempts"] == 2
    assert result["stats"]["rate_limit_backoff_seconds"] == 6.0
    assert len(result["jobs"]) == 1


def test_find_jobs_rate_limit_failure_after_retry_window(tmp_path: Path, monkeypatch) -> None:
    dataset = tmp_path / "companies.csv"
    _write_dataset(dataset)
    monkeypatch.setattr(server, "_get_required_user_visa_types", lambda user_id: ["h1b"])
    server._load_company_dataset.cache_clear()

    sleeps: list[float] = []
    monkeypatch.setattr(server, "scrape_jobs", lambda **kwargs: (_ for _ in ()).throw(RuntimeError("rate limit hit")))
    monkeypatch.setattr(server.time, "sleep", lambda seconds: sleeps.append(seconds))
    monkeypatch.setattr(server, "DEFAULT_RATE_LIMIT_RETRY_WINDOW_SECONDS", 5)
    monkeypatch.setattr(server, "DEFAULT_RATE_LIMIT_INITIAL_BACKOFF_SECONDS", 2)
    monkeypatch.setattr(server, "DEFAULT_RATE_LIMIT_MAX_BACKOFF_SECONDS", 30)

    try:
        server.find_visa_sponsored_jobs(
            location="Austin, TX",
            job_title="software engineer",
            user_id="u1",
            dataset_path=str(dataset),
            max_returned=10,
        )
        assert False, "Expected RuntimeError after exhausting retry window"
    except RuntimeError as e:
        text = str(e).lower()
        assert "rate limited" in text
        assert "try again" in text
    assert sleeps == [2.0, 3.0]


def test_strict_vs_balanced_mode_for_generic_sponsorship_text(tmp_path: Path, monkeypatch) -> None:
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
                    "title": "SE1",
                    "company": "Unknown Co",
                    "location": "Austin, TX",
                    "site": "linkedin",
                    "description": "Visa sponsorship available for qualified candidates.",
                    "job_url": "https://example.com/generic",
                    "date_posted": "2026-02-18",
                }
            ]
        ),
    )

    strict_res = server.find_visa_sponsored_jobs(
        location="Austin, TX",
        job_title="software engineer",
        user_id="u1",
        dataset_path=str(dataset),
        strictness_mode="strict",
    )
    assert strict_res["stats"]["accepted_jobs"] == 0

    balanced_res = server.find_visa_sponsored_jobs(
        location="Austin, TX",
        job_title="software engineer",
        user_id="u1",
        dataset_path=str(dataset),
        strictness_mode="balanced",
    )
    assert balanced_res["stats"]["accepted_jobs"] == 1
    assert balanced_res["jobs"][0]["matches_user_visa_preferences"] is True


def test_search_result_id_allows_save_and_ignore_by_alias(tmp_path: Path, monkeypatch) -> None:
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
                    "title": "SE1",
                    "company": "Acme Inc.",
                    "location": "New York, NY",
                    "site": "linkedin",
                    "description": "General role",
                    "job_url": "https://example.com/a",
                    "date_posted": "2026-02-18",
                }
            ]
        ),
    )

    res = server.find_visa_sponsored_jobs(
        location="New York, NY",
        job_title="software engineer",
        user_id="u1",
        dataset_path=str(dataset),
    )
    result_id = res["jobs"][0]["result_id"]
    session_id = res["search_session"]["session_id"]
    assert result_id.startswith(f"{session_id}:")

    saved = server.save_job_for_later(user_id="u1", result_id=result_id)
    assert saved["saved_job"]["job_url"] == "https://example.com/a"

    ignored = server.ignore_job(user_id="u1", result_id=result_id)
    assert ignored["ignored_job"]["job_url"] == "https://example.com/a"

    res_after_ignore = server.find_visa_sponsored_jobs(
        location="New York, NY",
        job_title="software engineer",
        user_id="u1",
        dataset_path=str(dataset),
    )
    assert res_after_ignore["stats"]["accepted_jobs"] == 0


def test_readiness_includes_dataset_freshness_from_manifest(tmp_path: Path) -> None:
    dataset = tmp_path / "companies.csv"
    dataset.write_text("company_tier,company_name,h1b,h1b1_chile,h1b1_singapore,e3_australian,green_card\\n", encoding="utf-8")
    manifest = {
        "run_at_utc": "2026-02-18T00:00:00Z",
        "output_path": str(dataset),
        "rows_written": 0,
    }
    Path(server.DEFAULT_DOL_MANIFEST_PATH).write_text(json.dumps(manifest), encoding="utf-8")
    server.set_user_preferences(user_id="u1", preferred_visa_types=["h1b"])

    readiness = server.get_user_readiness(user_id="u1", dataset_path=str(dataset))
    freshness = readiness["dataset_freshness"]
    assert freshness["manifest_run_at_utc"] == "2026-02-18T00:00:00Z"
    assert freshness["dataset_last_updated_at_utc"] is not None
    assert freshness["source"] == "manifest"


def test_session_limit_per_user_and_clear_tool(tmp_path: Path, monkeypatch) -> None:
    dataset = tmp_path / "companies.csv"
    _write_dataset(dataset)
    server.set_user_preferences(user_id="u1", preferred_visa_types=["h1b"])
    server._load_company_dataset.cache_clear()
    monkeypatch.setattr(server, "DEFAULT_MAX_SEARCH_SESSIONS_PER_USER", 1)
    monkeypatch.setattr(
        server,
        "scrape_jobs",
        lambda **kwargs: pd.DataFrame(
            [
                {
                    "title": "SE1",
                    "company": "Acme Inc.",
                    "location": "Austin, TX",
                    "site": "linkedin",
                    "description": "General role",
                    "job_url": "https://example.com/a",
                    "date_posted": "2026-02-18",
                }
            ]
        ),
    )

    s1 = server.find_visa_sponsored_jobs(
        location="Austin, TX",
        job_title="software engineer",
        user_id="u1",
        dataset_path=str(dataset),
    )["search_session"]["session_id"]
    s2 = server.find_visa_sponsored_jobs(
        location="Boston, MA",
        job_title="software engineer",
        user_id="u1",
        dataset_path=str(dataset),
    )["search_session"]["session_id"]
    assert s1 != s2

    store = server._load_search_sessions()
    sessions = store.get("sessions", {})
    assert s1 not in sessions
    assert s2 in sessions

    cleared = server.clear_search_session(user_id="u1", clear_all_for_user=True)
    assert cleared["deleted_count"] == 1
    assert cleared["remaining_user_sessions"] == 0


def test_export_and_delete_user_data(tmp_path: Path, monkeypatch) -> None:
    dataset = tmp_path / "companies.csv"
    _write_dataset(dataset)
    server.set_user_preferences(user_id="u1", preferred_visa_types=["h1b"])
    server.set_user_constraints(user_id="u1", days_remaining=30, work_modes=["remote"])
    server.add_user_memory_line(user_id="u1", content="Strong Python", kind="skills")
    server.save_job_for_later(user_id="u1", job_url="https://example.com/save-1")
    server.ignore_job(user_id="u1", job_url="https://example.com/ignore-1")
    server._load_company_dataset.cache_clear()

    monkeypatch.setattr(
        server,
        "scrape_jobs",
        lambda **kwargs: pd.DataFrame(
            [
                {
                    "title": "SE1",
                    "company": "Acme Inc.",
                    "location": "Austin, TX",
                    "site": "linkedin",
                    "description": "General role",
                    "job_url": "https://example.com/session",
                    "date_posted": "2026-02-18",
                }
            ]
        ),
    )
    server.find_visa_sponsored_jobs(
        location="Austin, TX",
        job_title="software engineer",
        user_id="u1",
        dataset_path=str(dataset),
    )

    exported = server.export_user_data(user_id="u1")
    assert exported["counts"]["memory_lines"] == 1
    assert exported["counts"]["saved_jobs"] == 1
    assert exported["counts"]["ignored_jobs"] == 1
    assert exported["counts"]["search_sessions"] == 1
    assert exported["counts"]["job_management_jobs"] >= 2
    assert exported["counts"]["job_management_applications"] >= 2
    assert "job_management" in exported["data"]

    deleted = server.delete_user_data(user_id="u1", confirm=True)
    assert deleted["deleted"]["preferences"] is True
    assert deleted["deleted"]["memory_lines"] == 1
    assert deleted["deleted"]["saved_jobs"] == 1
    assert deleted["deleted"]["ignored_jobs"] == 1
    assert deleted["deleted"]["search_sessions"] == 1
    assert deleted["deleted"]["job_management_jobs"] >= 2
    assert deleted["deleted"]["job_management_applications"] >= 2


def test_search_returns_recovery_suggestions_on_low_yield(tmp_path: Path, monkeypatch) -> None:
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
                    "title": "SE1",
                    "company": "Unknown Co",
                    "location": "New York, NY",
                    "site": "linkedin",
                    "description": "No sponsorship details here.",
                    "job_url": "https://example.com/no-match",
                    "date_posted": "2026-02-18",
                }
            ]
        ),
    )

    result = server.find_visa_sponsored_jobs(
        location="New York, NY",
        job_title="software engineer",
        user_id="u1",
        dataset_path=str(dataset),
        max_returned=10,
    )
    assert result["stats"]["accepted_jobs"] == 0
    assert result["recovery_suggestions"]
    assert any(step["id"] == "related_titles" for step in result["recovery_suggestions"])


def test_contact_strategy_and_outreach_template_from_result_id(tmp_path: Path, monkeypatch) -> None:
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
                    "description": "General role",
                    "job_url": "https://example.com/contact",
                    "date_posted": "2026-02-18",
                }
            ]
        ),
    )

    result = server.find_visa_sponsored_jobs(
        location="New York, NY",
        job_title="software engineer",
        user_id="u1",
        dataset_path=str(dataset),
    )
    result_id = result["jobs"][0]["result_id"]

    strategy = server.get_best_contact_strategy(user_id="u1", result_id=result_id)
    assert strategy["recommended_channel"] == "email"
    assert strategy["primary_contact"]["email"] == "jane@acme.com"

    draft = server.generate_outreach_message(user_id="u1", result_id=result_id)
    assert "H-1B" in draft["subject"]
    assert "Software Engineer" in draft["message"]


def test_related_titles_has_generic_fallback_for_uncommon_titles() -> None:
    related = server.find_related_titles(job_title="forensic lighthouse quantum architect", limit=5)
    assert related["count"] >= 1
    assert isinstance(related["related_titles"], list)
