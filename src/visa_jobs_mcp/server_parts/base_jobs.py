from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError

from .base_runtime import *  # noqa: F401,F403
from .base_runtime import (
    _JOB_DB_READY_PATHS,
    _ensure_job_db,
    _job_db_conn,
    _job_db_path,
    _parse_utc_iso,
    _save_search_sessions,
    _set_job_stage_in_conn,
    _stable_json,
    _upsert_job_in_conn,
    _utcnow_iso,
)

def _migrate_job_management_from_json(path: str | None = None) -> dict[str, Any]:
    load_saved_jobs = globals().get("_load_saved_jobs")
    load_ignored_jobs = globals().get("_load_ignored_jobs")
    normalize_saved_job = globals().get("_normalized_saved_job")
    normalize_ignored_job = globals().get("_normalized_ignored_job")
    if not callable(load_saved_jobs) or not callable(load_ignored_jobs):
        raise NameError("Saved/ignored job store helpers are not available")
    if not callable(normalize_saved_job) or not callable(normalize_ignored_job):
        raise NameError("Saved/ignored job normalizers are not available")

    _ensure_job_db(path)
    with _job_db_conn(path) as conn:
        existing = conn.execute(
            "SELECT key, applied_at_utc FROM schema_migrations WHERE key = ? LIMIT 1",
            (JOB_DB_MIGRATION_KEY,),
        ).fetchone()
        if existing:
            return {
                "already_migrated": True,
                "migration_key": JOB_DB_MIGRATION_KEY,
                "applied_at_utc": str(existing["applied_at_utc"]),
                "saved_jobs_migrated": 0,
                "ignored_jobs_migrated": 0,
            }

        saved_jobs_migrated = 0
        ignored_jobs_migrated = 0
        saved_store = load_saved_jobs()
        users = saved_store.get("users", {}) if isinstance(saved_store, dict) else {}
        if isinstance(users, dict):
            for uid, entry in users.items():
                if not isinstance(entry, dict):
                    continue
                for raw in entry.get("jobs", []):
                    normalized = normalize_saved_job(raw)
                    if not normalized:
                        continue
                    job_id = _upsert_job_in_conn(
                        conn,
                        user_id=uid,
                        job_url=str(normalized.get("job_url", "")).strip(),
                        title=str(normalized.get("title", "")).strip(),
                        company=str(normalized.get("company", "")).strip(),
                        location=str(normalized.get("location", "")).strip(),
                        site=str(normalized.get("site", "")).strip(),
                    )
                    _set_job_stage_in_conn(
                        conn,
                        user_id=uid,
                        job_id=job_id,
                        stage="saved",
                        note=str(normalized.get("note", "")).strip(),
                        source_session_id=str(normalized.get("source_session_id", "")).strip(),
                        reason="migration_saved_jobs",
                    )
                    saved_jobs_migrated += 1

        ignored_store = load_ignored_jobs()
        ignored_users = ignored_store.get("users", {}) if isinstance(ignored_store, dict) else {}
        if isinstance(ignored_users, dict):
            for uid, entry in ignored_users.items():
                if not isinstance(entry, dict):
                    continue
                for raw in entry.get("jobs", []):
                    normalized = normalize_ignored_job(raw)
                    if not normalized:
                        continue
                    job_id = _upsert_job_in_conn(
                        conn,
                        user_id=uid,
                        job_url=str(normalized.get("job_url", "")).strip(),
                    )
                    _set_job_stage_in_conn(
                        conn,
                        user_id=uid,
                        job_id=job_id,
                        stage="ignored",
                        note=str(normalized.get("reason", "")).strip(),
                        source_session_id=str(normalized.get("source", "")).strip(),
                        reason="migration_ignored_jobs",
                    )
                    ignored_jobs_migrated += 1

        now_utc = _utcnow_iso()
        conn.execute(
            "INSERT INTO schema_migrations (key, applied_at_utc) VALUES (?, ?)",
            (JOB_DB_MIGRATION_KEY, now_utc),
        )
        return {
            "already_migrated": False,
            "migration_key": JOB_DB_MIGRATION_KEY,
            "applied_at_utc": now_utc,
            "saved_jobs_migrated": int(saved_jobs_migrated),
            "ignored_jobs_migrated": int(ignored_jobs_migrated),
        }


def _ensure_job_management_ready(path: str | None = None) -> dict[str, Any]:
    resolved = str(Path(_job_db_path(path)).expanduser().resolve())
    if resolved in _JOB_DB_READY_PATHS:
        return {"already_ready": True, "job_db_path": resolved}
    _ensure_job_db(resolved)
    migration = _migrate_job_management_from_json(resolved)
    _JOB_DB_READY_PATHS.add(resolved)
    return {
        "already_ready": False,
        "job_db_path": resolved,
        "migration": migration,
    }


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


def _prune_search_runs(
    data: dict[str, Any],
    max_runs: int = DEFAULT_MAX_SEARCH_RUNS,
) -> dict[str, Any]:
    runs = data.get("runs")
    if not isinstance(runs, dict):
        data["runs"] = {}
        return data

    now = datetime.now(timezone.utc)
    valid: dict[str, dict[str, Any]] = {}
    for run_id, record in runs.items():
        if not isinstance(record, dict):
            continue
        expires_at = _parse_utc_iso(record.get("expires_at_utc"))
        if expires_at and expires_at <= now:
            continue
        valid[run_id] = record

    def sort_key(item: tuple[str, dict[str, Any]]) -> datetime:
        dt = _parse_utc_iso(item[1].get("updated_at_utc")) or _parse_utc_iso(item[1].get("created_at_utc"))
        return dt or datetime.fromtimestamp(0, tz=timezone.utc)

    if max_runs > 0 and len(valid) > max_runs:
        ordered = sorted(valid.items(), key=sort_key, reverse=True)[:max_runs]
        valid = {run_id: record for run_id, record in ordered}

    data["runs"] = valid
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
            "visa_match_strength": item.get("visa_match_strength", ""),
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


def _is_scrape_timeout_error(exc: Exception) -> bool:
    return "job source scrape attempt timed out" in str(exc).lower()


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
    attempt_timeout_seconds: int = DEFAULT_SCRAPE_ATTEMPT_TIMEOUT_SECONDS,
) -> tuple[pd.DataFrame, int, float]:
    attempts = 0
    elapsed_backoff_seconds = 0.0
    backoff_seconds = float(max(1, initial_backoff_seconds))
    retry_window = float(max(0, retry_window_seconds))
    max_backoff = float(max(1, max_backoff_seconds))
    attempt_timeout = float(max(1, attempt_timeout_seconds))

    while True:
        attempts += 1
        try:
            executor = ThreadPoolExecutor(max_workers=1)
            future = executor.submit(
                scrape_jobs,
                site_name=site_name,
                search_term=search_term,
                location=location,
                results_wanted=results_wanted,
                hours_old=hours_old,
                country_indeed=country_indeed,
            )
            try:
                raw = future.result(timeout=attempt_timeout)
            except FutureTimeoutError as exc:
                future.cancel()
                raise RuntimeError(
                    "Job source scrape attempt timed out before completion. "
                    "Please retry with the same session_id."
                ) from exc
            finally:
                executor.shutdown(wait=False, cancel_futures=True)
            return raw, attempts, elapsed_backoff_seconds
        except Exception as exc:
            if _is_scrape_timeout_error(exc):
                raise
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
