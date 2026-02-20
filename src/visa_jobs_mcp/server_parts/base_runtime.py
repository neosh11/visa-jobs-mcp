from __future__ import annotations

import json
import os
import re
import hashlib
import time
import sqlite3
import uuid
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any

import pandas as pd
from mcp.server.fastmcp import FastMCP
from visa_jobs_mcp import __version__
from visa_jobs_mcp.jobspy_adapter import JOBSPY_SOURCE, scrape_jobs
from visa_jobs_mcp.pipeline import (
    DEFAULT_MANIFEST_PATH,
    discover_latest_dol_disclosure_urls as pipeline_discover_latest_dol_disclosure_urls,
    run_dol_pipeline,
)
from visa_jobs_mcp.runtime_paths import resolve_runtime_dataset_path

mcp = FastMCP("visa-jobs-mcp")

DEFAULT_DATASET_PATH = resolve_runtime_dataset_path()
DEFAULT_SITES = [
    s.strip()
    for s in os.getenv("VISA_JOB_SITES", "linkedin").split(",")
    if s.strip()
]
SUPPORTED_SITES = {"linkedin"}
DEFAULT_INDEED_COUNTRY = os.getenv("VISA_INDEED_COUNTRY", "USA")
DEFAULT_DOL_PERFORMANCE_URL = os.getenv(
    "VISA_DOL_PERFORMANCE_URL",
    "https://www.dol.gov/agencies/eta/foreign-labor/performance",
)
DEFAULT_DOL_MANIFEST_PATH = os.getenv(
    "VISA_DOL_MANIFEST_PATH",
    DEFAULT_MANIFEST_PATH,
)
DEFAULT_USER_PREFS_PATH = os.getenv(
    "VISA_USER_PREFS_PATH",
    "data/config/user_preferences.json",
)
DEFAULT_USER_BLOB_PATH = os.getenv(
    "VISA_USER_BLOB_PATH",
    "data/config/user_memory_blob.json",
)


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


DEFAULT_SCAN_MULTIPLIER = _env_int("VISA_SCAN_MULTIPLIER", 8)
DEFAULT_MAX_SCAN_RESULTS = _env_int("VISA_MAX_SCAN_RESULTS", 1200)
DEFAULT_DATASET_STALE_AFTER_DAYS = _env_int("VISA_DATASET_STALE_AFTER_DAYS", 30)
DEFAULT_RATE_LIMIT_RETRY_WINDOW_SECONDS = _env_int(
    "VISA_RATE_LIMIT_RETRY_WINDOW_SECONDS",
    180,
)
DEFAULT_RATE_LIMIT_INITIAL_BACKOFF_SECONDS = _env_int(
    "VISA_RATE_LIMIT_INITIAL_BACKOFF_SECONDS",
    2,
)
DEFAULT_RATE_LIMIT_MAX_BACKOFF_SECONDS = _env_int(
    "VISA_RATE_LIMIT_MAX_BACKOFF_SECONDS",
    30,
)
DEFAULT_TOOL_CALL_SOFT_TIMEOUT_SECONDS = _env_int(
    "VISA_TOOL_CALL_SOFT_TIMEOUT_SECONDS",
    48,
)
DEFAULT_SCRAPE_ATTEMPT_TIMEOUT_SECONDS = _env_int(
    "VISA_SCRAPE_ATTEMPT_TIMEOUT_SECONDS",
    35,
)
DEFAULT_SEARCH_SESSION_PATH = os.getenv(
    "VISA_SEARCH_SESSION_PATH",
    "data/config/search_sessions.json",
)
DEFAULT_SEARCH_SESSION_TTL_SECONDS = _env_int("VISA_SEARCH_SESSION_TTL_SECONDS", 21600)
DEFAULT_MAX_SEARCH_SESSIONS = _env_int("VISA_MAX_SEARCH_SESSIONS", 200)
DEFAULT_MAX_SEARCH_SESSIONS_PER_USER = _env_int("VISA_MAX_SEARCH_SESSIONS_PER_USER", 20)
DEFAULT_SEARCH_RUNS_PATH = os.getenv(
    "VISA_SEARCH_RUNS_PATH",
    "data/config/search_runs.json",
)
DEFAULT_SEARCH_RUN_TTL_SECONDS = _env_int("VISA_SEARCH_RUN_TTL_SECONDS", 21600)
DEFAULT_MAX_SEARCH_RUNS = _env_int("VISA_MAX_SEARCH_RUNS", 500)
DEFAULT_SAVED_JOBS_PATH = os.getenv(
    "VISA_SAVED_JOBS_PATH",
    "data/config/saved_jobs.json",
)
DEFAULT_IGNORED_JOBS_PATH = os.getenv(
    "VISA_IGNORED_JOBS_PATH",
    "data/config/ignored_jobs.json",
)
DEFAULT_IGNORED_COMPANIES_PATH = os.getenv(
    "VISA_IGNORED_COMPANIES_PATH",
    "data/config/ignored_companies.json",
)
DEFAULT_JOB_DB_PATH = os.getenv(
    "VISA_JOB_DB_PATH",
    "data/app/visa_jobs.db",
)

CAPABILITIES_SCHEMA_VERSION = "1.1.0"
CONFIDENCE_MODEL_VERSION = "v1.1.0-rules"
SUPPORTED_STRICTNESS_MODES = {"strict", "balanced"}
SUPPORTED_WORK_MODES = {"remote", "hybrid", "onsite"}
VALID_JOB_STAGES = {"new", "saved", "applied", "interview", "offer", "rejected", "ignored"}
JOB_DB_MIGRATION_KEY = "json_saved_ignored_v1"
_JOB_DB_READY_PATHS: set[str] = set()


VISA_POSITIVE_PATTERNS = [
    r"\bvisa sponsorship\b",
    r"\bsponsor(?:ship|ed|s)?\b",
    r"\bh-?1b\b",
    r"\be-?3\b",
    r"\bopt\b",
    r"\bcpt\b",
    r"\bgreen card\b",
]

VISA_NEGATIVE_PATTERNS = [
    r"\bno visa sponsorship\b",
    r"\bwithout visa sponsorship\b",
    r"\bdo not sponsor\b",
    r"\bunable to sponsor\b",
    r"\bmust be authorized to work\b",
]

CANONICAL_COLUMNS = {
    "company_tier": ["company_tier", "size"],
    "company_name": ["company_name", "EMPLOYER"],
    "h1b": ["h1b", "H-1B"],
    "h1b1_chile": ["h1b1_chile", "H-1B1 Chile"],
    "h1b1_singapore": ["h1b1_singapore", "H-1B1 Singapore"],
    "e3_australian": ["e3_australian", "E-3 Australian"],
    "green_card": ["green_card", "Green Card"],
    "email_1": ["email_1", "EMAIL_1"],
    "email_1_date": ["email_1_date", "EMAIL_1_DATE"],
    "contact_1": ["contact_1", "CONTACT_1"],
    "contact_1_title": ["contact_1_title", "CONTACT_1_TITLE"],
    "contact_1_phone": ["contact_1_phone", "CONTACT_1_PHONE"],
    "email_2": ["email_2", "EMAIL_2"],
    "email_2_date": ["email_2_date", "EMAIL_2_DATE"],
    "contact_2": ["contact_2", "CONTACT_2"],
    "contact_2_title": ["contact_2_title", "CONTACT_2_TITLE"],
    "contact_2_phone": ["contact_2_phone", "CONTACT_2_PHONE"],
    "email_3": ["email_3", "EMAIL_3"],
    "email_3_date": ["email_3_date", "EMAIL_3_DATE"],
    "contact_3": ["contact_3", "CONTACT_3"],
    "contact_3_title": ["contact_3_title", "CONTACT_3_TITLE"],
    "contact_3_phone": ["contact_3_phone", "CONTACT_3_PHONE"],
}

LEGAL_SUFFIXES = (
    "inc",
    "corp",
    "corporation",
    "co",
    "llc",
    "ltd",
    "lp",
    "plc",
    "pc",
    "holdings",
    "holding",
    "group",
    "technologies",
    "technology",
)

VISA_TYPE_ALIASES = {
    "h1b": "h1b",
    "h-1b": "h1b",
    "h1b1_chile": "h1b1_chile",
    "h-1b1 chile": "h1b1_chile",
    "h1b1 chile": "h1b1_chile",
    "h1b1_chile/singapore": "h1b1_chile",
    "h1b1_singapore": "h1b1_singapore",
    "h-1b1 singapore": "h1b1_singapore",
    "h1b1 singapore": "h1b1_singapore",
    "e3": "e3_australian",
    "e-3": "e3_australian",
    "e3_australian": "e3_australian",
    "e-3 australian": "e3_australian",
    "green_card": "green_card",
    "green card": "green_card",
    "perm": "green_card",
}

VISA_TYPE_LABELS = {
    "h1b": "H-1B",
    "h1b1_chile": "H-1B1 Chile",
    "h1b1_singapore": "H-1B1 Singapore",
    "e3_australian": "E-3 Australian",
    "green_card": "Green Card",
}

RELATED_TITLE_HINTS = {
    "software engineer": [
        "Software Developer",
        "Backend Engineer",
        "Full Stack Engineer",
        "Platform Engineer",
        "Site Reliability Engineer",
        "Application Engineer",
        "Machine Learning Engineer",
    ],
    "data engineer": [
        "Data Platform Engineer",
        "Analytics Engineer",
        "ETL Engineer",
        "Big Data Engineer",
        "Data Infrastructure Engineer",
        "Data Developer",
    ],
    "product manager": [
        "Technical Product Manager",
        "Program Manager",
        "Product Owner",
        "Growth Product Manager",
        "Platform Product Manager",
    ],
}



@dataclass
class CompanySponsorStats:
    company_name: str
    company_tier: str
    h1b: int
    h1b1_chile: int
    h1b1_singapore: int
    e3_australian: int
    green_card: int
    total_visas: int
    email_1: str
    contact_1: str
    contact_1_title: str
    contact_1_phone: str


@dataclass
class EvaluatedJob:
    title: str
    company: str
    location: str
    site: str
    date_posted: str | None
    job_url: str
    description_snippet: str
    matched_via_company_dataset: bool
    matched_via_job_description: bool
    rejected_for_no_sponsorship_phrase: bool
    sponsorship_reasons: list[str]
    employer_contacts: list[dict[str, str]]
    visa_counts: dict[str, int]
    visas_sponsored: list[str]
    matches_user_visa_preferences: bool
    visa_match_strength: str
    eligibility_reasons: list[str]
    confidence_score: float
    confidence_model_version: str
    contactability_score: float
    sponsor_stats: dict[str, Any] | None


def _disable_proxies() -> None:
    for key in (
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "ALL_PROXY",
        "http_proxy",
        "https_proxy",
        "all_proxy",
    ):
        os.environ.pop(key, None)


def _normalize_visa_type(value: str) -> str:
    key = value.strip().lower()
    if key not in VISA_TYPE_ALIASES:
        raise ValueError(
            f"Unsupported visa type '{value}'. Use one of: {sorted(set(VISA_TYPE_ALIASES.values()))}"
        )
    return VISA_TYPE_ALIASES[key]


def _normalize_work_mode(value: str) -> str:
    mode = value.strip().lower()
    if mode not in SUPPORTED_WORK_MODES:
        raise ValueError(
            f"Unsupported work mode '{value}'. Use one or more of: {sorted(SUPPORTED_WORK_MODES)}"
        )
    return mode


def _normalize_strictness_mode(value: str) -> str:
    mode = value.strip().lower()
    if mode not in SUPPORTED_STRICTNESS_MODES:
        raise ValueError(
            f"strictness_mode must be one of {sorted(SUPPORTED_STRICTNESS_MODES)}"
        )
    return mode


def _load_user_prefs(path: str = DEFAULT_USER_PREFS_PATH) -> dict[str, Any]:
    pref_file = Path(path)
    if not pref_file.exists():
        return {}
    try:
        return json.loads(pref_file.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def _save_user_prefs(data: dict[str, Any], path: str = DEFAULT_USER_PREFS_PATH) -> None:
    pref_file = Path(path)
    pref_file.parent.mkdir(parents=True, exist_ok=True)
    pref_file.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _future_utc_iso(seconds_from_now: int) -> str:
    return (
        (datetime.now(timezone.utc) + timedelta(seconds=max(1, seconds_from_now)))
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _parse_utc_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    text = str(value).strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _read_json_file(path: str, fallback: dict[str, Any]) -> dict[str, Any]:
    file_path = Path(path)
    if not file_path.exists():
        return dict(fallback)
    try:
        parsed = json.loads(file_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return dict(fallback)
    if not isinstance(parsed, dict):
        return dict(fallback)
    return parsed


def _dataset_freshness(
    dataset_path: str,
    manifest_path: str | None = None,
    stale_after_days: int | None = None,
) -> dict[str, Any]:
    now_utc = datetime.now(timezone.utc)
    stale_days = max(1, int(stale_after_days if stale_after_days is not None else DEFAULT_DATASET_STALE_AFTER_DAYS))
    manifest_file_path = manifest_path or DEFAULT_DOL_MANIFEST_PATH

    manifest = _read_json_file(manifest_file_path, fallback={})
    manifest_run_at_utc = str(manifest.get("run_at_utc", "")).strip()
    manifest_output_path = str(manifest.get("output_path", "")).strip()
    manifest_dt = _parse_utc_iso(manifest_run_at_utc)

    dataset_resolved = str(Path(dataset_path).expanduser().resolve())
    manifest_output_resolved = ""
    if manifest_output_path:
        try:
            manifest_output_resolved = str(Path(manifest_output_path).expanduser().resolve())
        except Exception:
            manifest_output_resolved = manifest_output_path

    source = "unknown"
    refreshed_at = None
    dataset_exists = Path(dataset_path).exists()
    output_matches = bool(
        manifest_output_resolved
        and manifest_output_resolved == dataset_resolved
    )

    if manifest_dt and output_matches:
        source = "manifest"
        refreshed_at = manifest_dt
    elif dataset_exists:
        source = "filesystem_mtime"
        refreshed_at = datetime.fromtimestamp(Path(dataset_path).stat().st_mtime, tz=timezone.utc)

    age_seconds = None
    age_days = None
    is_stale = True
    if refreshed_at:
        age_seconds = max(0.0, (now_utc - refreshed_at).total_seconds())
        age_days = round(age_seconds / 86400.0, 2)
        is_stale = age_days >= stale_days

    return {
        "dataset_exists": bool(dataset_exists),
        "dataset_path": dataset_path,
        "manifest_path": manifest_file_path,
        "manifest_run_at_utc": manifest_run_at_utc or None,
        "dataset_last_updated_at_utc": (
            refreshed_at.replace(microsecond=0).isoformat().replace("+00:00", "Z")
            if refreshed_at
            else None
        ),
        "days_since_refresh": age_days,
        "age_seconds": round(age_seconds, 2) if age_seconds is not None else None,
        "stale_after_days": int(stale_days),
        "is_stale": bool(is_stale),
        "source": source,
        "manifest_output_matches_dataset": bool(output_matches),
    }


def _stable_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _search_session_store_path(path: str | None = None) -> str:
    return path or DEFAULT_SEARCH_SESSION_PATH


def _load_search_sessions(path: str | None = None) -> dict[str, Any]:
    store_file = Path(_search_session_store_path(path))
    if not store_file.exists():
        return {"sessions": {}}
    try:
        data = json.loads(store_file.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"sessions": {}}
    if not isinstance(data, dict):
        return {"sessions": {}}
    sessions = data.get("sessions")
    if not isinstance(sessions, dict):
        data["sessions"] = {}
    return data


def _save_search_sessions(data: dict[str, Any], path: str | None = None) -> None:
    store_file = Path(_search_session_store_path(path))
    store_file.parent.mkdir(parents=True, exist_ok=True)
    store_file.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _search_run_store_path(path: str | None = None) -> str:
    return path or DEFAULT_SEARCH_RUNS_PATH


def _load_search_runs(path: str | None = None) -> dict[str, Any]:
    store_file = Path(_search_run_store_path(path))
    if not store_file.exists():
        return {"runs": {}}
    try:
        data = json.loads(store_file.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"runs": {}}
    if not isinstance(data, dict):
        return {"runs": {}}
    runs = data.get("runs")
    if not isinstance(runs, dict):
        data["runs"] = {}
    return data


def _save_search_runs(data: dict[str, Any], path: str | None = None) -> None:
    store_file = Path(_search_run_store_path(path))
    store_file.parent.mkdir(parents=True, exist_ok=True)
    store_file.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _job_db_path(path: str | None = None) -> str:
    return path or DEFAULT_JOB_DB_PATH


@contextmanager
def _job_db_conn(path: str | None = None):
    db_file = Path(_job_db_path(path))
    db_file.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_file)
    try:
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        yield conn
        conn.commit()
    finally:
        conn.close()


def _validate_job_stage(stage: str) -> str:
    clean = stage.strip().lower()
    if clean not in VALID_JOB_STAGES:
        raise ValueError(f"stage must be one of {sorted(VALID_JOB_STAGES)}")
    return clean


def _ensure_job_db(path: str | None = None) -> None:
    with _job_db_conn(path) as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
              key TEXT PRIMARY KEY,
              applied_at_utc TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS jobs (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              user_id TEXT NOT NULL,
              result_id TEXT NOT NULL DEFAULT '',
              job_url TEXT NOT NULL,
              title TEXT NOT NULL DEFAULT '',
              company TEXT NOT NULL DEFAULT '',
              location TEXT NOT NULL DEFAULT '',
              site TEXT NOT NULL DEFAULT '',
              created_at_utc TEXT NOT NULL,
              updated_at_utc TEXT NOT NULL,
              UNIQUE(user_id, job_url)
            );

            CREATE TABLE IF NOT EXISTS job_applications (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              user_id TEXT NOT NULL,
              job_id INTEGER NOT NULL,
              stage TEXT NOT NULL,
              applied_at_utc TEXT,
              source_session_id TEXT NOT NULL DEFAULT '',
              note TEXT NOT NULL DEFAULT '',
              updated_at_utc TEXT NOT NULL,
              UNIQUE(user_id, job_id),
              FOREIGN KEY(job_id) REFERENCES jobs(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS job_events (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              user_id TEXT NOT NULL,
              job_id INTEGER NOT NULL,
              from_stage TEXT,
              to_stage TEXT,
              reason TEXT NOT NULL DEFAULT '',
              note TEXT NOT NULL DEFAULT '',
              created_at_utc TEXT NOT NULL,
              FOREIGN KEY(job_id) REFERENCES jobs(id) ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_jobs_user_id ON jobs(user_id);
            CREATE INDEX IF NOT EXISTS idx_jobs_user_url ON jobs(user_id, job_url);
            CREATE INDEX IF NOT EXISTS idx_apps_user_stage ON job_applications(user_id, stage, updated_at_utc);
            CREATE INDEX IF NOT EXISTS idx_events_user_created ON job_events(user_id, created_at_utc);
            """
        )


def _row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return {key: row[key] for key in row.keys()}


def _get_job_by_id_in_conn(conn: sqlite3.Connection, user_id: str, job_id: int) -> dict[str, Any] | None:
    row = conn.execute(
        """
        SELECT id, user_id, result_id, job_url, title, company, location, site, created_at_utc, updated_at_utc
        FROM jobs
        WHERE user_id = ? AND id = ?
        """,
        (user_id, int(job_id)),
    ).fetchone()
    return _row_to_dict(row)


def _get_job_by_url_in_conn(conn: sqlite3.Connection, user_id: str, job_url: str) -> dict[str, Any] | None:
    row = conn.execute(
        """
        SELECT id, user_id, result_id, job_url, title, company, location, site, created_at_utc, updated_at_utc
        FROM jobs
        WHERE user_id = ? AND lower(job_url) = lower(?)
        LIMIT 1
        """,
        (user_id, job_url.strip()),
    ).fetchone()
    return _row_to_dict(row)


def _upsert_job_in_conn(
    conn: sqlite3.Connection,
    *,
    user_id: str,
    job_url: str,
    title: str = "",
    company: str = "",
    location: str = "",
    site: str = "",
    result_id: str = "",
) -> int:
    uid = user_id.strip()
    clean_url = job_url.strip()
    if not uid:
        raise ValueError("user_id is required")
    if not clean_url:
        raise ValueError("job_url is required")

    now_utc = _utcnow_iso()
    existing = conn.execute(
        """
        SELECT id, title, company, location, site, result_id
        FROM jobs
        WHERE user_id = ? AND lower(job_url) = lower(?)
        LIMIT 1
        """,
        (uid, clean_url),
    ).fetchone()
    if existing:
        existing_id = int(existing["id"])
        merged_title = title.strip() or str(existing["title"] or "")
        merged_company = company.strip() or str(existing["company"] or "")
        merged_location = location.strip() or str(existing["location"] or "")
        merged_site = site.strip() or str(existing["site"] or "")
        merged_result_id = result_id.strip() or str(existing["result_id"] or "")
        conn.execute(
            """
            UPDATE jobs
            SET result_id = ?, title = ?, company = ?, location = ?, site = ?, updated_at_utc = ?
            WHERE id = ?
            """,
            (
                merged_result_id,
                merged_title,
                merged_company,
                merged_location,
                merged_site,
                now_utc,
                existing_id,
            ),
        )
        return existing_id

    cursor = conn.execute(
        """
        INSERT INTO jobs (user_id, result_id, job_url, title, company, location, site, created_at_utc, updated_at_utc)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            uid,
            result_id.strip(),
            clean_url,
            title.strip(),
            company.strip(),
            location.strip(),
            site.strip(),
            now_utc,
            now_utc,
        ),
    )
    return int(cursor.lastrowid)


def _set_job_stage_in_conn(
    conn: sqlite3.Connection,
    *,
    user_id: str,
    job_id: int,
    stage: str,
    note: str = "",
    source_session_id: str = "",
    applied_at_utc: str = "",
    reason: str = "stage_update",
) -> tuple[dict[str, Any], dict[str, Any]]:
    uid = user_id.strip()
    if not uid:
        raise ValueError("user_id is required")
    clean_stage = _validate_job_stage(stage)
    if job_id < 1:
        raise ValueError("job_id must be a positive integer")

    existing = conn.execute(
        """
        SELECT id, stage, applied_at_utc, source_session_id, note
        FROM job_applications
        WHERE user_id = ? AND job_id = ?
        LIMIT 1
        """,
        (uid, int(job_id)),
    ).fetchone()

    prior_stage = str(existing["stage"]) if existing else None
    prior_note = str(existing["note"] or "") if existing else ""
    merged_note = prior_note
    new_note = note.strip()
    if new_note:
        merged_note = f"{prior_note}\n{new_note}".strip() if prior_note else new_note

    prior_applied_at = str(existing["applied_at_utc"] or "") if existing else ""
    final_applied_at = prior_applied_at or None
    if clean_stage == "applied":
        explicit_applied_at = applied_at_utc.strip()
        final_applied_at = explicit_applied_at or prior_applied_at or _utcnow_iso()

    prior_source_session = str(existing["source_session_id"] or "") if existing else ""
    final_source_session = source_session_id.strip() or prior_source_session
    now_utc = _utcnow_iso()

    conn.execute(
        """
        INSERT INTO job_applications (
          user_id, job_id, stage, applied_at_utc, source_session_id, note, updated_at_utc
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(user_id, job_id) DO UPDATE SET
          stage = excluded.stage,
          applied_at_utc = COALESCE(excluded.applied_at_utc, job_applications.applied_at_utc),
          source_session_id = CASE
            WHEN excluded.source_session_id <> '' THEN excluded.source_session_id
            ELSE job_applications.source_session_id
          END,
          note = excluded.note,
          updated_at_utc = excluded.updated_at_utc
        """,
        (
            uid,
            int(job_id),
            clean_stage,
            final_applied_at,
            final_source_session,
            merged_note,
            now_utc,
        ),
    )

    conn.execute(
        """
        INSERT INTO job_events (user_id, job_id, from_stage, to_stage, reason, note, created_at_utc)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            uid,
            int(job_id),
            prior_stage,
            clean_stage,
            reason.strip() or "stage_update",
            new_note,
            now_utc,
        ),
    )

    app_row = conn.execute(
        """
        SELECT id, user_id, job_id, stage, applied_at_utc, source_session_id, note, updated_at_utc
        FROM job_applications
        WHERE user_id = ? AND job_id = ?
        LIMIT 1
        """,
        (uid, int(job_id)),
    ).fetchone()
    event_row = conn.execute(
        """
        SELECT id, user_id, job_id, from_stage, to_stage, reason, note, created_at_utc
        FROM job_events
        WHERE rowid = last_insert_rowid()
        """
    ).fetchone()
    return _row_to_dict(app_row) or {}, _row_to_dict(event_row) or {}


def _append_job_note_in_conn(
    conn: sqlite3.Connection,
    *,
    user_id: str,
    job_id: int,
    note: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    clean_note = note.strip()
    if not clean_note:
        raise ValueError("note is required")

    existing = conn.execute(
        """
        SELECT id, stage, note
        FROM job_applications
        WHERE user_id = ? AND job_id = ?
        LIMIT 1
        """,
        (user_id, int(job_id)),
    ).fetchone()
    current_stage = str(existing["stage"]) if existing else "new"
    if not existing:
        _set_job_stage_in_conn(
            conn,
            user_id=user_id,
            job_id=int(job_id),
            stage="new",
            reason="initialize_application",
        )
        existing_note = ""
    else:
        existing_note = str(existing["note"] or "")

    merged_note = f"{existing_note}\n{clean_note}".strip() if existing_note else clean_note
    now_utc = _utcnow_iso()
    conn.execute(
        """
        UPDATE job_applications
        SET note = ?, updated_at_utc = ?
        WHERE user_id = ? AND job_id = ?
        """,
        (merged_note, now_utc, user_id, int(job_id)),
    )
    conn.execute(
        """
        INSERT INTO job_events (user_id, job_id, from_stage, to_stage, reason, note, created_at_utc)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            user_id,
            int(job_id),
            current_stage,
            current_stage,
            "note_added",
            clean_note,
            now_utc,
        ),
    )

    app_row = conn.execute(
        """
        SELECT id, user_id, job_id, stage, applied_at_utc, source_session_id, note, updated_at_utc
        FROM job_applications
        WHERE user_id = ? AND job_id = ?
        LIMIT 1
        """,
        (user_id, int(job_id)),
    ).fetchone()
    event_row = conn.execute(
        """
        SELECT id, user_id, job_id, from_stage, to_stage, reason, note, created_at_utc
        FROM job_events
        WHERE rowid = last_insert_rowid()
        """
    ).fetchone()
    return _row_to_dict(app_row) or {}, _row_to_dict(event_row) or {}


def _job_snapshot_in_conn(conn: sqlite3.Connection, user_id: str, job_id: int) -> dict[str, Any]:
    row = conn.execute(
        """
        SELECT
          j.id AS job_id,
          j.user_id,
          j.result_id,
          j.job_url,
          j.title,
          j.company,
          j.location,
          j.site,
          j.created_at_utc,
          j.updated_at_utc,
          COALESCE(ja.stage, 'new') AS stage,
          ja.applied_at_utc,
          COALESCE(ja.source_session_id, '') AS source_session_id,
          COALESCE(ja.note, '') AS note,
          ja.updated_at_utc AS stage_updated_at_utc
        FROM jobs j
        LEFT JOIN job_applications ja
          ON ja.user_id = j.user_id AND ja.job_id = j.id
        WHERE j.user_id = ? AND j.id = ?
        LIMIT 1
        """,
        (user_id, int(job_id)),
    ).fetchone()
    snapshot = _row_to_dict(row)
    if not snapshot:
        raise ValueError("job record not found")
    return snapshot


def _resolve_job_management_target_in_conn(
    conn: sqlite3.Connection,
    *,
    user_id: str,
    job_id: int = 0,
    job_url: str = "",
    result_id: str = "",
    session_id: str = "",
    title: str = "",
    company: str = "",
    location: str = "",
    site: str = "",
) -> tuple[int, dict[str, Any]]:
    uid = user_id.strip()
    if not uid:
        raise ValueError("user_id is required")

    if int(job_id or 0) > 0:
        existing = _get_job_by_id_in_conn(conn, uid, int(job_id))
        if not existing:
            raise ValueError(f"job_id={int(job_id)} not found for user_id='{uid}'")
        return int(existing["id"]), existing

    resolved = _resolve_job_reference(
        user_id=uid,
        job_url=job_url,
        result_id=result_id,
        session_id=session_id,
    )
    merged_title = title.strip() or str(resolved.get("title", "")).strip()
    merged_company = company.strip() or str(resolved.get("company", "")).strip()
    merged_location = location.strip() or str(resolved.get("location", "")).strip()
    merged_site = site.strip() or str(resolved.get("site", "")).strip()
    clean_url = str(resolved.get("job_url", "")).strip()
    if not clean_url:
        raise ValueError("job_url is required")

    upserted_id = _upsert_job_in_conn(
        conn,
        user_id=uid,
        job_url=clean_url,
        title=merged_title,
        company=merged_company,
        location=merged_location,
        site=merged_site,
        result_id=str(resolved.get("result_id", "")).strip(),
    )
    job_record = _get_job_by_id_in_conn(conn, uid, upserted_id) or {}
    return upserted_id, job_record
