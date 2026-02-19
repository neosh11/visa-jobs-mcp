from __future__ import annotations

from .base import *  # noqa: F401,F403

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
        _ensure_job_management_ready()
        with _job_db_conn() as conn:
            db_job_id = _upsert_job_in_conn(
                conn,
                user_id=uid,
                job_url=clean_job_url,
                title=saved.get("title", ""),
                company=saved.get("company", ""),
                location=saved.get("location", ""),
                site=saved.get("site", ""),
                result_id=str(resolved.get("result_id", "")).strip(),
            )
            application, _ = _set_job_stage_in_conn(
                conn,
                user_id=uid,
                job_id=db_job_id,
                stage="saved",
                note=saved.get("note", ""),
                source_session_id=saved.get("source_session_id", ""),
                reason="save_job_for_later",
            )
        return {
            "user_id": uid,
            "action": "updated_existing",
            "saved_job": saved,
            "resolved_result_id": str(resolved.get("result_id", "")).strip(),
            "total_saved_jobs": len(entry["jobs"]),
            "job_management": {
                "job_id": int(db_job_id),
                "stage": str(application.get("stage", "saved")),
                "job_db_path": DEFAULT_JOB_DB_PATH,
            },
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
    _ensure_job_management_ready()
    with _job_db_conn() as conn:
        db_job_id = _upsert_job_in_conn(
            conn,
            user_id=uid,
            job_url=clean_job_url,
            title=saved_job.get("title", ""),
            company=saved_job.get("company", ""),
            location=saved_job.get("location", ""),
            site=saved_job.get("site", ""),
            result_id=str(resolved.get("result_id", "")).strip(),
        )
        application, _ = _set_job_stage_in_conn(
            conn,
            user_id=uid,
            job_id=db_job_id,
            stage="saved",
            note=saved_job.get("note", ""),
            source_session_id=saved_job.get("source_session_id", ""),
            reason="save_job_for_later",
        )
    return {
        "user_id": uid,
        "action": "saved_new",
        "saved_job": saved_job,
        "resolved_result_id": str(resolved.get("result_id", "")).strip(),
        "total_saved_jobs": len(entry["jobs"]),
        "job_management": {
            "job_id": int(db_job_id),
            "stage": str(application.get("stage", "saved")),
            "job_db_path": DEFAULT_JOB_DB_PATH,
        },
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
    _ensure_job_management_ready()
    deleted_url = str(deleted_job.get("job_url", "")).strip() if deleted_job else ""
    if deleted_url:
        with _job_db_conn() as conn:
            existing_job = _get_job_by_url_in_conn(conn, uid, deleted_url)
            if existing_job:
                _set_job_stage_in_conn(
                    conn,
                    user_id=uid,
                    job_id=int(existing_job["id"]),
                    stage="new",
                    note="",
                    reason="delete_saved_job",
                )
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
        _ensure_job_management_ready()
        with _job_db_conn() as conn:
            db_job_id = _upsert_job_in_conn(
                conn,
                user_id=uid,
                job_url=clean_job_url,
                result_id=str(resolved.get("result_id", "")).strip(),
            )
            application, _ = _set_job_stage_in_conn(
                conn,
                user_id=uid,
                job_id=db_job_id,
                stage="ignored",
                note=ignored.get("reason", ""),
                source_session_id=ignored.get("source", ""),
                reason="ignore_job",
            )
        return {
            "user_id": uid,
            "action": "updated_existing",
            "ignored_job": ignored,
            "resolved_result_id": str(resolved.get("result_id", "")).strip(),
            "total_ignored_jobs": len(entry["jobs"]),
            "job_management": {
                "job_id": int(db_job_id),
                "stage": str(application.get("stage", "ignored")),
                "job_db_path": DEFAULT_JOB_DB_PATH,
            },
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
    _ensure_job_management_ready()
    with _job_db_conn() as conn:
        db_job_id = _upsert_job_in_conn(
            conn,
            user_id=uid,
            job_url=clean_job_url,
            result_id=str(resolved.get("result_id", "")).strip(),
        )
        application, _ = _set_job_stage_in_conn(
            conn,
            user_id=uid,
            job_id=db_job_id,
            stage="ignored",
            note=ignored_job.get("reason", ""),
            source_session_id=ignored_job.get("source", ""),
            reason="ignore_job",
        )
    return {
        "user_id": uid,
        "action": "ignored_new",
        "ignored_job": ignored_job,
        "resolved_result_id": str(resolved.get("result_id", "")).strip(),
        "total_ignored_jobs": len(entry["jobs"]),
        "job_management": {
            "job_id": int(db_job_id),
            "stage": str(application.get("stage", "ignored")),
            "job_db_path": DEFAULT_JOB_DB_PATH,
        },
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
    _ensure_job_management_ready()
    deleted_url = str(deleted_job.get("job_url", "")).strip() if deleted_job else ""
    if deleted_url:
        with _job_db_conn() as conn:
            existing_job = _get_job_by_url_in_conn(conn, uid, deleted_url)
            if existing_job:
                _set_job_stage_in_conn(
                    conn,
                    user_id=uid,
                    job_id=int(existing_job["id"]),
                    stage="new",
                    note="",
                    reason="unignore_job",
                )
    return {
        "user_id": uid,
        "ignored_job_id": target_id,
        "deleted": True,
        "deleted_job": deleted_job,
        "total_ignored_jobs": len(remaining),
        "path": DEFAULT_IGNORED_JOBS_PATH,
    }


@mcp.tool()
def mark_job_applied(
    user_id: str,
    job_id: int = 0,
    job_url: str = "",
    result_id: str = "",
    session_id: str = "",
    applied_at_utc: str = "",
    note: str = "",
) -> dict[str, Any]:
    """Mark a job as applied and persist lifecycle state locally."""
    uid = user_id.strip()
    if not uid:
        raise ValueError("user_id is required")
    _ensure_job_management_ready()
    source_session = session_id.strip()
    if not source_session and ":" in result_id:
        source_session = result_id.split(":", 1)[0].strip()

    with _job_db_conn() as conn:
        resolved_job_id, _ = _resolve_job_management_target_in_conn(
            conn,
            user_id=uid,
            job_id=int(job_id or 0),
            job_url=job_url,
            result_id=result_id,
            session_id=session_id,
        )
        application, event = _set_job_stage_in_conn(
            conn,
            user_id=uid,
            job_id=resolved_job_id,
            stage="applied",
            note=note,
            source_session_id=source_session,
            applied_at_utc=applied_at_utc,
            reason="mark_job_applied",
        )
        snapshot = _job_snapshot_in_conn(conn, uid, resolved_job_id)

    return {
        "user_id": uid,
        "job": snapshot,
        "application": application,
        "event": event,
        "job_db_path": DEFAULT_JOB_DB_PATH,
    }


@mcp.tool()
def update_job_stage(
    user_id: str,
    stage: str,
    job_id: int = 0,
    job_url: str = "",
    result_id: str = "",
    session_id: str = "",
    note: str = "",
) -> dict[str, Any]:
    """Update a job lifecycle stage (saved/applied/interview/offer/rejected/ignored/new)."""
    uid = user_id.strip()
    if not uid:
        raise ValueError("user_id is required")
    clean_stage = _validate_job_stage(stage)
    _ensure_job_management_ready()
    source_session = session_id.strip()
    if not source_session and ":" in result_id:
        source_session = result_id.split(":", 1)[0].strip()

    with _job_db_conn() as conn:
        resolved_job_id, _ = _resolve_job_management_target_in_conn(
            conn,
            user_id=uid,
            job_id=int(job_id or 0),
            job_url=job_url,
            result_id=result_id,
            session_id=session_id,
        )
        application, event = _set_job_stage_in_conn(
            conn,
            user_id=uid,
            job_id=resolved_job_id,
            stage=clean_stage,
            note=note,
            source_session_id=source_session,
            reason="update_job_stage",
        )
        snapshot = _job_snapshot_in_conn(conn, uid, resolved_job_id)

    return {
        "user_id": uid,
        "job": snapshot,
        "application": application,
        "event": event,
        "job_db_path": DEFAULT_JOB_DB_PATH,
    }


@mcp.tool()
def add_job_note(
    user_id: str,
    note: str,
    job_id: int = 0,
    job_url: str = "",
    result_id: str = "",
    session_id: str = "",
) -> dict[str, Any]:
    """Append a note to a job record in the local job-management database."""
    uid = user_id.strip()
    if not uid:
        raise ValueError("user_id is required")
    if not note.strip():
        raise ValueError("note is required")
    _ensure_job_management_ready()

    with _job_db_conn() as conn:
        resolved_job_id, _ = _resolve_job_management_target_in_conn(
            conn,
            user_id=uid,
            job_id=int(job_id or 0),
            job_url=job_url,
            result_id=result_id,
            session_id=session_id,
        )
        application, event = _append_job_note_in_conn(
            conn,
            user_id=uid,
            job_id=resolved_job_id,
            note=note,
        )
        snapshot = _job_snapshot_in_conn(conn, uid, resolved_job_id)

    return {
        "user_id": uid,
        "job": snapshot,
        "application": application,
        "event": event,
        "job_db_path": DEFAULT_JOB_DB_PATH,
    }


@mcp.tool()
def list_jobs_by_stage(
    user_id: str,
    stage: str,
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    """List jobs for a user filtered by lifecycle stage."""
    uid = user_id.strip()
    if not uid:
        raise ValueError("user_id is required")
    clean_stage = _validate_job_stage(stage)
    safe_limit = max(1, min(limit, 200))
    safe_offset = max(offset, 0)
    _ensure_job_management_ready()

    with _job_db_conn() as conn:
        rows = conn.execute(
            """
            SELECT
              j.id AS job_id,
              j.result_id,
              j.job_url,
              j.title,
              j.company,
              j.location,
              j.site,
              ja.stage,
              ja.applied_at_utc,
              ja.source_session_id,
              ja.note,
              ja.updated_at_utc AS stage_updated_at_utc
            FROM job_applications ja
            JOIN jobs j ON j.id = ja.job_id AND j.user_id = ja.user_id
            WHERE ja.user_id = ? AND ja.stage = ?
            ORDER BY ja.updated_at_utc DESC
            LIMIT ? OFFSET ?
            """,
            (uid, clean_stage, safe_limit, safe_offset),
        ).fetchall()
        total = conn.execute(
            """
            SELECT COUNT(*) AS count
            FROM job_applications
            WHERE user_id = ? AND stage = ?
            """,
            (uid, clean_stage),
        ).fetchone()

    return {
        "user_id": uid,
        "stage": clean_stage,
        "offset": safe_offset,
        "limit": safe_limit,
        "total_jobs": int(total["count"]) if total else 0,
        "returned_jobs": len(rows),
        "jobs": [_row_to_dict(row) for row in rows],
        "job_db_path": DEFAULT_JOB_DB_PATH,
    }


@mcp.tool()
def list_recent_job_events(
    user_id: str,
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    """List recent lifecycle events for a user."""
    uid = user_id.strip()
    if not uid:
        raise ValueError("user_id is required")
    safe_limit = max(1, min(limit, 200))
    safe_offset = max(offset, 0)
    _ensure_job_management_ready()

    with _job_db_conn() as conn:
        rows = conn.execute(
            """
            SELECT
              e.id AS event_id,
              e.user_id,
              e.job_id,
              j.result_id,
              j.job_url,
              j.title,
              j.company,
              e.from_stage,
              e.to_stage,
              e.reason,
              e.note,
              e.created_at_utc
            FROM job_events e
            JOIN jobs j ON j.id = e.job_id AND j.user_id = e.user_id
            WHERE e.user_id = ?
            ORDER BY e.created_at_utc DESC, e.id DESC
            LIMIT ? OFFSET ?
            """,
            (uid, safe_limit, safe_offset),
        ).fetchall()
        total = conn.execute(
            "SELECT COUNT(*) AS count FROM job_events WHERE user_id = ?",
            (uid,),
        ).fetchone()

    return {
        "user_id": uid,
        "offset": safe_offset,
        "limit": safe_limit,
        "total_events": int(total["count"]) if total else 0,
        "returned_events": len(rows),
        "events": [_row_to_dict(row) for row in rows],
        "job_db_path": DEFAULT_JOB_DB_PATH,
    }


@mcp.tool()
def get_job_pipeline_summary(user_id: str) -> dict[str, Any]:
    """Return counts by stage and recent events for the local job pipeline."""
    uid = user_id.strip()
    if not uid:
        raise ValueError("user_id is required")
    _ensure_job_management_ready()

    stage_counts = {stage: 0 for stage in sorted(VALID_JOB_STAGES)}
    with _job_db_conn() as conn:
        rows = conn.execute(
            """
            SELECT stage, COUNT(*) AS count
            FROM job_applications
            WHERE user_id = ?
            GROUP BY stage
            """,
            (uid,),
        ).fetchall()
        for row in rows:
            key = str(row["stage"]).strip().lower()
            if key in stage_counts:
                stage_counts[key] = int(row["count"])

        recent_rows = conn.execute(
            """
            SELECT
              e.id AS event_id,
              e.job_id,
              j.result_id,
              j.job_url,
              j.title,
              j.company,
              e.from_stage,
              e.to_stage,
              e.reason,
              e.created_at_utc
            FROM job_events e
            JOIN jobs j ON j.id = e.job_id AND j.user_id = e.user_id
            WHERE e.user_id = ?
            ORDER BY e.created_at_utc DESC, e.id DESC
            LIMIT 10
            """,
            (uid,),
        ).fetchall()

        total_jobs_row = conn.execute(
            "SELECT COUNT(*) AS count FROM jobs WHERE user_id = ?",
            (uid,),
        ).fetchone()

    return {
        "user_id": uid,
        "stage_counts": stage_counts,
        "applied_jobs_count": int(stage_counts.get("applied", 0)),
        "total_tracked_jobs": int(total_jobs_row["count"]) if total_jobs_row else 0,
        "recent_events": [_row_to_dict(row) for row in recent_rows],
        "job_db_path": DEFAULT_JOB_DB_PATH,
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


