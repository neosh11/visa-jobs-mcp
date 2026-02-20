from __future__ import annotations

from .base import *  # noqa: F401,F403

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
    ignored_companies_entry = _get_ignored_companies_entry(_load_ignored_companies(), uid) or {}
    ignored_companies = (
        ignored_companies_entry.get("companies", [])
        if isinstance(ignored_companies_entry, dict)
        else []
    )
    if not isinstance(ignored_companies, list):
        ignored_companies = []

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
    runs_store = _prune_search_runs(_load_search_runs())
    runs = runs_store.get("runs", {})
    exported_runs: list[dict[str, Any]] = []
    if isinstance(runs, dict):
        for run_id, record in runs.items():
            if not isinstance(record, dict):
                continue
            query = record.get("query", {})
            if not isinstance(query, dict):
                continue
            if str(query.get("user_id", "")).strip() != uid:
                continue
            exported_runs.append(
                {
                    "run_id": run_id,
                    "status": str(record.get("status", "")).strip(),
                    "created_at_utc": record.get("created_at_utc"),
                    "updated_at_utc": record.get("updated_at_utc"),
                    "completed_at_utc": record.get("completed_at_utc"),
                    "expires_at_utc": record.get("expires_at_utc"),
                    "attempt_count": int(record.get("attempt_count", 0) or 0),
                    "search_session_id": str(record.get("search_session_id", "")).strip(),
                    "query": query,
                }
            )

    _ensure_job_management_ready()
    with _job_db_conn() as conn:
        job_rows = conn.execute(
            """
            SELECT id, user_id, result_id, job_url, title, company, location, site, created_at_utc, updated_at_utc
            FROM jobs
            WHERE user_id = ?
            ORDER BY updated_at_utc DESC, id DESC
            """,
            (uid,),
        ).fetchall()
        application_rows = conn.execute(
            """
            SELECT id, user_id, job_id, stage, applied_at_utc, source_session_id, note, updated_at_utc
            FROM job_applications
            WHERE user_id = ?
            ORDER BY updated_at_utc DESC, id DESC
            """,
            (uid,),
        ).fetchall()
        event_rows = conn.execute(
            """
            SELECT id, user_id, job_id, from_stage, to_stage, reason, note, created_at_utc
            FROM job_events
            WHERE user_id = ?
            ORDER BY created_at_utc DESC, id DESC
            """,
            (uid,),
        ).fetchall()

    return {
        "user_id": uid,
        "exported_at_utc": _utcnow_iso(),
        "data": {
            "preferences": prefs,
            "memory_lines": memory_lines,
            "saved_jobs": saved_jobs,
            "ignored_jobs": ignored_jobs,
            "ignored_companies": ignored_companies,
            "search_sessions": exported_sessions,
            "search_runs": exported_runs,
            "job_management": {
                "jobs": [_row_to_dict(row) for row in job_rows],
                "applications": [_row_to_dict(row) for row in application_rows],
                "events": [_row_to_dict(row) for row in event_rows],
            },
        },
        "counts": {
            "memory_lines": len(memory_lines),
            "saved_jobs": len(saved_jobs),
            "ignored_jobs": len(ignored_jobs),
            "ignored_companies": len(ignored_companies),
            "search_sessions": len(exported_sessions),
            "search_runs": len(exported_runs),
            "job_management_jobs": len(job_rows),
            "job_management_applications": len(application_rows),
            "job_management_events": len(event_rows),
        },
        "paths": {
            "preferences_path": DEFAULT_USER_PREFS_PATH,
            "memory_blob_path": DEFAULT_USER_BLOB_PATH,
            "saved_jobs_path": DEFAULT_SAVED_JOBS_PATH,
            "ignored_jobs_path": DEFAULT_IGNORED_JOBS_PATH,
            "ignored_companies_path": DEFAULT_IGNORED_COMPANIES_PATH,
            "search_sessions_path": DEFAULT_SEARCH_SESSION_PATH,
            "search_runs_path": DEFAULT_SEARCH_RUNS_PATH,
            "job_db_path": DEFAULT_JOB_DB_PATH,
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
        "ignored_companies": 0,
        "search_sessions": 0,
        "search_runs": 0,
        "job_management_jobs": 0,
        "job_management_applications": 0,
        "job_management_events": 0,
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

    ignored_companies_store = _load_ignored_companies()
    if isinstance(ignored_companies_store, dict):
        users = ignored_companies_store.get("users", {})
        if isinstance(users, dict):
            entry = users.pop(uid, None)
            if isinstance(entry, dict):
                companies = entry.get("companies", [])
                deleted["ignored_companies"] = len(companies) if isinstance(companies, list) else 0
                _save_ignored_companies(ignored_companies_store)

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

    runs_store = _prune_search_runs(_load_search_runs())
    runs = runs_store.get("runs", {})
    if isinstance(runs, dict):
        removed = 0
        for run_id, record in list(runs.items()):
            if not isinstance(record, dict):
                continue
            query = record.get("query", {})
            if isinstance(query, dict) and str(query.get("user_id", "")).strip() == uid:
                runs.pop(run_id, None)
                removed += 1
        if removed > 0:
            runs_store["runs"] = runs
            _save_search_runs(_prune_search_runs(runs_store))
        deleted["search_runs"] = removed

    _ensure_job_management_ready()
    with _job_db_conn() as conn:
        counts_row = conn.execute(
            """
            SELECT
              (SELECT COUNT(*) FROM jobs WHERE user_id = ?) AS jobs_count,
              (SELECT COUNT(*) FROM job_applications WHERE user_id = ?) AS applications_count,
              (SELECT COUNT(*) FROM job_events WHERE user_id = ?) AS events_count
            """,
            (uid, uid, uid),
        ).fetchone()
        if counts_row:
            deleted["job_management_jobs"] = int(counts_row["jobs_count"])
            deleted["job_management_applications"] = int(counts_row["applications_count"])
            deleted["job_management_events"] = int(counts_row["events_count"])
        conn.execute("DELETE FROM job_events WHERE user_id = ?", (uid,))
        conn.execute("DELETE FROM job_applications WHERE user_id = ?", (uid,))
        conn.execute("DELETE FROM jobs WHERE user_id = ?", (uid,))

    return {
        "user_id": uid,
        "deleted": deleted,
        "paths": {
            "preferences_path": DEFAULT_USER_PREFS_PATH,
            "memory_blob_path": DEFAULT_USER_BLOB_PATH,
            "saved_jobs_path": DEFAULT_SAVED_JOBS_PATH,
            "ignored_jobs_path": DEFAULT_IGNORED_JOBS_PATH,
            "ignored_companies_path": DEFAULT_IGNORED_COMPANIES_PATH,
            "search_sessions_path": DEFAULT_SEARCH_SESSION_PATH,
            "search_runs_path": DEFAULT_SEARCH_RUNS_PATH,
            "job_db_path": DEFAULT_JOB_DB_PATH,
        },
    }
