from __future__ import annotations

import json
import os
import re
import hashlib
import time
import uuid
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
    default_dataset_path,
    discover_latest_dol_disclosure_urls as pipeline_discover_latest_dol_disclosure_urls,
    run_dol_pipeline,
)

mcp = FastMCP("visa-jobs-mcp")

DEFAULT_DATASET_PATH = default_dataset_path()
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
DEFAULT_SEARCH_SESSION_PATH = os.getenv(
    "VISA_SEARCH_SESSION_PATH",
    "data/config/search_sessions.json",
)
DEFAULT_SEARCH_SESSION_TTL_SECONDS = _env_int("VISA_SEARCH_SESSION_TTL_SECONDS", 21600)
DEFAULT_MAX_SEARCH_SESSIONS = _env_int("VISA_MAX_SEARCH_SESSIONS", 200)
DEFAULT_MAX_SEARCH_SESSIONS_PER_USER = _env_int("VISA_MAX_SEARCH_SESSIONS_PER_USER", 20)
DEFAULT_SAVED_JOBS_PATH = os.getenv(
    "VISA_SAVED_JOBS_PATH",
    "data/config/saved_jobs.json",
)
DEFAULT_IGNORED_JOBS_PATH = os.getenv(
    "VISA_IGNORED_JOBS_PATH",
    "data/config/ignored_jobs.json",
)

CAPABILITIES_SCHEMA_VERSION = "1.1.0"
CONFIDENCE_MODEL_VERSION = "v1.1.0-rules"
SUPPORTED_STRICTNESS_MODES = {"strict", "balanced"}
SUPPORTED_WORK_MODES = {"remote", "hybrid", "onsite"}


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


def _prune_search_sessions(
    data: dict[str, Any],
    max_sessions: int = DEFAULT_MAX_SEARCH_SESSIONS,
) -> dict[str, Any]:
    sessions = data.get("sessions")
    if not isinstance(sessions, dict):
        data["sessions"] = {}
        return data

    now = datetime.now(timezone.utc)
    valid: dict[str, dict[str, Any]] = {}
    for sid, record in sessions.items():
        if not isinstance(record, dict):
            continue
        expires_at = _parse_utc_iso(record.get("expires_at_utc"))
        if expires_at and expires_at <= now:
            continue
        valid[sid] = record

    def sort_key(item: tuple[str, dict[str, Any]]) -> datetime:
        dt = _parse_utc_iso(item[1].get("updated_at_utc")) or _parse_utc_iso(item[1].get("created_at_utc"))
        return dt or datetime.fromtimestamp(0, tz=timezone.utc)

    if max_sessions > 0 and len(valid) > max_sessions:
        ordered = sorted(valid.items(), key=sort_key, reverse=True)[:max_sessions]
        valid = {sid: record for sid, record in ordered}

    data["sessions"] = valid
    return data


def _enforce_user_session_limit(
    data: dict[str, Any],
    user_id: str,
    max_sessions_per_user: int = DEFAULT_MAX_SEARCH_SESSIONS_PER_USER,
) -> dict[str, Any]:
    if max_sessions_per_user <= 0:
        return data
    sessions = data.get("sessions")
    if not isinstance(sessions, dict):
        return data

    uid = user_id.strip()
    if not uid:
        return data

    user_sessions: list[tuple[str, dict[str, Any], int]] = []
    for ordinal, (sid, record) in enumerate(sessions.items()):
        if not isinstance(record, dict):
            continue
        query = record.get("query", {})
        if not isinstance(query, dict):
            continue
        if str(query.get("user_id", "")).strip() != uid:
            continue
        user_sessions.append((sid, record, ordinal))

    if len(user_sessions) <= max_sessions_per_user:
        return data

    def sort_key(item: tuple[str, dict[str, Any], int]) -> tuple[datetime, int]:
        dt = _parse_utc_iso(item[1].get("updated_at_utc")) or _parse_utc_iso(item[1].get("created_at_utc"))
        return (dt or datetime.fromtimestamp(0, tz=timezone.utc), item[2])

    user_sessions.sort(key=sort_key, reverse=True)
    keep_ids = {sid for sid, _, _ in user_sessions[:max_sessions_per_user]}
    for sid, _, _ in user_sessions[max_sessions_per_user:]:
        if sid not in keep_ids:
            sessions.pop(sid, None)
    data["sessions"] = sessions
    return data


def _search_query_fingerprint(
    *,
    location: str,
    job_title: str,
    user_id: str,
    hours_old: int,
    dataset_path: str,
    sites: list[str],
    require_description_signal: bool,
    desired_visa_types: list[str],
    strictness_mode: str,
) -> str:
    payload = {
        "location": location.strip().lower(),
        "job_title": job_title.strip().lower(),
        "user_id": user_id.strip(),
        "hours_old": int(hours_old),
        "dataset_path": str(Path(dataset_path).expanduser().resolve()),
        "sites": sorted(sites),
        "require_description_signal": bool(require_description_signal),
        "preferred_visa_types": sorted(desired_visa_types),
        "strictness_mode": strictness_mode,
    }
    return hashlib.sha256(_stable_json(payload).encode("utf-8")).hexdigest()


def _attach_result_ids(session_id: str, accepted_jobs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for idx, job in enumerate(accepted_jobs, start=1):
        item = dict(job)
        existing = str(item.get("result_id", "")).strip()
        if existing:
            result_id = existing
        else:
            result_id = f"{session_id}:{idx}"
        item["result_id"] = result_id
        out.append(item)
    return out


def _build_result_id_index(accepted_jobs: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    for item in accepted_jobs:
        result_id = str(item.get("result_id", "")).strip()
        if not result_id:
            continue
        index[result_id] = {
            "result_id": result_id,
            "job_url": str(item.get("job_url", "")).strip(),
            "title": str(item.get("title", "")).strip(),
            "company": str(item.get("company", "")).strip(),
            "location": str(item.get("location", "")).strip(),
            "site": str(item.get("site", "")).strip(),
            "employer_contacts": item.get("employer_contacts", []),
            "visa_counts": item.get("visa_counts", {}),
            "visas_sponsored": item.get("visas_sponsored", []),
            "eligibility_reasons": item.get("eligibility_reasons", []),
            "confidence_score": item.get("confidence_score"),
            "confidence_model_version": item.get("confidence_model_version"),
        }
    return index


def _resolve_job_reference(
    *,
    user_id: str,
    job_url: str = "",
    result_id: str = "",
    session_id: str = "",
) -> dict[str, Any]:
    direct_url = job_url.strip()
    if direct_url:
        return {
            "job_url": direct_url,
            "title": "",
            "company": "",
            "location": "",
            "site": "",
            "result_id": result_id.strip(),
            "source_session_id": session_id.strip(),
            "employer_contacts": [],
            "visa_counts": {},
            "visas_sponsored": [],
            "eligibility_reasons": [],
            "confidence_score": None,
            "confidence_model_version": None,
        }

    rid = result_id.strip()
    sid = session_id.strip()
    if not rid:
        raise ValueError("job_url or result_id is required")

    if ":" in rid and not sid:
        sid = rid.split(":", 1)[0].strip()
    if not sid:
        raise ValueError("session_id is required when using result_id without a session prefix")

    session_store = _prune_search_sessions(_load_search_sessions())
    sessions = session_store.get("sessions", {})
    session_record = sessions.get(sid)
    if not isinstance(session_record, dict):
        raise ValueError(f"Unknown session_id '{sid}'.")

    query = session_record.get("query", {})
    if not isinstance(query, dict) or str(query.get("user_id", "")).strip() != user_id.strip():
        raise ValueError("session_id does not belong to this user_id.")

    result_index = session_record.get("result_id_index")
    if not isinstance(result_index, dict):
        accepted = session_record.get("accepted_jobs", [])
        if not isinstance(accepted, list):
            accepted = []
        accepted_jobs = [job for job in accepted if isinstance(job, dict)]
        accepted_jobs = _attach_result_ids(sid, accepted_jobs)
        result_index = _build_result_id_index(accepted_jobs)
        session_record["accepted_jobs"] = accepted_jobs
        session_record["result_id_index"] = result_index
        sessions[sid] = session_record
        session_store["sessions"] = sessions
        _save_search_sessions(_prune_search_sessions(session_store))

    if rid in result_index:
        resolved = result_index[rid]
    elif ":" not in rid and f"{sid}:{rid}" in result_index:
        resolved = result_index[f"{sid}:{rid}"]
    else:
        raise ValueError(
            "Unknown result_id for this session. Pass a result_id returned by find_visa_sponsored_jobs."
        )

    resolved_url = str(resolved.get("job_url", "")).strip()
    if not resolved_url:
        raise ValueError("Resolved result_id does not have a job_url. Save/ignore requires a job URL.")
    return {
        **resolved,
        "source_session_id": sid,
    }


def _is_rate_limit_error(exc: Exception) -> bool:
    text = str(exc).lower()
    return any(token in text for token in ("429", "rate limit", "ratelimit", "too many requests"))


def _scrape_jobs_with_backoff(
    *,
    site_name: list[str],
    search_term: str,
    location: str,
    results_wanted: int,
    hours_old: int,
    country_indeed: str,
    retry_window_seconds: int = DEFAULT_RATE_LIMIT_RETRY_WINDOW_SECONDS,
    initial_backoff_seconds: int = DEFAULT_RATE_LIMIT_INITIAL_BACKOFF_SECONDS,
    max_backoff_seconds: int = DEFAULT_RATE_LIMIT_MAX_BACKOFF_SECONDS,
) -> tuple[pd.DataFrame, int, float]:
    attempts = 0
    elapsed_backoff_seconds = 0.0
    backoff_seconds = float(max(1, initial_backoff_seconds))
    retry_window = float(max(0, retry_window_seconds))
    max_backoff = float(max(1, max_backoff_seconds))

    while True:
        attempts += 1
        try:
            raw = scrape_jobs(
                site_name=site_name,
                search_term=search_term,
                location=location,
                results_wanted=results_wanted,
                hours_old=hours_old,
                country_indeed=country_indeed,
            )
            return raw, attempts, elapsed_backoff_seconds
        except Exception as exc:
            if not _is_rate_limit_error(exc):
                raise
            if elapsed_backoff_seconds >= retry_window:
                raise RuntimeError(
                    "Rate limited by upstream job source (429/Too Many Requests). "
                    "Retried for 3 minutes without recovery. Please try again shortly."
                ) from exc

            remaining = retry_window - elapsed_backoff_seconds
            sleep_for = min(backoff_seconds, max_backoff, remaining)
            if sleep_for <= 0:
                raise RuntimeError(
                    "Rate limited by upstream job source (429/Too Many Requests). "
                    "Retried for 3 minutes without recovery. Please try again shortly."
                ) from exc

            time.sleep(sleep_for)
            elapsed_backoff_seconds += float(sleep_for)
            backoff_seconds = min(max_backoff, backoff_seconds * 2)


def _blob_store_path(path: str | None = None) -> str:
    return path or DEFAULT_USER_BLOB_PATH


def _load_user_blob(path: str | None = None) -> dict[str, Any]:
    blob_file = Path(_blob_store_path(path))
    if not blob_file.exists():
        return {"users": {}}
    try:
        data = json.loads(blob_file.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"users": {}}
    if not isinstance(data, dict):
        return {"users": {}}
    users = data.get("users")
    if not isinstance(users, dict):
        data["users"] = {}
    return data


def _save_user_blob(data: dict[str, Any], path: str | None = None) -> None:
    blob_file = Path(_blob_store_path(path))
    blob_file.parent.mkdir(parents=True, exist_ok=True)
    blob_file.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _saved_jobs_store_path(path: str | None = None) -> str:
    return path or DEFAULT_SAVED_JOBS_PATH


def _load_saved_jobs(path: str | None = None) -> dict[str, Any]:
    jobs_file = Path(_saved_jobs_store_path(path))
    if not jobs_file.exists():
        return {"users": {}}
    try:
        data = json.loads(jobs_file.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"users": {}}
    if not isinstance(data, dict):
        return {"users": {}}
    users = data.get("users")
    if not isinstance(users, dict):
        data["users"] = {}
    return data


def _save_saved_jobs(data: dict[str, Any], path: str | None = None) -> None:
    jobs_file = Path(_saved_jobs_store_path(path))
    jobs_file.parent.mkdir(parents=True, exist_ok=True)
    jobs_file.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _normalized_saved_job(raw: Any) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    try:
        saved_job_id = int(raw.get("id", 0))
    except (TypeError, ValueError):
        return None
    if saved_job_id < 1:
        return None
    return {
        "id": saved_job_id,
        "job_url": str(raw.get("job_url", "")).strip(),
        "title": str(raw.get("title", "")).strip(),
        "company": str(raw.get("company", "")).strip(),
        "location": str(raw.get("location", "")).strip(),
        "site": str(raw.get("site", "")).strip(),
        "note": str(raw.get("note", "")).strip(),
        "source_session_id": str(raw.get("source_session_id", "")).strip(),
        "saved_at_utc": str(raw.get("saved_at_utc", "")).strip(),
        "updated_at_utc": str(raw.get("updated_at_utc", "")).strip(),
    }


def _ensure_saved_jobs_entry(data: dict[str, Any], user_id: str) -> dict[str, Any]:
    users = data.setdefault("users", {})
    if not isinstance(users, dict):
        users = {}
        data["users"] = users

    entry = users.get(user_id)
    if not isinstance(entry, dict):
        entry = {}
        users[user_id] = entry

    raw_jobs = entry.get("jobs")
    if not isinstance(raw_jobs, list):
        raw_jobs = []

    jobs = [job for job in (_normalized_saved_job(item) for item in raw_jobs) if job]
    jobs = sorted(jobs, key=lambda job: job["id"])
    entry["jobs"] = jobs

    max_existing_id = max((job["id"] for job in jobs), default=0)
    try:
        next_id = int(entry.get("next_id", 1))
    except (TypeError, ValueError):
        next_id = 1
    if next_id < 1:
        next_id = 1
    if next_id <= max_existing_id:
        next_id = max_existing_id + 1
    entry["next_id"] = next_id
    return entry


def _get_saved_jobs_entry(data: dict[str, Any], user_id: str) -> dict[str, Any] | None:
    users = data.get("users")
    if not isinstance(users, dict):
        return None
    entry = users.get(user_id)
    if not isinstance(entry, dict):
        return None
    raw_jobs = entry.get("jobs")
    if not isinstance(raw_jobs, list):
        raw_jobs = []
    jobs = [job for job in (_normalized_saved_job(item) for item in raw_jobs) if job]
    jobs = sorted(jobs, key=lambda job: job["id"])
    entry["jobs"] = jobs
    return entry


def _ignored_jobs_store_path(path: str | None = None) -> str:
    return path or DEFAULT_IGNORED_JOBS_PATH


def _load_ignored_jobs(path: str | None = None) -> dict[str, Any]:
    jobs_file = Path(_ignored_jobs_store_path(path))
    if not jobs_file.exists():
        return {"users": {}}
    try:
        data = json.loads(jobs_file.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"users": {}}
    if not isinstance(data, dict):
        return {"users": {}}
    users = data.get("users")
    if not isinstance(users, dict):
        data["users"] = {}
    return data


def _save_ignored_jobs(data: dict[str, Any], path: str | None = None) -> None:
    jobs_file = Path(_ignored_jobs_store_path(path))
    jobs_file.parent.mkdir(parents=True, exist_ok=True)
    jobs_file.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _normalized_ignored_job(raw: Any) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    try:
        ignored_job_id = int(raw.get("id", 0))
    except (TypeError, ValueError):
        return None
    if ignored_job_id < 1:
        return None
    return {
        "id": ignored_job_id,
        "job_url": str(raw.get("job_url", "")).strip(),
        "reason": str(raw.get("reason", "")).strip(),
        "source": str(raw.get("source", "")).strip(),
        "ignored_at_utc": str(raw.get("ignored_at_utc", "")).strip(),
        "updated_at_utc": str(raw.get("updated_at_utc", "")).strip(),
    }


def _ensure_ignored_jobs_entry(data: dict[str, Any], user_id: str) -> dict[str, Any]:
    users = data.setdefault("users", {})
    if not isinstance(users, dict):
        users = {}
        data["users"] = users

    entry = users.get(user_id)
    if not isinstance(entry, dict):
        entry = {}
        users[user_id] = entry

    raw_jobs = entry.get("jobs")
    if not isinstance(raw_jobs, list):
        raw_jobs = []

    jobs = [job for job in (_normalized_ignored_job(item) for item in raw_jobs) if job]
    jobs = sorted(jobs, key=lambda job: job["id"])
    entry["jobs"] = jobs

    max_existing_id = max((job["id"] for job in jobs), default=0)
    try:
        next_id = int(entry.get("next_id", 1))
    except (TypeError, ValueError):
        next_id = 1
    if next_id < 1:
        next_id = 1
    if next_id <= max_existing_id:
        next_id = max_existing_id + 1
    entry["next_id"] = next_id
    return entry


def _get_ignored_jobs_entry(data: dict[str, Any], user_id: str) -> dict[str, Any] | None:
    users = data.get("users")
    if not isinstance(users, dict):
        return None
    entry = users.get(user_id)
    if not isinstance(entry, dict):
        return None
    raw_jobs = entry.get("jobs")
    if not isinstance(raw_jobs, list):
        raw_jobs = []
    jobs = [job for job in (_normalized_ignored_job(item) for item in raw_jobs) if job]
    jobs = sorted(jobs, key=lambda job: job["id"])
    entry["jobs"] = jobs
    return entry


def _ignored_job_url_set(user_id: str) -> set[str]:
    uid = user_id.strip()
    if not uid:
        return set()
    data = _load_ignored_jobs()
    entry = _get_ignored_jobs_entry(data, uid)
    if not entry:
        return set()
    return {
        job.get("job_url", "").strip().lower()
        for job in entry["jobs"]
        if job.get("job_url", "").strip()
    }


def _normalized_blob_line(raw: Any) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    try:
        line_id = int(raw.get("id", 0))
    except (TypeError, ValueError):
        return None
    if line_id < 1:
        return None
    return {
        "id": line_id,
        "text": str(raw.get("text", "")).strip(),
        "kind": str(raw.get("kind", "")).strip(),
        "source": str(raw.get("source", "")).strip(),
        "created_at_utc": str(raw.get("created_at_utc", "")).strip(),
    }


def _ensure_user_blob_entry(data: dict[str, Any], user_id: str) -> dict[str, Any]:
    users = data.setdefault("users", {})
    if not isinstance(users, dict):
        users = {}
        data["users"] = users

    entry = users.get(user_id)
    if not isinstance(entry, dict):
        entry = {}
        users[user_id] = entry

    raw_lines = entry.get("lines")
    if not isinstance(raw_lines, list):
        raw_lines = []

    lines = [line for line in (_normalized_blob_line(item) for item in raw_lines) if line]
    lines = sorted(lines, key=lambda line: line["id"])
    entry["lines"] = lines

    max_existing_id = max((line["id"] for line in lines), default=0)
    try:
        next_id = int(entry.get("next_id", 1))
    except (TypeError, ValueError):
        next_id = 1
    if next_id < 1:
        next_id = 1
    if next_id <= max_existing_id:
        next_id = max_existing_id + 1
    entry["next_id"] = next_id
    return entry


def _get_user_blob_entry(data: dict[str, Any], user_id: str) -> dict[str, Any] | None:
    users = data.get("users")
    if not isinstance(users, dict):
        return None
    entry = users.get(user_id)
    if not isinstance(entry, dict):
        return None
    raw_lines = entry.get("lines")
    if not isinstance(raw_lines, list):
        raw_lines = []
    lines = [line for line in (_normalized_blob_line(item) for item in raw_lines) if line]
    lines = sorted(lines, key=lambda line: line["id"])
    entry["lines"] = lines
    return entry


def _get_required_user_visa_types(user_id: str) -> list[str]:
    uid = user_id.strip()
    if not uid:
        raise ValueError(
            "user_id is required. Set visa preferences first using set_user_preferences."
        )
    prefs = _load_user_prefs()
    user = prefs.get(uid)
    if not user:
        raise ValueError(
            f"No saved preferences for user_id='{uid}'. Set visa preferences first using set_user_preferences."
        )
    stored = user.get("preferred_visa_types", [])
    if not stored:
        raise ValueError(
            f"user_id='{uid}' has no preferred_visa_types. Set visa preferences first using set_user_preferences."
        )
    return sorted({_normalize_visa_type(v) for v in stored})


def normalize_company_name(name: str | None) -> str:
    if not name:
        return ""
    text = str(name).strip()
    if text.lower() in {"nan", "none", "null", "na", "n/a"}:
        return ""
    cleaned = re.sub(r"[^A-Za-z0-9\s]", " ", text.lower())
    tokens = [t for t in cleaned.split() if t]
    while tokens and tokens[-1] in LEGAL_SUFFIXES:
        tokens.pop()
    return " ".join(tokens)


def _detect_visa_signals(description: str) -> tuple[bool, bool, list[str]]:
    text = (description or "").lower()
    positive_hits = [p for p in VISA_POSITIVE_PATTERNS if re.search(p, text)]
    negative_hits = [p for p in VISA_NEGATIVE_PATTERNS if re.search(p, text)]
    return bool(positive_hits), bool(negative_hits), positive_hits + negative_hits


def _canonicalize_company_df(df: pd.DataFrame) -> pd.DataFrame:
    rename_map: dict[str, str] = {}
    for canonical, options in CANONICAL_COLUMNS.items():
        for option in options:
            if option in df.columns:
                rename_map[option] = canonical
                break
    cdf = df.rename(columns=rename_map).copy()

    required = [
        "company_tier",
        "company_name",
        "h1b",
        "h1b1_chile",
        "h1b1_singapore",
        "e3_australian",
        "green_card",
    ]
    missing = [c for c in required if c not in cdf.columns]
    if missing:
        raise ValueError(f"Dataset missing required columns: {missing}")

    for col in ("h1b", "h1b1_chile", "h1b1_singapore", "e3_australian", "green_card"):
        cdf[col] = pd.to_numeric(cdf[col], errors="coerce").fillna(0).astype(int)

    cdf["company_name"] = cdf["company_name"].astype(str).str.strip()
    cdf["normalized_company"] = cdf["company_name"].map(normalize_company_name)
    cdf = cdf[cdf["normalized_company"] != ""].copy()

    cdf["total_visas"] = (
        cdf["h1b"]
        + cdf["h1b1_chile"]
        + cdf["h1b1_singapore"]
        + cdf["e3_australian"]
        + cdf["green_card"]
    )

    # Keep strongest sponsor entry when duplicates normalize to same value.
    cdf = cdf.sort_values(["total_visas"], ascending=False).drop_duplicates(
        subset=["normalized_company"], keep="first"
    )
    return cdf


@lru_cache(maxsize=4)
def _load_company_dataset(dataset_path: str) -> pd.DataFrame:
    if not os.path.exists(dataset_path):
        raise FileNotFoundError(
            f"Dataset not found at '{dataset_path}'. Set VISA_COMPANY_DATASET_PATH correctly."
        )
    raw = pd.read_csv(dataset_path)
    return _canonicalize_company_df(raw)


def _ensure_dataset_exists(dataset_path: str) -> None:
    if os.path.exists(dataset_path):
        return
    run_dol_pipeline(output_path=dataset_path, performance_url=DEFAULT_DOL_PERFORMANCE_URL)
    _load_company_dataset.cache_clear()


def _extract_text(row: pd.Series, key: str) -> str:
    value = row.get(key, "")
    if pd.isna(value):
        return ""
    return str(value).strip()


def _job_date(row: pd.Series) -> str | None:
    raw = row.get("date_posted")
    if raw is None or pd.isna(raw):
        return None
    try:
        dt = pd.to_datetime(raw, errors="coerce")
    except Exception:
        return str(raw)
    if pd.isna(dt):
        return str(raw)
    return dt.isoformat()


def _company_stats(company_row: pd.Series) -> CompanySponsorStats:
    return CompanySponsorStats(
        company_name=_extract_text(company_row, "company_name"),
        company_tier=_extract_text(company_row, "company_tier"),
        h1b=int(company_row.get("h1b", 0)),
        h1b1_chile=int(company_row.get("h1b1_chile", 0)),
        h1b1_singapore=int(company_row.get("h1b1_singapore", 0)),
        e3_australian=int(company_row.get("e3_australian", 0)),
        green_card=int(company_row.get("green_card", 0)),
        total_visas=int(company_row.get("total_visas", 0)),
        email_1=_extract_text(company_row, "email_1"),
        contact_1=_extract_text(company_row, "contact_1"),
        contact_1_title=_extract_text(company_row, "contact_1_title"),
        contact_1_phone=_extract_text(company_row, "contact_1_phone"),
    )


def _company_contacts(company_row: pd.Series) -> list[dict[str, str]]:
    contacts: list[dict[str, str]] = []
    for i in (1, 2, 3):
        name = _extract_text(company_row, f"contact_{i}")
        title = _extract_text(company_row, f"contact_{i}_title")
        email = _extract_text(company_row, f"email_{i}")
        phone = _extract_text(company_row, f"contact_{i}_phone")
        if not any([name, title, email, phone]):
            continue
        contacts.append(
            {
                "name": name,
                "title": title,
                "email": email,
                "phone": phone,
            }
        )
    return contacts


def _visa_counts_from_company_row(company_row: pd.Series) -> dict[str, int]:
    counts = {
        "h1b": int(company_row.get("h1b", 0)),
        "h1b1_chile": int(company_row.get("h1b1_chile", 0)),
        "h1b1_singapore": int(company_row.get("h1b1_singapore", 0)),
        "e3_australian": int(company_row.get("e3_australian", 0)),
        "green_card": int(company_row.get("green_card", 0)),
    }
    counts["total_visas"] = sum(counts.values())
    return counts


def _visa_types_from_description(description: str) -> set[str]:
    text = (description or "").lower()
    found: set[str] = set()
    if re.search(r"\bh-?1b\b", text):
        found.add("h1b")
    if re.search(r"\bh-?1b1\b", text) and re.search(r"\bchile\b", text):
        found.add("h1b1_chile")
    if re.search(r"\bh-?1b1\b", text) and re.search(r"\bsingapore\b", text):
        found.add("h1b1_singapore")
    if re.search(r"\be-?3\b", text):
        found.add("e3_australian")
    if re.search(r"\bgreen card\b", text) or re.search(r"\bperm\b", text):
        found.add("green_card")
    return found


def _dedupe_raw_jobs(raw_jobs: pd.DataFrame | None) -> pd.DataFrame:
    if raw_jobs is None or raw_jobs.empty:
        return pd.DataFrame([])

    cdf = raw_jobs.copy()
    if "job_url" in cdf.columns:
        cdf["__dedupe_key"] = cdf["job_url"].fillna("").astype(str).str.strip()
    else:
        cdf["__dedupe_key"] = ""

    fallback_mask = cdf["__dedupe_key"] == ""
    if fallback_mask.any():
        for col in ("title", "company", "location", "site"):
            if col not in cdf.columns:
                cdf[col] = ""
        cdf.loc[fallback_mask, "__dedupe_key"] = (
            cdf.loc[fallback_mask, ["title", "company", "location", "site"]]
            .fillna("")
            .astype(str)
            .agg("|".join, axis=1)
        )

    cdf = cdf.drop_duplicates(subset=["__dedupe_key"], keep="first").drop(columns=["__dedupe_key"])
    return cdf.reset_index(drop=True)


def _find_related_titles_internal(job_title: str, limit: int = 8) -> list[str]:
    base = job_title.strip()
    if not base:
        return []
    normalized = base.lower()
    related: list[str] = []

    for key, values in RELATED_TITLE_HINTS.items():
        if key in normalized or normalized in key:
            related.extend(values)
            break

    if not related:
        if "engineer" in normalized:
            related.extend(
                [
                    base.replace("Engineer", "Developer"),
                    base.replace("Engineer", "Platform Engineer"),
                    base.replace("Engineer", "Systems Engineer"),
                ]
            )
        elif "developer" in normalized:
            related.extend(
                [
                    base.replace("Developer", "Engineer"),
                    base.replace("Developer", "Application Engineer"),
                    base.replace("Developer", "Software Engineer"),
                ]
            )
        elif "architect" in normalized:
            related.extend(
                [
                    base.replace("architect", "engineer").replace("Architect", "Engineer"),
                    f"Senior {base}",
                    f"Lead {base}",
                ]
            )

    if not related:
        related.extend(
            [
                f"Senior {base}",
                f"Lead {base}",
                f"{base} Specialist",
            ]
        )

    candidates = [c.strip() for c in related if c and c.strip()]
    deduped: list[str] = []
    seen: set[str] = {normalized}
    for item in candidates:
        key = item.lower()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
        if len(deduped) >= max(1, limit):
            break
    return deduped


def _build_recovery_suggestions(
    *,
    location: str,
    job_title: str,
    hours_old: int,
    max_scan_results: int,
    accepted_jobs: int,
    returned_jobs: int,
    scan_exhausted: bool,
) -> list[dict[str, Any]]:
    low_yield = returned_jobs == 0 or (accepted_jobs < 10 and scan_exhausted)
    if not low_yield:
        return []

    related_titles = _find_related_titles_internal(job_title, limit=8)
    next_hours_old = min(max(hours_old * 2, hours_old + 168), 24 * 60)
    next_scan_cap = min(max(max_scan_results * 2, max_scan_results + 400), 5000)
    suggestions = [
        {
            "id": "expand_time_window",
            "description": "Broaden the posting time window to find older eligible roles.",
            "proposed_call_args": {"hours_old": int(next_hours_old)},
            "requires_user_confirmation": True,
        },
        {
            "id": "increase_scan_depth",
            "description": "Increase scan depth so the MCP can sift more postings before filtering.",
            "proposed_call_args": {"max_scan_results": int(next_scan_cap)},
            "requires_user_confirmation": True,
        },
    ]

    if related_titles:
        suggestions.insert(
            0,
            {
                "id": "related_titles",
                "description": "Try adjacent job titles that map to similar skill requirements.",
                "options": related_titles,
                "requires_user_confirmation": True,
            },
        )

    if "," in location:
        city = location.split(",", 1)[0].strip()
        suggestions.append(
            {
                "id": "nearby_location",
                "description": "Try a nearby metro location to widen supply.",
                "options": [city, f"{city} Metro Area", location],
                "requires_user_confirmation": True,
            }
        )

    return suggestions


def _evaluate_scraped_jobs(
    raw_jobs: pd.DataFrame,
    sponsor_df: pd.DataFrame,
    desired_visa_types: list[str],
    require_description_signal: bool,
    strictness_mode: str,
) -> list[EvaluatedJob]:
    results: list[EvaluatedJob] = []
    desired_visa_set = set(desired_visa_types)

    for _, row in raw_jobs.iterrows():
        company = _extract_text(row, "company")
        normalized = normalize_company_name(company)
        description = _extract_text(row, "description")
        title = _extract_text(row, "title")
        job_url = _extract_text(row, "job_url")
        site = _extract_text(row, "site")
        job_location = _extract_text(row, "location")

        has_positive, has_negative, hits = _detect_visa_signals(description)

        sponsor_stats = None
        visa_counts: dict[str, int] = {}
        visas_sponsored: list[str] = []
        matches_user_visa_preferences = False
        company_matches_requested_visa = False
        matched_company = False
        contacts: list[dict[str, str]] = []
        if normalized and normalized in sponsor_df.index:
            company_row = sponsor_df.loc[normalized]
            sponsor_stats = _company_stats(company_row)
            visa_counts = _visa_counts_from_company_row(company_row)
            visas_sponsored = [
                VISA_TYPE_LABELS[k]
                for k in ("h1b", "h1b1_chile", "h1b1_singapore", "e3_australian", "green_card")
                if visa_counts.get(k, 0) > 0
            ]
            matched_company = sponsor_stats.total_visas > 0
            contacts = _company_contacts(company_row) if matched_company else []
            if desired_visa_set:
                company_matches_requested_visa = any(visa_counts.get(v, 0) > 0 for v in desired_visa_set)

        rejected_for_negative = has_negative
        desc_visa_types = _visa_types_from_description(description)
        desc_matches_requested_visa = bool(desired_visa_set and desc_visa_types.intersection(desired_visa_set))
        desc_specific_mismatch = bool(
            desired_visa_set
            and desc_visa_types
            and not desc_visa_types.intersection(desired_visa_set)
        )
        desc_generic_sponsorship = bool(has_positive and not desc_visa_types)

        if desired_visa_set:
            if strictness_mode == "strict":
                matches_user_visa_preferences = (
                    company_matches_requested_visa
                    or desc_matches_requested_visa
                )
            else:
                matches_user_visa_preferences = (
                    company_matches_requested_visa
                    or desc_matches_requested_visa
                    or desc_generic_sponsorship
                )
                if desc_specific_mismatch and not company_matches_requested_visa:
                    matches_user_visa_preferences = False

        accept = False
        if not rejected_for_negative:
            if require_description_signal:
                accept = has_positive
            else:
                accept = matched_company or has_positive
            # Always enforce user visa fit so we never return "random sponsorship" jobs.
            if desired_visa_set:
                accept = accept and matches_user_visa_preferences
            # If a specific but different visa is listed, keep strict behavior unless company history proves fit.
            if desc_specific_mismatch and not company_matches_requested_visa:
                accept = False

        if not accept:
            continue

        matched_preference_labels = [
            VISA_TYPE_LABELS[v]
                for v in desired_visa_types
                if visa_counts.get(v, 0) > 0 or v in desc_visa_types
        ]
        eligibility_reasons: list[str] = []
        if strictness_mode == "strict":
            eligibility_reasons.append("Strict visa match mode is active.")
        else:
            eligibility_reasons.append("Balanced visa match mode is active.")
        if matched_company:
            company_visa_summary = ", ".join(
                [
                    f"{VISA_TYPE_LABELS[k]}={visa_counts.get(k, 0)}"
                    for k in ("h1b", "h1b1_chile", "h1b1_singapore", "e3_australian", "green_card")
                    if visa_counts.get(k, 0) > 0
                ]
            )
            if company_visa_summary:
                eligibility_reasons.append(
                    f"Company has historical sponsor filings ({company_visa_summary})."
                )
            else:
                eligibility_reasons.append("Company matched in sponsorship dataset.")
        if has_positive:
            eligibility_reasons.append("Job description mentions visa sponsorship language.")
        if matched_preference_labels:
            eligibility_reasons.append(
                f"Matches requested visa type(s): {', '.join(sorted(set(matched_preference_labels)))}."
            )
        elif strictness_mode == "balanced" and desc_generic_sponsorship:
            eligibility_reasons.append(
                "Accepted in balanced mode using generic sponsorship language."
            )

        contactability_score = 0.0
        if contacts:
            primary_contact = contacts[0]
            if str(primary_contact.get("email", "")).strip():
                contactability_score += 0.6
            if str(primary_contact.get("phone", "")).strip():
                contactability_score += 0.25
            if str(primary_contact.get("name", "")).strip():
                contactability_score += 0.1
            if str(primary_contact.get("title", "")).strip():
                contactability_score += 0.05
        contactability_score = min(1.0, round(contactability_score, 2))

        confidence_score = 0.0
        if matched_company:
            confidence_score += 0.65
        if has_positive:
            confidence_score += 0.20
        if matches_user_visa_preferences:
            confidence_score += 0.10
        if contactability_score > 0:
            confidence_score += 0.05
        confidence_score = min(1.0, round(confidence_score, 2))

        results.append(
            EvaluatedJob(
                title=title,
                company=company,
                location=job_location,
                site=site,
                date_posted=_job_date(row),
                job_url=job_url,
                description_snippet=description[:350],
                matched_via_company_dataset=matched_company,
                matched_via_job_description=has_positive,
                rejected_for_no_sponsorship_phrase=rejected_for_negative,
                sponsorship_reasons=hits,
                employer_contacts=contacts,
                visa_counts=visa_counts,
                visas_sponsored=visas_sponsored,
                matches_user_visa_preferences=matches_user_visa_preferences,
                eligibility_reasons=eligibility_reasons,
                confidence_score=confidence_score,
                confidence_model_version=CONFIDENCE_MODEL_VERSION,
                contactability_score=contactability_score,
                sponsor_stats=asdict(sponsor_stats) if sponsor_stats else None,
            )
        )

    # Rank by sponsorship confidence first, then contactability to prioritize outreach-friendly roles.
    return sorted(
        results,
        key=lambda job: (job.confidence_score, job.contactability_score),
        reverse=True,
    )


@mcp.tool()
def get_mcp_capabilities() -> dict[str, Any]:
    """Return machine-readable MCP capability metadata for agents."""
    return {
        "server": "visa-jobs-mcp",
        "version": __version__,
        "capabilities_schema_version": CAPABILITIES_SCHEMA_VERSION,
        "confidence_model_version": CONFIDENCE_MODEL_VERSION,
        "design_decisions": {
            "llm_runtime_inside_mcp": False,
            "llm_api_keys_required_by_mcp": False,
            "agent_is_reasoning_layer": True,
            "proxies_used": False,
            "free_forever": True,
            "license": "MIT",
            "supported_job_sites": sorted(SUPPORTED_SITES),
            "strict_user_visa_match": True,
            "strictness_modes_supported": sorted(SUPPORTED_STRICTNESS_MODES),
            "search_sessions_local_persistence": True,
            "saved_jobs_local_persistence": True,
            "ignored_jobs_local_persistence": True,
            "rate_limit_backoff_retries": True,
        },
        "required_before_search": {
            "tool": "set_user_preferences",
            "required_fields": ["user_id", "preferred_visa_types"],
        },
        "defaults": {
            "search_session_ttl_seconds": int(DEFAULT_SEARCH_SESSION_TTL_SECONDS),
            "max_search_sessions_per_user": int(DEFAULT_MAX_SEARCH_SESSIONS_PER_USER),
            "scan_multiplier": int(DEFAULT_SCAN_MULTIPLIER),
            "max_scan_results": int(DEFAULT_MAX_SCAN_RESULTS),
            "strictness_mode": "strict",
            "dataset_stale_after_days": int(DEFAULT_DATASET_STALE_AFTER_DAYS),
            "rate_limit_retry_window_seconds": int(DEFAULT_RATE_LIMIT_RETRY_WINDOW_SECONDS),
            "rate_limit_initial_backoff_seconds": int(DEFAULT_RATE_LIMIT_INITIAL_BACKOFF_SECONDS),
            "rate_limit_max_backoff_seconds": int(DEFAULT_RATE_LIMIT_MAX_BACKOFF_SECONDS),
        },
        "tools": [
            {"name": "set_user_preferences", "required_inputs": ["user_id", "preferred_visa_types"]},
            {"name": "set_user_constraints", "required_inputs": ["user_id"]},
            {"name": "get_user_preferences", "required_inputs": ["user_id"]},
            {"name": "get_user_readiness", "required_inputs": ["user_id"]},
            {"name": "find_related_titles", "required_inputs": ["job_title"]},
            {"name": "add_user_memory_line", "required_inputs": ["user_id", "content"]},
            {"name": "query_user_memory_blob", "required_inputs": ["user_id"]},
            {"name": "delete_user_memory_line", "required_inputs": ["user_id", "line_id"]},
            {
                "name": "save_job_for_later",
                "required_inputs": ["user_id"],
                "optional_inputs": ["job_url", "result_id", "session_id"],
            },
            {"name": "list_saved_jobs", "required_inputs": ["user_id"]},
            {"name": "delete_saved_job", "required_inputs": ["user_id", "saved_job_id"]},
            {
                "name": "ignore_job",
                "required_inputs": ["user_id"],
                "optional_inputs": ["job_url", "result_id", "session_id"],
            },
            {"name": "list_ignored_jobs", "required_inputs": ["user_id"]},
            {"name": "unignore_job", "required_inputs": ["user_id", "ignored_job_id"]},
            {"name": "clear_search_session", "required_inputs": ["user_id"]},
            {"name": "export_user_data", "required_inputs": ["user_id"]},
            {"name": "delete_user_data", "required_inputs": ["user_id", "confirm"]},
            {"name": "get_best_contact_strategy", "required_inputs": ["user_id"]},
            {"name": "generate_outreach_message", "required_inputs": ["user_id"]},
            {
                "name": "find_visa_sponsored_jobs",
                "required_inputs": ["location", "job_title", "user_id"],
                "optional_inputs": [
                    "offset",
                    "max_returned",
                    "session_id",
                    "refresh_session",
                    "auto_expand_scan",
                    "scan_multiplier",
                    "max_scan_results",
                    "strictness_mode",
                ],
            },
            {"name": "discover_latest_dol_disclosure_urls", "required_inputs": []},
            {"name": "run_internal_dol_pipeline", "required_inputs": []},
            {"name": "refresh_company_dataset_cache", "required_inputs": []},
        ],
        "search_response_fields_for_agents": [
            "jobs[].result_id",
            "jobs[].job_url",
            "jobs[].employer_contacts",
            "jobs[].visa_counts",
            "jobs[].visas_sponsored",
            "jobs[].eligibility_reasons",
            "jobs[].confidence_score",
            "jobs[].confidence_model_version",
            "jobs[].contactability_score",
            "jobs[].matched_via_company_dataset",
            "jobs[].matched_via_job_description",
            "jobs[].matches_user_visa_preferences",
            "search_session",
            "stats",
            "agent_guidance",
            "pagination",
            "dataset_freshness",
            "recovery_suggestions",
        ],
        "pagination_contract": {
            "offset_model": "offset is applied to accepted jobs, not raw scraped jobs",
            "next_step": "use pagination.next_offset to request the next page",
            "scan_behavior": "server can increase raw scan depth when auto_expand_scan=true",
            "session_behavior": "pass search_session.session_id for stable paging without redundant rescans",
            "result_id_aliases": "use jobs[].result_id in save_job_for_later/ignore_job to avoid URL copy friction",
        },
        "rate_limit_contract": {
            "retry_behavior": "automatic exponential backoff on rate-limit errors (429/Too Many Requests)",
            "max_retry_window_seconds": int(DEFAULT_RATE_LIMIT_RETRY_WINDOW_SECONDS),
            "failure_message": "asks agent to retry shortly when the retry window is exhausted",
        },
        "deprecations": [
            {
                "name": "build_company_dataset_from_dol_disclosures",
                "replacement": "run_internal_dol_pipeline",
                "status": "soft_deprecated",
            }
        ],
        "paths": {
            "dataset_default": DEFAULT_DATASET_PATH,
            "pipeline_manifest_default": DEFAULT_DOL_MANIFEST_PATH,
            "user_preferences_default": DEFAULT_USER_PREFS_PATH,
            "user_memory_blob_default": DEFAULT_USER_BLOB_PATH,
            "search_session_store_default": DEFAULT_SEARCH_SESSION_PATH,
            "saved_jobs_default": DEFAULT_SAVED_JOBS_PATH,
            "ignored_jobs_default": DEFAULT_IGNORED_JOBS_PATH,
        },
    }


@mcp.tool()
def discover_latest_dol_disclosure_urls(
    performance_url: str = DEFAULT_DOL_PERFORMANCE_URL,
) -> dict[str, Any]:
    """Discover latest LCA and PERM disclosure xlsx URLs from DOL performance page."""
    return pipeline_discover_latest_dol_disclosure_urls(performance_url=performance_url)


@mcp.tool()
def build_company_dataset_from_dol_disclosures(
    output_path: str = DEFAULT_DATASET_PATH,
    lca_path_or_url: str = "",
    perm_path_or_url: str = "",
    performance_url: str = DEFAULT_DOL_PERFORMANCE_URL,
) -> dict[str, Any]:
    """Build canonical sponsor-company dataset from DOL LCA + PERM disclosure files."""
    result = run_dol_pipeline(
        output_path=output_path,
        lca_path_or_url=lca_path_or_url,
        perm_path_or_url=perm_path_or_url,
        performance_url=performance_url,
    )

    _load_company_dataset.cache_clear()

    return {
        "output_path": result.output_path,
        "rows_written": result.rows_written,
        "lca_source": result.lca_source,
        "perm_source": result.perm_source,
        "lca_employer_col": result.lca_employer_col,
        "lca_visa_col": result.lca_visa_col,
        "perm_employer_col": result.perm_employer_col,
        "discovered_from_performance_url": result.discovered_from_performance_url,
        "manifest_path": result.manifest_path,
        "run_at_utc": result.run_at_utc,
    }


@mcp.tool()
def run_internal_dol_pipeline(
    output_path: str = DEFAULT_DATASET_PATH,
    lca_path_or_url: str = "",
    perm_path_or_url: str = "",
    performance_url: str = DEFAULT_DOL_PERFORMANCE_URL,
) -> dict[str, Any]:
    """Internal pipeline: discover/pull DOL data and rebuild canonical sponsorship CSV."""
    result = run_dol_pipeline(
        output_path=output_path,
        lca_path_or_url=lca_path_or_url,
        perm_path_or_url=perm_path_or_url,
        performance_url=performance_url,
    )
    _load_company_dataset.cache_clear()
    return {
        "output_path": result.output_path,
        "rows_written": result.rows_written,
        "lca_source": result.lca_source,
        "perm_source": result.perm_source,
        "manifest_path": result.manifest_path,
        "run_at_utc": result.run_at_utc,
    }


@mcp.tool()
def set_user_preferences(
    user_id: str,
    preferred_visa_types: list[str],
) -> dict[str, Any]:
    """Save persistent user preferences for visa search filtering."""
    if not user_id.strip():
        raise ValueError("user_id is required")
    normalized_types = sorted({_normalize_visa_type(v) for v in preferred_visa_types})
    prefs = _load_user_prefs()
    existing = prefs.get(user_id, {})
    if not isinstance(existing, dict):
        existing = {}
    existing["preferred_visa_types"] = normalized_types
    prefs[user_id] = existing
    _save_user_prefs(prefs)
    return {"user_id": user_id, "preferences": prefs[user_id], "path": DEFAULT_USER_PREFS_PATH}


@mcp.tool()
def set_user_constraints(
    user_id: str,
    days_remaining: int | None = None,
    work_modes: list[str] | None = None,
    willing_to_relocate: bool | None = None,
) -> dict[str, Any]:
    """Save optional onboarding constraints for downstream agent orchestration."""
    uid = user_id.strip()
    if not uid:
        raise ValueError("user_id is required")

    prefs = _load_user_prefs()
    user = prefs.get(uid, {})
    if not isinstance(user, dict):
        user = {}
    constraints = user.get("constraints", {})
    if not isinstance(constraints, dict):
        constraints = {}

    if days_remaining is not None:
        try:
            parsed_days = int(days_remaining)
        except (TypeError, ValueError) as exc:
            raise ValueError("days_remaining must be an integer when provided") from exc
        if parsed_days < 0:
            raise ValueError("days_remaining must be >= 0")
        constraints["days_remaining"] = parsed_days

    if work_modes is not None:
        normalized_modes = sorted({_normalize_work_mode(mode) for mode in work_modes})
        constraints["work_modes"] = normalized_modes

    if willing_to_relocate is not None:
        constraints["willing_to_relocate"] = bool(willing_to_relocate)

    constraints["updated_at_utc"] = _utcnow_iso()
    user["constraints"] = constraints
    prefs[uid] = user
    _save_user_prefs(prefs)

    return {
        "user_id": uid,
        "constraints": constraints,
        "path": DEFAULT_USER_PREFS_PATH,
    }


@mcp.tool()
def get_user_preferences(user_id: str) -> dict[str, Any]:
    """Get persisted user preferences."""
    if not user_id.strip():
        raise ValueError("user_id is required")
    prefs = _load_user_prefs()
    return {
        "user_id": user_id,
        "preferences": prefs.get(user_id, {}),
        "path": DEFAULT_USER_PREFS_PATH,
    }


@mcp.tool()
def get_user_readiness(
    user_id: str,
    dataset_path: str = DEFAULT_DATASET_PATH,
    manifest_path: str = "",
) -> dict[str, Any]:
    """Return setup/readiness status so agents know what to ask next."""
    uid = user_id.strip()
    if not uid:
        raise ValueError("user_id is required")

    prefs = _load_user_prefs().get(uid, {})
    if not isinstance(prefs, dict):
        prefs = {}
    preferred_visa_types = prefs.get("preferred_visa_types", [])
    has_preferences = bool(preferred_visa_types)
    constraints = prefs.get("constraints", {}) if isinstance(prefs, dict) else {}
    if not isinstance(constraints, dict):
        constraints = {}

    user_blob_entry = _get_user_blob_entry(_load_user_blob(), uid) or {}
    memory_lines_count = len(user_blob_entry.get("lines", []))

    saved_jobs_entry = _get_saved_jobs_entry(_load_saved_jobs(), uid) or {}
    saved_jobs_count = len(saved_jobs_entry.get("jobs", []))

    ignored_jobs_entry = _get_ignored_jobs_entry(_load_ignored_jobs(), uid) or {}
    ignored_jobs_count = len(ignored_jobs_entry.get("jobs", []))

    dataset_exists = os.path.exists(dataset_path)
    manifest_path_resolved = manifest_path.strip() or DEFAULT_DOL_MANIFEST_PATH
    freshness = _dataset_freshness(
        dataset_path=dataset_path,
        manifest_path=manifest_path_resolved,
        stale_after_days=DEFAULT_DATASET_STALE_AFTER_DAYS,
    )
    action_items: list[str] = []
    if not has_preferences:
        action_items.append(
            "Call set_user_preferences first (required before find_visa_sponsored_jobs)."
        )
    if not dataset_exists:
        action_items.append(
            "Dataset CSV missing; call run_internal_dol_pipeline or rely on first-search auto-bootstrap."
        )
    if freshness["dataset_exists"] and freshness["is_stale"]:
        action_items.append(
            "Dataset may be stale; run run_internal_dol_pipeline to refresh sponsorship evidence."
        )

    return {
        "user_id": uid,
        "readiness": {
            "ready_for_search": bool(has_preferences),
            "has_preferences": has_preferences,
            "preferred_visa_types": preferred_visa_types,
            "dataset_exists": dataset_exists,
            "constraints": constraints,
            "memory_lines_count": int(memory_lines_count),
            "saved_jobs_count": int(saved_jobs_count),
            "ignored_jobs_count": int(ignored_jobs_count),
        },
        "dataset_freshness": freshness,
        "paths": {
            "dataset_path": dataset_path,
            "manifest_path": manifest_path_resolved,
            "preferences_path": DEFAULT_USER_PREFS_PATH,
            "memory_blob_path": DEFAULT_USER_BLOB_PATH,
            "saved_jobs_path": DEFAULT_SAVED_JOBS_PATH,
            "ignored_jobs_path": DEFAULT_IGNORED_JOBS_PATH,
        },
        "next_actions": action_items,
    }


@mcp.tool()
def find_related_titles(job_title: str, limit: int = 8) -> dict[str, Any]:
    """Return adjacent job titles for low-yield recovery flows."""
    title = job_title.strip()
    if not title:
        raise ValueError("job_title is required")
    safe_limit = max(1, min(limit, 20))
    related = _find_related_titles_internal(title, limit=safe_limit)
    return {
        "job_title": title,
        "related_titles": related,
        "count": len(related),
    }


@mcp.tool()
def get_best_contact_strategy(
    user_id: str,
    job_url: str = "",
    result_id: str = "",
    session_id: str = "",
) -> dict[str, Any]:
    """Suggest immediate outreach strategy based on available employer contact data."""
    uid = user_id.strip()
    if not uid:
        raise ValueError("user_id is required")

    resolved = _resolve_job_reference(
        user_id=uid,
        job_url=job_url,
        result_id=result_id,
        session_id=session_id,
    )
    contacts = resolved.get("employer_contacts", [])
    if not isinstance(contacts, list):
        contacts = []

    primary = contacts[0] if contacts else {}
    primary_name = str(primary.get("name", "")).strip()
    primary_title = str(primary.get("title", "")).strip()
    primary_email = str(primary.get("email", "")).strip()
    primary_phone = str(primary.get("phone", "")).strip()

    if primary_email:
        channel = "email"
        strategy_steps = [
            "Send a short intro email referencing role fit and visa type.",
            "Attach or link a targeted resume with matching skills.",
            "Follow up once in 48 hours if no response.",
        ]
    elif primary_phone:
        channel = "phone"
        strategy_steps = [
            "Call during business hours and ask for recruiter/hiring manager routing.",
            "Leave a concise voicemail with callback and role context.",
            "Follow with a short email or LinkedIn note if available.",
        ]
    else:
        channel = "application_plus_linkedin"
        strategy_steps = [
            "Submit the application immediately using the job URL.",
            "Find the recruiter/hiring manager on LinkedIn and send a short intro note.",
            "Track this role in saved jobs and follow up in 3-5 days.",
        ]

    return {
        "user_id": uid,
        "job_reference": {
            "result_id": resolved.get("result_id"),
            "source_session_id": resolved.get("source_session_id"),
            "job_url": resolved.get("job_url"),
            "title": resolved.get("title"),
            "company": resolved.get("company"),
        },
        "recommended_channel": channel,
        "primary_contact": {
            "name": primary_name,
            "title": primary_title,
            "email": primary_email,
            "phone": primary_phone,
        },
        "strategy_steps": strategy_steps,
        "non_legal_disclaimer": "Guidance is informational only and not legal advice.",
    }


@mcp.tool()
def generate_outreach_message(
    user_id: str,
    job_url: str = "",
    result_id: str = "",
    session_id: str = "",
    recipient_name: str = "",
    recipient_title: str = "",
    visa_type: str = "",
    tone: str = "professional",
) -> dict[str, Any]:
    """Generate a concise outreach template for a job contact."""
    uid = user_id.strip()
    if not uid:
        raise ValueError("user_id is required")

    resolved = _resolve_job_reference(
        user_id=uid,
        job_url=job_url,
        result_id=result_id,
        session_id=session_id,
    )
    prefs = _load_user_prefs().get(uid, {})
    preferred = []
    if isinstance(prefs, dict):
        preferred = prefs.get("preferred_visa_types", [])
    preferred_labels: list[str] = []
    for value in preferred:
        try:
            normalized = _normalize_visa_type(value)
        except ValueError:
            normalized = str(value).strip().lower()
        preferred_labels.append(VISA_TYPE_LABELS.get(normalized, str(value)))
    visa_label = visa_type.strip() or (preferred_labels[0] if preferred_labels else "work visa sponsorship")
    to_name = recipient_name.strip() or "Hiring Team"
    to_title = recipient_title.strip()
    role = str(resolved.get("title", "")).strip() or "this role"
    company = str(resolved.get("company", "")).strip() or "your team"
    url = str(resolved.get("job_url", "")).strip()

    greeting = f"Hi {to_name},"
    intro = f"I’m reaching out about {role} at {company} ({url})."
    fit = "I align strongly with the role requirements and can contribute quickly."
    visa_line = f"I am specifically looking for opportunities that support {visa_label}."
    ask = (
        "If this role is still open, I’d appreciate the chance to share my background "
        "and discuss fit."
    )
    close = "Thanks for your time,\n[Your Name]"

    if tone.strip().lower() == "urgent":
        ask = (
            "Given timing constraints on my side, a quick conversation would be very helpful "
            "if sponsorship is possible."
        )

    body = "\n".join(
        [
            greeting,
            "",
            intro,
            fit,
            visa_line,
            ask,
            "",
            close,
        ]
    )

    return {
        "user_id": uid,
        "job_reference": {
            "result_id": resolved.get("result_id"),
            "source_session_id": resolved.get("source_session_id"),
            "job_url": url,
            "title": role,
            "company": company,
        },
        "recipient": {
            "name": to_name,
            "title": to_title,
        },
        "tone": tone.strip() or "professional",
        "subject": f"Interest in {role} ({visa_label})",
        "message": body,
        "non_legal_disclaimer": "Template guidance only; not legal advice.",
    }


@mcp.tool()
def add_user_memory_line(
    user_id: str,
    content: str,
    kind: str = "",
    source: str = "",
) -> dict[str, Any]:
    """Append one line to a user's local memory blob store."""
    uid = user_id.strip()
    if not uid:
        raise ValueError("user_id is required")
    text = content.strip()
    if not text:
        raise ValueError("content is required")

    data = _load_user_blob()
    entry = _ensure_user_blob_entry(data, uid)
    line_id = int(entry["next_id"])
    line = {
        "id": line_id,
        "text": text,
        "kind": kind.strip(),
        "source": source.strip(),
        "created_at_utc": _utcnow_iso(),
    }
    entry["lines"].append(line)
    entry["next_id"] = line_id + 1
    entry["updated_at_utc"] = line["created_at_utc"]
    _save_user_blob(data)
    return {
        "user_id": uid,
        "added_line": line,
        "total_lines": len(entry["lines"]),
        "path": DEFAULT_USER_BLOB_PATH,
    }


@mcp.tool()
def query_user_memory_blob(
    user_id: str,
    query: str = "",
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    """Query a user's local memory lines with optional substring matching."""
    uid = user_id.strip()
    if not uid:
        raise ValueError("user_id is required")

    safe_limit = max(1, min(limit, 200))
    safe_offset = max(offset, 0)
    query_text = query.strip().lower()

    data = _load_user_blob()
    entry = _get_user_blob_entry(data, uid)
    if not entry:
        return {
            "user_id": uid,
            "query": query,
            "offset": safe_offset,
            "limit": safe_limit,
            "total_lines": 0,
            "total_matches": 0,
            "returned_lines": 0,
            "lines": [],
            "path": DEFAULT_USER_BLOB_PATH,
        }

    lines = sorted(entry["lines"], key=lambda line: line["id"], reverse=True)
    if query_text:
        lines = [
            line
            for line in lines
            if query_text
            in " ".join([line.get("text", ""), line.get("kind", ""), line.get("source", "")]).lower()
        ]
    total_matches = len(lines)
    page = lines[safe_offset : safe_offset + safe_limit]
    return {
        "user_id": uid,
        "query": query,
        "offset": safe_offset,
        "limit": safe_limit,
        "total_lines": len(entry["lines"]),
        "total_matches": total_matches,
        "returned_lines": len(page),
        "lines": page,
        "path": DEFAULT_USER_BLOB_PATH,
    }


@mcp.tool()
def delete_user_memory_line(user_id: str, line_id: int) -> dict[str, Any]:
    """Delete one line from a user's local memory blob store by id."""
    uid = user_id.strip()
    if not uid:
        raise ValueError("user_id is required")
    try:
        target_line_id = int(line_id)
    except (TypeError, ValueError) as exc:
        raise ValueError("line_id must be an integer") from exc
    if target_line_id < 1:
        raise ValueError("line_id must be a positive integer")

    data = _load_user_blob()
    entry = _get_user_blob_entry(data, uid)
    if not entry:
        return {
            "user_id": uid,
            "line_id": target_line_id,
            "deleted": False,
            "deleted_line": None,
            "total_lines": 0,
            "path": DEFAULT_USER_BLOB_PATH,
        }

    remaining: list[dict[str, Any]] = []
    deleted_line: dict[str, Any] | None = None
    for line in entry["lines"]:
        if deleted_line is None and line["id"] == target_line_id:
            deleted_line = line
            continue
        remaining.append(line)

    if deleted_line is None:
        return {
            "user_id": uid,
            "line_id": target_line_id,
            "deleted": False,
            "deleted_line": None,
            "total_lines": len(entry["lines"]),
            "path": DEFAULT_USER_BLOB_PATH,
        }

    entry["lines"] = remaining
    entry["updated_at_utc"] = _utcnow_iso()
    _save_user_blob(data)
    return {
        "user_id": uid,
        "line_id": target_line_id,
        "deleted": True,
        "deleted_line": deleted_line,
        "total_lines": len(remaining),
        "path": DEFAULT_USER_BLOB_PATH,
    }


@mcp.tool()
def save_job_for_later(
    user_id: str,
    job_url: str = "",
    result_id: str = "",
    session_id: str = "",
    title: str = "",
    company: str = "",
    location: str = "",
    site: str = "",
    note: str = "",
    source_session_id: str = "",
) -> dict[str, Any]:
    """Save or update a job bookmark for a user."""
    uid = user_id.strip()
    if not uid:
        raise ValueError("user_id is required")

    resolved = _resolve_job_reference(
        user_id=uid,
        job_url=job_url,
        result_id=result_id,
        session_id=session_id,
    )
    clean_job_url = str(resolved.get("job_url", "")).strip()

    data = _load_saved_jobs()
    entry = _ensure_saved_jobs_entry(data, uid)
    now_utc = _utcnow_iso()

    if not title.strip():
        title = str(resolved.get("title", "")).strip()
    if not company.strip():
        company = str(resolved.get("company", "")).strip()
    if not location.strip():
        location = str(resolved.get("location", "")).strip()
    if not site.strip():
        site = str(resolved.get("site", "")).strip()
    if not source_session_id.strip():
        source_session_id = str(resolved.get("source_session_id", "")).strip()

    normalized_incoming_url = clean_job_url.lower()
    for saved in entry["jobs"]:
        if saved.get("job_url", "").strip().lower() != normalized_incoming_url:
            continue
        # Upsert behavior by URL avoids noisy duplicates for the same job.
        if title.strip():
            saved["title"] = title.strip()
        if company.strip():
            saved["company"] = company.strip()
        if location.strip():
            saved["location"] = location.strip()
        if site.strip():
            saved["site"] = site.strip()
        if note.strip():
            saved["note"] = note.strip()
        if source_session_id.strip():
            saved["source_session_id"] = source_session_id.strip()
        saved["updated_at_utc"] = now_utc
        _save_saved_jobs(data)
        return {
            "user_id": uid,
            "action": "updated_existing",
            "saved_job": saved,
            "resolved_result_id": str(resolved.get("result_id", "")).strip(),
            "total_saved_jobs": len(entry["jobs"]),
            "path": DEFAULT_SAVED_JOBS_PATH,
        }

    saved_job_id = int(entry["next_id"])
    saved_job = {
        "id": saved_job_id,
        "job_url": clean_job_url,
        "title": title.strip(),
        "company": company.strip(),
        "location": location.strip(),
        "site": site.strip(),
        "note": note.strip(),
        "source_session_id": source_session_id.strip(),
        "saved_at_utc": now_utc,
        "updated_at_utc": now_utc,
    }
    entry["jobs"].append(saved_job)
    entry["next_id"] = saved_job_id + 1
    entry["updated_at_utc"] = now_utc
    _save_saved_jobs(data)
    return {
        "user_id": uid,
        "action": "saved_new",
        "saved_job": saved_job,
        "resolved_result_id": str(resolved.get("result_id", "")).strip(),
        "total_saved_jobs": len(entry["jobs"]),
        "path": DEFAULT_SAVED_JOBS_PATH,
    }


@mcp.tool()
def list_saved_jobs(
    user_id: str,
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    """List saved jobs for a user (latest-first)."""
    uid = user_id.strip()
    if not uid:
        raise ValueError("user_id is required")
    safe_limit = max(1, min(limit, 200))
    safe_offset = max(offset, 0)

    data = _load_saved_jobs()
    entry = _get_saved_jobs_entry(data, uid)
    if not entry:
        return {
            "user_id": uid,
            "offset": safe_offset,
            "limit": safe_limit,
            "total_saved_jobs": 0,
            "returned_jobs": 0,
            "jobs": [],
            "path": DEFAULT_SAVED_JOBS_PATH,
        }

    ordered_jobs = sorted(entry["jobs"], key=lambda job: job["id"], reverse=True)
    page = ordered_jobs[safe_offset : safe_offset + safe_limit]
    return {
        "user_id": uid,
        "offset": safe_offset,
        "limit": safe_limit,
        "total_saved_jobs": len(ordered_jobs),
        "returned_jobs": len(page),
        "jobs": page,
        "path": DEFAULT_SAVED_JOBS_PATH,
    }


@mcp.tool()
def delete_saved_job(user_id: str, saved_job_id: int) -> dict[str, Any]:
    """Delete one saved job by id."""
    uid = user_id.strip()
    if not uid:
        raise ValueError("user_id is required")
    try:
        target_id = int(saved_job_id)
    except (TypeError, ValueError) as exc:
        raise ValueError("saved_job_id must be an integer") from exc
    if target_id < 1:
        raise ValueError("saved_job_id must be a positive integer")

    data = _load_saved_jobs()
    entry = _get_saved_jobs_entry(data, uid)
    if not entry:
        return {
            "user_id": uid,
            "saved_job_id": target_id,
            "deleted": False,
            "deleted_job": None,
            "total_saved_jobs": 0,
            "path": DEFAULT_SAVED_JOBS_PATH,
        }

    remaining: list[dict[str, Any]] = []
    deleted_job: dict[str, Any] | None = None
    for job in entry["jobs"]:
        if deleted_job is None and job["id"] == target_id:
            deleted_job = job
            continue
        remaining.append(job)

    if deleted_job is None:
        return {
            "user_id": uid,
            "saved_job_id": target_id,
            "deleted": False,
            "deleted_job": None,
            "total_saved_jobs": len(entry["jobs"]),
            "path": DEFAULT_SAVED_JOBS_PATH,
        }

    entry["jobs"] = remaining
    entry["updated_at_utc"] = _utcnow_iso()
    _save_saved_jobs(data)
    return {
        "user_id": uid,
        "saved_job_id": target_id,
        "deleted": True,
        "deleted_job": deleted_job,
        "total_saved_jobs": len(remaining),
        "path": DEFAULT_SAVED_JOBS_PATH,
    }


@mcp.tool()
def ignore_job(
    user_id: str,
    job_url: str = "",
    result_id: str = "",
    session_id: str = "",
    reason: str = "",
    source: str = "",
) -> dict[str, Any]:
    """Ignore a job URL so future search results exclude it."""
    uid = user_id.strip()
    if not uid:
        raise ValueError("user_id is required")

    resolved = _resolve_job_reference(
        user_id=uid,
        job_url=job_url,
        result_id=result_id,
        session_id=session_id,
    )
    clean_job_url = str(resolved.get("job_url", "")).strip()
    if not source.strip():
        source = str(resolved.get("source_session_id", "")).strip()

    data = _load_ignored_jobs()
    entry = _ensure_ignored_jobs_entry(data, uid)
    now_utc = _utcnow_iso()
    normalized_incoming_url = clean_job_url.lower()

    for ignored in entry["jobs"]:
        if ignored.get("job_url", "").strip().lower() != normalized_incoming_url:
            continue
        if reason.strip():
            ignored["reason"] = reason.strip()
        if source.strip():
            ignored["source"] = source.strip()
        ignored["updated_at_utc"] = now_utc
        _save_ignored_jobs(data)
        return {
            "user_id": uid,
            "action": "updated_existing",
            "ignored_job": ignored,
            "resolved_result_id": str(resolved.get("result_id", "")).strip(),
            "total_ignored_jobs": len(entry["jobs"]),
            "path": DEFAULT_IGNORED_JOBS_PATH,
        }

    ignored_job_id = int(entry["next_id"])
    ignored_job = {
        "id": ignored_job_id,
        "job_url": clean_job_url,
        "reason": reason.strip(),
        "source": source.strip(),
        "ignored_at_utc": now_utc,
        "updated_at_utc": now_utc,
    }
    entry["jobs"].append(ignored_job)
    entry["next_id"] = ignored_job_id + 1
    entry["updated_at_utc"] = now_utc
    _save_ignored_jobs(data)
    return {
        "user_id": uid,
        "action": "ignored_new",
        "ignored_job": ignored_job,
        "resolved_result_id": str(resolved.get("result_id", "")).strip(),
        "total_ignored_jobs": len(entry["jobs"]),
        "path": DEFAULT_IGNORED_JOBS_PATH,
    }


@mcp.tool()
def list_ignored_jobs(
    user_id: str,
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    """List ignored job URLs for a user (latest-first)."""
    uid = user_id.strip()
    if not uid:
        raise ValueError("user_id is required")
    safe_limit = max(1, min(limit, 200))
    safe_offset = max(offset, 0)

    data = _load_ignored_jobs()
    entry = _get_ignored_jobs_entry(data, uid)
    if not entry:
        return {
            "user_id": uid,
            "offset": safe_offset,
            "limit": safe_limit,
            "total_ignored_jobs": 0,
            "returned_jobs": 0,
            "jobs": [],
            "path": DEFAULT_IGNORED_JOBS_PATH,
        }

    ordered_jobs = sorted(entry["jobs"], key=lambda job: job["id"], reverse=True)
    page = ordered_jobs[safe_offset : safe_offset + safe_limit]
    return {
        "user_id": uid,
        "offset": safe_offset,
        "limit": safe_limit,
        "total_ignored_jobs": len(ordered_jobs),
        "returned_jobs": len(page),
        "jobs": page,
        "path": DEFAULT_IGNORED_JOBS_PATH,
    }


@mcp.tool()
def unignore_job(user_id: str, ignored_job_id: int) -> dict[str, Any]:
    """Remove one ignored job URL by id."""
    uid = user_id.strip()
    if not uid:
        raise ValueError("user_id is required")
    try:
        target_id = int(ignored_job_id)
    except (TypeError, ValueError) as exc:
        raise ValueError("ignored_job_id must be an integer") from exc
    if target_id < 1:
        raise ValueError("ignored_job_id must be a positive integer")

    data = _load_ignored_jobs()
    entry = _get_ignored_jobs_entry(data, uid)
    if not entry:
        return {
            "user_id": uid,
            "ignored_job_id": target_id,
            "deleted": False,
            "deleted_job": None,
            "total_ignored_jobs": 0,
            "path": DEFAULT_IGNORED_JOBS_PATH,
        }

    remaining: list[dict[str, Any]] = []
    deleted_job: dict[str, Any] | None = None
    for job in entry["jobs"]:
        if deleted_job is None and job["id"] == target_id:
            deleted_job = job
            continue
        remaining.append(job)

    if deleted_job is None:
        return {
            "user_id": uid,
            "ignored_job_id": target_id,
            "deleted": False,
            "deleted_job": None,
            "total_ignored_jobs": len(entry["jobs"]),
            "path": DEFAULT_IGNORED_JOBS_PATH,
        }

    entry["jobs"] = remaining
    entry["updated_at_utc"] = _utcnow_iso()
    _save_ignored_jobs(data)
    return {
        "user_id": uid,
        "ignored_job_id": target_id,
        "deleted": True,
        "deleted_job": deleted_job,
        "total_ignored_jobs": len(remaining),
        "path": DEFAULT_IGNORED_JOBS_PATH,
    }


@mcp.tool()
def clear_search_session(
    user_id: str,
    session_id: str = "",
    clear_all_for_user: bool = False,
) -> dict[str, Any]:
    """Delete one search session or all sessions for a user."""
    uid = user_id.strip()
    if not uid:
        raise ValueError("user_id is required")

    store = _prune_search_sessions(_load_search_sessions())
    sessions = store.get("sessions", {})
    if not isinstance(sessions, dict):
        sessions = {}

    deleted_ids: list[str] = []
    if clear_all_for_user:
        for sid, record in list(sessions.items()):
            if not isinstance(record, dict):
                continue
            query = record.get("query", {})
            if isinstance(query, dict) and str(query.get("user_id", "")).strip() == uid:
                sessions.pop(sid, None)
                deleted_ids.append(sid)
    else:
        sid = session_id.strip()
        if not sid:
            raise ValueError("session_id is required unless clear_all_for_user=true")
        record = sessions.get(sid)
        if not isinstance(record, dict):
            return {
                "user_id": uid,
                "session_id": sid,
                "deleted": False,
                "deleted_session_ids": [],
                "remaining_user_sessions": 0,
                "path": DEFAULT_SEARCH_SESSION_PATH,
            }
        query = record.get("query", {})
        if not isinstance(query, dict) or str(query.get("user_id", "")).strip() != uid:
            raise ValueError("session_id does not belong to this user_id")
        sessions.pop(sid, None)
        deleted_ids.append(sid)

    store["sessions"] = sessions
    _save_search_sessions(_prune_search_sessions(store))
    remaining_user_sessions = 0
    for record in sessions.values():
        if not isinstance(record, dict):
            continue
        query = record.get("query", {})
        if isinstance(query, dict) and str(query.get("user_id", "")).strip() == uid:
            remaining_user_sessions += 1

    return {
        "user_id": uid,
        "session_id": session_id.strip(),
        "clear_all_for_user": bool(clear_all_for_user),
        "deleted": bool(deleted_ids),
        "deleted_session_ids": deleted_ids,
        "deleted_count": len(deleted_ids),
        "remaining_user_sessions": int(remaining_user_sessions),
        "path": DEFAULT_SEARCH_SESSION_PATH,
    }


@mcp.tool()
def export_user_data(user_id: str) -> dict[str, Any]:
    """Export all local data for one user across preference/memory/job/session stores."""
    uid = user_id.strip()
    if not uid:
        raise ValueError("user_id is required")

    prefs_store = _load_user_prefs()
    prefs = prefs_store.get(uid, {}) if isinstance(prefs_store, dict) else {}
    if not isinstance(prefs, dict):
        prefs = {}

    blob_entry = _get_user_blob_entry(_load_user_blob(), uid) or {}
    memory_lines = blob_entry.get("lines", []) if isinstance(blob_entry, dict) else []
    if not isinstance(memory_lines, list):
        memory_lines = []

    saved_entry = _get_saved_jobs_entry(_load_saved_jobs(), uid) or {}
    saved_jobs = saved_entry.get("jobs", []) if isinstance(saved_entry, dict) else []
    if not isinstance(saved_jobs, list):
        saved_jobs = []

    ignored_entry = _get_ignored_jobs_entry(_load_ignored_jobs(), uid) or {}
    ignored_jobs = ignored_entry.get("jobs", []) if isinstance(ignored_entry, dict) else []
    if not isinstance(ignored_jobs, list):
        ignored_jobs = []

    session_store = _prune_search_sessions(_load_search_sessions())
    sessions = session_store.get("sessions", {})
    exported_sessions: list[dict[str, Any]] = []
    if isinstance(sessions, dict):
        for sid, record in sessions.items():
            if not isinstance(record, dict):
                continue
            query = record.get("query", {})
            if not isinstance(query, dict):
                continue
            if str(query.get("user_id", "")).strip() != uid:
                continue
            exported_sessions.append(
                {
                    "session_id": sid,
                    "created_at_utc": record.get("created_at_utc"),
                    "updated_at_utc": record.get("updated_at_utc"),
                    "expires_at_utc": record.get("expires_at_utc"),
                    "query": query,
                    "accepted_jobs_total": int(record.get("accepted_jobs_total", 0) or 0),
                    "latest_scan_target": int(record.get("latest_scan_target", 0) or 0),
                    "scan_exhausted": bool(record.get("scan_exhausted", False)),
                }
            )

    return {
        "user_id": uid,
        "exported_at_utc": _utcnow_iso(),
        "data": {
            "preferences": prefs,
            "memory_lines": memory_lines,
            "saved_jobs": saved_jobs,
            "ignored_jobs": ignored_jobs,
            "search_sessions": exported_sessions,
        },
        "counts": {
            "memory_lines": len(memory_lines),
            "saved_jobs": len(saved_jobs),
            "ignored_jobs": len(ignored_jobs),
            "search_sessions": len(exported_sessions),
        },
        "paths": {
            "preferences_path": DEFAULT_USER_PREFS_PATH,
            "memory_blob_path": DEFAULT_USER_BLOB_PATH,
            "saved_jobs_path": DEFAULT_SAVED_JOBS_PATH,
            "ignored_jobs_path": DEFAULT_IGNORED_JOBS_PATH,
            "search_sessions_path": DEFAULT_SEARCH_SESSION_PATH,
        },
    }


@mcp.tool()
def delete_user_data(user_id: str, confirm: bool = False) -> dict[str, Any]:
    """Permanently delete all local records for one user."""
    uid = user_id.strip()
    if not uid:
        raise ValueError("user_id is required")
    if not confirm:
        raise ValueError("confirm=true is required to delete user data")

    deleted = {
        "preferences": False,
        "memory_lines": 0,
        "saved_jobs": 0,
        "ignored_jobs": 0,
        "search_sessions": 0,
    }

    prefs_store = _load_user_prefs()
    if isinstance(prefs_store, dict) and uid in prefs_store:
        prefs_store.pop(uid, None)
        _save_user_prefs(prefs_store)
        deleted["preferences"] = True

    blob_store = _load_user_blob()
    if isinstance(blob_store, dict):
        users = blob_store.get("users", {})
        if isinstance(users, dict):
            entry = users.pop(uid, None)
            if isinstance(entry, dict):
                lines = entry.get("lines", [])
                deleted["memory_lines"] = len(lines) if isinstance(lines, list) else 0
                _save_user_blob(blob_store)

    saved_store = _load_saved_jobs()
    if isinstance(saved_store, dict):
        users = saved_store.get("users", {})
        if isinstance(users, dict):
            entry = users.pop(uid, None)
            if isinstance(entry, dict):
                jobs = entry.get("jobs", [])
                deleted["saved_jobs"] = len(jobs) if isinstance(jobs, list) else 0
                _save_saved_jobs(saved_store)

    ignored_store = _load_ignored_jobs()
    if isinstance(ignored_store, dict):
        users = ignored_store.get("users", {})
        if isinstance(users, dict):
            entry = users.pop(uid, None)
            if isinstance(entry, dict):
                jobs = entry.get("jobs", [])
                deleted["ignored_jobs"] = len(jobs) if isinstance(jobs, list) else 0
                _save_ignored_jobs(ignored_store)

    session_store = _prune_search_sessions(_load_search_sessions())
    sessions = session_store.get("sessions", {})
    if isinstance(sessions, dict):
        removed = 0
        for sid, record in list(sessions.items()):
            if not isinstance(record, dict):
                continue
            query = record.get("query", {})
            if isinstance(query, dict) and str(query.get("user_id", "")).strip() == uid:
                sessions.pop(sid, None)
                removed += 1
        if removed > 0:
            session_store["sessions"] = sessions
            _save_search_sessions(_prune_search_sessions(session_store))
        deleted["search_sessions"] = removed

    return {
        "user_id": uid,
        "deleted": deleted,
        "paths": {
            "preferences_path": DEFAULT_USER_PREFS_PATH,
            "memory_blob_path": DEFAULT_USER_BLOB_PATH,
            "saved_jobs_path": DEFAULT_SAVED_JOBS_PATH,
            "ignored_jobs_path": DEFAULT_IGNORED_JOBS_PATH,
            "search_sessions_path": DEFAULT_SEARCH_SESSION_PATH,
        },
    }


@mcp.tool()
def find_visa_sponsored_jobs(
    location: str,
    job_title: str,
    user_id: str,
    results_wanted: int = 300,
    hours_old: int = 336,
    dataset_path: str = DEFAULT_DATASET_PATH,
    sites: list[str] | None = None,
    max_returned: int = 10,
    offset: int = 0,
    require_description_signal: bool = False,
    strictness_mode: str = "strict",
    session_id: str = "",
    refresh_session: bool = False,
    auto_expand_scan: bool = True,
    scan_multiplier: int = DEFAULT_SCAN_MULTIPLIER,
    max_scan_results: int = DEFAULT_MAX_SCAN_RESULTS,
) -> dict[str, Any]:
    """Search jobs by area with JobSpy, then keep jobs likely to sponsor visas.

    This uses the flipped model:
    1) Scrape jobs in an area across multiple sites.
    2) Match scraped companies against the sponsorship dataset.
    3) Also accept jobs when description contains visa sponsorship signals.
    """
    if not location.strip():
        raise ValueError("location is required")
    if not job_title.strip():
        raise ValueError("job_title is required")
    if results_wanted < 1:
        raise ValueError("results_wanted must be >= 1")
    if max_returned < 1:
        raise ValueError("max_returned must be >= 1")
    if offset < 0:
        raise ValueError("offset must be >= 0")
    if scan_multiplier < 1:
        raise ValueError("scan_multiplier must be >= 1")
    normalized_strictness_mode = _normalize_strictness_mode(strictness_mode)
    if max_scan_results < 1:
        max_scan_results = results_wanted
    if max_scan_results < results_wanted:
        max_scan_results = results_wanted

    _disable_proxies()
    _ensure_dataset_exists(dataset_path)
    dataset_freshness = _dataset_freshness(
        dataset_path=dataset_path,
        manifest_path=DEFAULT_DOL_MANIFEST_PATH,
        stale_after_days=DEFAULT_DATASET_STALE_AFTER_DAYS,
    )

    sponsor_df = _load_company_dataset(dataset_path).set_index("normalized_company", drop=False)
    requested_sites = sites or DEFAULT_SITES
    invalid_sites = [s for s in requested_sites if s not in SUPPORTED_SITES]
    if invalid_sites:
        raise ValueError(f"Only LinkedIn is supported right now. Invalid sites: {invalid_sites}")
    chosen_sites = ["linkedin"]
    desired_visa_types = _get_required_user_visa_types(user_id)

    required_accepted_for_page = offset + max_returned
    query_fingerprint = _search_query_fingerprint(
        location=location,
        job_title=job_title,
        user_id=user_id,
        hours_old=hours_old,
        dataset_path=dataset_path,
        sites=chosen_sites,
        require_description_signal=require_description_signal,
        desired_visa_types=desired_visa_types,
        strictness_mode=normalized_strictness_mode,
    )
    session_store = _prune_search_sessions(_load_search_sessions())
    sessions = session_store.setdefault("sessions", {})
    now_utc = datetime.now(timezone.utc)

    search_session_id = session_id.strip()
    session_record: dict[str, Any] = {}
    session_reused = False
    cache_hit = False

    if search_session_id:
        existing = sessions.get(search_session_id)
        if not isinstance(existing, dict):
            raise ValueError(
                f"Unknown session_id '{search_session_id}'. Omit session_id to start a new search session."
            )
        expires_at = _parse_utc_iso(existing.get("expires_at_utc"))
        if expires_at and expires_at <= now_utc:
            sessions.pop(search_session_id, None)
            _save_search_sessions(_prune_search_sessions(session_store))
            raise ValueError(
                f"session_id '{search_session_id}' has expired. Omit session_id to start a new search session."
            )
        if str(existing.get("query_fingerprint", "")) != query_fingerprint:
            raise ValueError(
                "Provided session_id does not match this query. Omit session_id to start a new search session."
            )
        session_record = dict(existing)
        session_reused = True
    else:
        search_session_id = uuid.uuid4().hex

    if refresh_session:
        session_record = {}

    cached_jobs_raw = session_record.get("accepted_jobs", [])
    cached_jobs: list[dict[str, Any]] = []
    if isinstance(cached_jobs_raw, list):
        cached_jobs = [job for job in cached_jobs_raw if isinstance(job, dict)]
    if cached_jobs:
        cached_jobs = _attach_result_ids(search_session_id, cached_jobs)

    try:
        cached_scan_target = int(session_record.get("latest_scan_target", 0))
    except (TypeError, ValueError):
        cached_scan_target = 0
    if cached_scan_target < 0:
        cached_scan_target = 0

    accepted_job_dicts: list[dict[str, Any]] = []
    scan_attempts: list[dict[str, int]] = []
    last_scraped_jobs_count = 0
    last_requested_scan_target = max(results_wanted, cached_scan_target)
    scan_exhausted = False
    rate_limit_retry_attempts = 0
    rate_limit_backoff_seconds = 0.0

    if (not refresh_session) and len(cached_jobs) >= required_accepted_for_page:
        accepted_job_dicts = cached_jobs
        cache_hit = True
        try:
            last_scraped_jobs_count = int(session_record.get("scraped_jobs", 0))
        except (TypeError, ValueError):
            last_scraped_jobs_count = 0
        if last_scraped_jobs_count < 0:
            last_scraped_jobs_count = 0
        scan_exhausted = bool(session_record.get("scan_exhausted", False))
        try:
            rate_limit_retry_attempts = int(session_record.get("rate_limit_retry_attempts", 0))
        except (TypeError, ValueError):
            rate_limit_retry_attempts = 0
        try:
            rate_limit_backoff_seconds = float(session_record.get("rate_limit_backoff_seconds", 0.0))
        except (TypeError, ValueError):
            rate_limit_backoff_seconds = 0.0
    else:
        requested_scan_target = results_wanted
        if auto_expand_scan:
            requested_scan_target = max(
                requested_scan_target,
                required_accepted_for_page * scan_multiplier,
            )
        requested_scan_target = max(requested_scan_target, cached_scan_target)
        scan_target = min(requested_scan_target, max_scan_results)

        last_raw_jobs = pd.DataFrame([])
        evaluated_results: list[EvaluatedJob] = []
        while True:
            raw_jobs, scrape_attempts, scrape_backoff_seconds = _scrape_jobs_with_backoff(
                site_name=chosen_sites,
                search_term=job_title,
                location=location,
                results_wanted=scan_target,
                hours_old=hours_old,
                country_indeed=DEFAULT_INDEED_COUNTRY,
                retry_window_seconds=DEFAULT_RATE_LIMIT_RETRY_WINDOW_SECONDS,
                initial_backoff_seconds=DEFAULT_RATE_LIMIT_INITIAL_BACKOFF_SECONDS,
                max_backoff_seconds=DEFAULT_RATE_LIMIT_MAX_BACKOFF_SECONDS,
            )
            rate_limit_retry_attempts += max(0, scrape_attempts - 1)
            rate_limit_backoff_seconds += float(scrape_backoff_seconds)
            raw_jobs = _dedupe_raw_jobs(raw_jobs)
            last_raw_jobs = raw_jobs

            evaluated_results = _evaluate_scraped_jobs(
                raw_jobs=raw_jobs,
                sponsor_df=sponsor_df,
                desired_visa_types=desired_visa_types,
                require_description_signal=require_description_signal,
                strictness_mode=normalized_strictness_mode,
            )
            scan_attempts.append(
                {
                    "results_wanted": int(scan_target),
                    "scraped_jobs": int(len(raw_jobs)),
                    "accepted_jobs": int(len(evaluated_results)),
                }
            )

            if not auto_expand_scan:
                break
            if len(evaluated_results) >= required_accepted_for_page:
                break
            if len(raw_jobs) < scan_target:
                break
            if scan_target >= max_scan_results:
                break

            next_scan_target = min(
                max_scan_results,
                max(scan_target * 2, scan_target + (max_returned * scan_multiplier)),
            )
            if next_scan_target <= scan_target:
                break
            scan_target = next_scan_target

        accepted_job_dicts = [asdict(job) for job in evaluated_results]
        last_scraped_jobs_count = int(len(last_raw_jobs))
        last_requested_scan_target = scan_attempts[-1]["results_wanted"] if scan_attempts else scan_target
        scan_exhausted = (
            len(accepted_job_dicts) < required_accepted_for_page
            and (
                not auto_expand_scan
                or last_requested_scan_target >= max_scan_results
                or last_scraped_jobs_count < last_requested_scan_target
            )
        )

    accepted_job_dicts = _attach_result_ids(search_session_id, accepted_job_dicts)
    ignored_job_urls = _ignored_job_url_set(user_id)
    filtered_accepted_job_dicts = (
        [
            job
            for job in accepted_job_dicts
            if str(job.get("job_url", "")).strip().lower() not in ignored_job_urls
        ]
        if ignored_job_urls
        else accepted_job_dicts
    )
    ignored_filtered_count = len(accepted_job_dicts) - len(filtered_accepted_job_dicts)
    effective_scan_exhausted = bool(
        scan_exhausted
        or (
            len(filtered_accepted_job_dicts) < required_accepted_for_page
            and ignored_filtered_count > 0
        )
    )

    limited = filtered_accepted_job_dicts[offset : offset + max_returned]
    returned_jobs = len(limited)
    has_next_page = (offset + returned_jobs) < len(filtered_accepted_job_dicts)
    next_offset = (offset + returned_jobs) if has_next_page else None
    recovery_suggestions = _build_recovery_suggestions(
        location=location,
        job_title=job_title,
        hours_old=hours_old,
        max_scan_results=max_scan_results,
        accepted_jobs=len(filtered_accepted_job_dicts),
        returned_jobs=returned_jobs,
        scan_exhausted=effective_scan_exhausted,
    )

    created_at_utc = str(session_record.get("created_at_utc", _utcnow_iso()))
    updated_at_utc = _utcnow_iso()
    expires_at_utc = _future_utc_iso(DEFAULT_SEARCH_SESSION_TTL_SECONDS)
    result_id_index = _build_result_id_index(accepted_job_dicts)
    sessions[search_session_id] = {
        "query_fingerprint": query_fingerprint,
        "query": {
            "location": location,
            "job_title": job_title,
            "user_id": user_id,
            "hours_old": hours_old,
            "dataset_path": str(Path(dataset_path).expanduser().resolve()),
            "sites": chosen_sites,
            "require_description_signal": bool(require_description_signal),
            "preferred_visa_types": desired_visa_types,
            "strictness_mode": normalized_strictness_mode,
        },
        "created_at_utc": created_at_utc,
        "updated_at_utc": updated_at_utc,
        "expires_at_utc": expires_at_utc,
        "accepted_jobs": accepted_job_dicts,
        "result_id_index": result_id_index,
        "accepted_jobs_total": int(len(accepted_job_dicts)),
        "latest_scan_target": int(last_requested_scan_target),
        "scraped_jobs": int(last_scraped_jobs_count),
        "scan_exhausted": bool(scan_exhausted),
        "scan_attempts_detail": scan_attempts,
        "rate_limit_retry_attempts": int(rate_limit_retry_attempts),
        "rate_limit_backoff_seconds": float(round(rate_limit_backoff_seconds, 2)),
    }
    session_store["sessions"] = sessions
    session_store = _enforce_user_session_limit(
        _prune_search_sessions(session_store),
        user_id=user_id,
        max_sessions_per_user=DEFAULT_MAX_SEARCH_SESSIONS_PER_USER,
    )
    _save_search_sessions(session_store)

    return {
        "query": {
            "location": location,
            "job_title": job_title,
            "sites": chosen_sites,
            "results_wanted": results_wanted,
            "hours_old": hours_old,
            "dataset_path": dataset_path,
            "jobspy_source": JOBSPY_SOURCE,
            "offset": offset,
            "max_returned": max_returned,
            "user_id": user_id,
            "preferred_visa_types": desired_visa_types,
            "require_description_signal": require_description_signal,
            "strictness_mode": normalized_strictness_mode,
            "session_id": search_session_id,
            "refresh_session": refresh_session,
            "auto_expand_scan": auto_expand_scan,
            "scan_multiplier": scan_multiplier,
            "max_scan_results": max_scan_results,
            "rate_limit_retry_window_seconds": int(DEFAULT_RATE_LIMIT_RETRY_WINDOW_SECONDS),
            "rate_limit_initial_backoff_seconds": int(DEFAULT_RATE_LIMIT_INITIAL_BACKOFF_SECONDS),
            "rate_limit_max_backoff_seconds": int(DEFAULT_RATE_LIMIT_MAX_BACKOFF_SECONDS),
            "proxies_used": False,
        },
        "search_session": {
            "session_id": search_session_id,
            "reused_session": bool(session_reused),
            "cache_hit": bool(cache_hit),
            "created_at_utc": created_at_utc,
            "updated_at_utc": updated_at_utc,
            "expires_at_utc": expires_at_utc,
            "ttl_seconds": int(DEFAULT_SEARCH_SESSION_TTL_SECONDS),
            "max_sessions_per_user": int(DEFAULT_MAX_SEARCH_SESSIONS_PER_USER),
            "path": DEFAULT_SEARCH_SESSION_PATH,
        },
        "stats": {
            "scraped_jobs": int(last_scraped_jobs_count),
            "accepted_jobs_before_ignore_filter": int(len(accepted_job_dicts)),
            "ignored_filtered_count": int(ignored_filtered_count),
            "accepted_jobs": int(len(filtered_accepted_job_dicts)),
            "returned_jobs": int(returned_jobs),
            "cache_hit": bool(cache_hit),
            "scan_attempts": int(len(scan_attempts)),
            "scan_attempts_detail": scan_attempts,
            "rate_limit_retry_attempts": int(rate_limit_retry_attempts),
            "rate_limit_backoff_seconds": float(round(rate_limit_backoff_seconds, 2)),
            "confidence_model_version": CONFIDENCE_MODEL_VERSION,
        },
        "agent_guidance": {
            "strict_visa_match_applied": True,
            "strictness_mode": normalized_strictness_mode,
            "use_search_session_id_for_next_page": search_session_id,
            "ask_user_to_save_jobs_prompt": (
                "Ask the user if they want to save any returned jobs for later. "
                "If yes, call save_job_for_later for each selected job (prefer result_id)."
            ),
            "save_for_later_tool": "save_job_for_later",
            "ask_user_to_ignore_jobs_prompt": (
                "Ask the user if they want to hide any irrelevant jobs. "
                "If yes, call ignore_job with result_id (or job_url)."
            ),
            "ignore_job_tool": "ignore_job",
            "rate_limit_guidance": (
                "If a search fails with a rate-limit error, wait a few minutes and retry the same call."
            ),
            "fallback_guidance": (
                "If results are sparse, show recovery_suggestions and ask the user to approve one."
            ),
            "next_call_hint": (
                {
                    "tool": "find_visa_sponsored_jobs",
                    "session_id": search_session_id,
                    "offset": int(next_offset),
                    "max_returned": int(max_returned),
                }
                if next_offset is not None
                else None
            ),
        },
        "dataset_freshness": dataset_freshness,
        "pagination": {
            "offset": int(offset),
            "page_size": int(max_returned),
            "returned_jobs": int(returned_jobs),
            "next_offset": next_offset,
            "has_next_page": bool(has_next_page),
            "accepted_jobs_total": int(len(filtered_accepted_job_dicts)),
            "accepted_jobs_needed_for_page": int(required_accepted_for_page),
            "requested_scan_target": int(last_requested_scan_target),
            "max_scan_results": int(max_scan_results),
            "scan_exhausted": effective_scan_exhausted,
        },
        "recovery_suggestions": recovery_suggestions,
        "jobs": limited,
    }


@mcp.tool()
def refresh_company_dataset_cache(dataset_path: str = DEFAULT_DATASET_PATH) -> dict[str, Any]:
    """Clear and reload cached sponsorship dataset."""
    _ensure_dataset_exists(dataset_path)
    _load_company_dataset.cache_clear()
    df = _load_company_dataset(dataset_path)
    return {
        "dataset_path": dataset_path,
        "rows": int(len(df)),
        "distinct_normalized_companies": int(df["normalized_company"].nunique()),
    }


def main() -> None:
    _disable_proxies()
    mcp.run()


if __name__ == "__main__":
    main()
