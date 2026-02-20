from __future__ import annotations

from .base import *  # noqa: F401,F403
from visa_jobs_mcp import __version__ as PACKAGE_VERSION


TOOL_DESCRIPTIONS: dict[str, str] = {
    "set_user_preferences": "Save the user's visa preferences required before search.",
    "set_user_constraints": "Save urgency and work-mode constraints used for personalized guidance.",
    "get_user_preferences": "Fetch the saved user preferences and constraints.",
    "get_user_readiness": "Report whether the user and local dataset are ready for search.",
    "find_related_titles": "Return adjacent role titles to widen low-yield searches.",
    "add_user_memory_line": "Append a profile memory line (skills, goals, fears, constraints).",
    "query_user_memory_blob": "Query the user's local memory blob with optional text filtering.",
    "delete_user_memory_line": "Delete one memory line by id from the local blob.",
    "save_job_for_later": "Save a job to the user's local shortlist for follow-up.",
    "list_saved_jobs": "List saved jobs in reverse-chronological order.",
    "delete_saved_job": "Remove one saved job from the local shortlist.",
    "ignore_job": "Hide one job from future results for this user.",
    "list_ignored_jobs": "List ignored jobs in reverse-chronological order.",
    "unignore_job": "Unhide a previously ignored job by id.",
    "ignore_company": "Hide all jobs from a company in future searches.",
    "list_ignored_companies": "List ignored companies in reverse-chronological order.",
    "unignore_company": "Remove one company from the ignored list.",
    "mark_job_applied": "Mark a job as applied and persist pipeline state.",
    "update_job_stage": "Update lifecycle stage for a tracked job (saved/applied/interview/etc).",
    "list_jobs_by_stage": "List tracked jobs filtered by lifecycle stage.",
    "add_job_note": "Attach or append a note to a tracked job record.",
    "list_recent_job_events": "List recent stage transitions and lifecycle events.",
    "get_job_pipeline_summary": "Summarize tracked pipeline counts by stage for one user.",
    "clear_search_session": "Delete one cached search session or all sessions for a user.",
    "export_user_data": "Export all local records for a user across stores.",
    "delete_user_data": "Permanently delete all local records for a user.",
    "get_best_contact_strategy": "Suggest best outreach channel/contact for a job.",
    "generate_outreach_message": "Generate a practical outreach draft tailored to user and role.",
    "start_visa_job_search": "Start a background search run for long scans.",
    "get_visa_job_search_status": "Poll incremental progress/events for a background search run.",
    "get_visa_job_search_results": "Fetch current result page from a background search run.",
    "cancel_visa_job_search": "Request cancellation of an in-progress background run.",
    "discover_latest_dol_disclosure_urls": "Discover latest DOL LCA/PERM disclosure sources.",
    "run_internal_dol_pipeline": "Run internal pipeline to refresh sponsor-company dataset.",
    "refresh_company_dataset_cache": "Clear and reload in-memory company dataset cache.",
}


def tool_contract_entry(
    *,
    name: str,
    required_inputs: list[str],
    optional_inputs: list[str] | None = None,
) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "name": name,
        "description": TOOL_DESCRIPTIONS.get(name, ""),
        "required_inputs": required_inputs,
    }
    if optional_inputs:
        entry["optional_inputs"] = optional_inputs
    return entry


@mcp.tool()
def get_mcp_capabilities() -> dict[str, Any]:
    """Return machine-readable MCP capability metadata for agents."""
    return {
        "server": "visa-jobs-mcp",
        "version": PACKAGE_VERSION,
        "capabilities_schema_version": CAPABILITIES_SCHEMA_VERSION,
        "confidence_model_version": CONFIDENCE_MODEL_VERSION,
        "design_decisions": {
            "llm_runtime_inside_mcp": False,
            "llm_api_keys_required_by_mcp": False,
            "agent_is_reasoning_layer": True,
            "proxies_used": False,
            "free_forever": True,
            "license": "MIT",
            "data_not_shared_or_sold": True,
            "no_fake_reviews_or_bot_marketing": True,
            "fresh_job_search_per_query": True,
            "supported_job_sites": sorted(SUPPORTED_SITES),
            "strict_user_visa_match": True,
            "strictness_modes_supported": sorted(SUPPORTED_STRICTNESS_MODES),
            "search_sessions_local_persistence": True,
            "background_search_runs_local_persistence": True,
            "saved_jobs_local_persistence": True,
            "ignored_jobs_local_persistence": True,
            "ignored_companies_local_persistence": True,
            "first_class_job_management": True,
            "rate_limit_backoff_retries": True,
        },
        "required_before_search": {
            "tool": "set_user_preferences",
            "required_fields": ["user_id", "preferred_visa_types"],
        },
        "defaults": {
            "search_session_ttl_seconds": int(DEFAULT_SEARCH_SESSION_TTL_SECONDS),
            "max_search_sessions_per_user": int(DEFAULT_MAX_SEARCH_SESSIONS_PER_USER),
            "search_run_ttl_seconds": int(DEFAULT_SEARCH_RUN_TTL_SECONDS),
            "scan_multiplier": int(DEFAULT_SCAN_MULTIPLIER),
            "max_scan_results": int(DEFAULT_MAX_SCAN_RESULTS),
            "strictness_mode": "strict",
            "dataset_stale_after_days": int(DEFAULT_DATASET_STALE_AFTER_DAYS),
            "job_db_path": DEFAULT_JOB_DB_PATH,
            "tool_call_soft_timeout_seconds": int(DEFAULT_TOOL_CALL_SOFT_TIMEOUT_SECONDS),
            "rate_limit_retry_window_seconds": int(DEFAULT_RATE_LIMIT_RETRY_WINDOW_SECONDS),
            "rate_limit_initial_backoff_seconds": int(DEFAULT_RATE_LIMIT_INITIAL_BACKOFF_SECONDS),
            "rate_limit_max_backoff_seconds": int(DEFAULT_RATE_LIMIT_MAX_BACKOFF_SECONDS),
        },
        "tools": [
            tool_contract_entry(
                name="set_user_preferences",
                required_inputs=["user_id", "preferred_visa_types"],
            ),
            tool_contract_entry(name="set_user_constraints", required_inputs=["user_id"]),
            tool_contract_entry(name="get_user_preferences", required_inputs=["user_id"]),
            tool_contract_entry(name="get_user_readiness", required_inputs=["user_id"]),
            tool_contract_entry(name="find_related_titles", required_inputs=["job_title"]),
            tool_contract_entry(name="add_user_memory_line", required_inputs=["user_id", "content"]),
            tool_contract_entry(name="query_user_memory_blob", required_inputs=["user_id"]),
            tool_contract_entry(name="delete_user_memory_line", required_inputs=["user_id", "line_id"]),
            tool_contract_entry(
                name="save_job_for_later",
                required_inputs=["user_id"],
                optional_inputs=["job_url", "result_id", "session_id"],
            ),
            tool_contract_entry(name="list_saved_jobs", required_inputs=["user_id"]),
            tool_contract_entry(name="delete_saved_job", required_inputs=["user_id", "saved_job_id"]),
            tool_contract_entry(
                name="ignore_job",
                required_inputs=["user_id"],
                optional_inputs=["job_url", "result_id", "session_id"],
            ),
            tool_contract_entry(name="list_ignored_jobs", required_inputs=["user_id"]),
            tool_contract_entry(name="unignore_job", required_inputs=["user_id", "ignored_job_id"]),
            tool_contract_entry(name="ignore_company", required_inputs=["user_id"]),
            tool_contract_entry(name="list_ignored_companies", required_inputs=["user_id"]),
            tool_contract_entry(name="unignore_company", required_inputs=["user_id", "ignored_company_id"]),
            tool_contract_entry(name="mark_job_applied", required_inputs=["user_id"]),
            tool_contract_entry(name="update_job_stage", required_inputs=["user_id", "stage"]),
            tool_contract_entry(name="list_jobs_by_stage", required_inputs=["user_id", "stage"]),
            tool_contract_entry(name="add_job_note", required_inputs=["user_id", "note"]),
            tool_contract_entry(name="list_recent_job_events", required_inputs=["user_id"]),
            tool_contract_entry(name="get_job_pipeline_summary", required_inputs=["user_id"]),
            tool_contract_entry(name="clear_search_session", required_inputs=["user_id"]),
            tool_contract_entry(name="export_user_data", required_inputs=["user_id"]),
            tool_contract_entry(name="delete_user_data", required_inputs=["user_id", "confirm"]),
            tool_contract_entry(name="get_best_contact_strategy", required_inputs=["user_id"]),
            tool_contract_entry(name="generate_outreach_message", required_inputs=["user_id"]),
            tool_contract_entry(
                name="start_visa_job_search",
                required_inputs=["location", "job_title", "user_id"],
            ),
            tool_contract_entry(name="get_visa_job_search_status", required_inputs=["user_id", "run_id"]),
            tool_contract_entry(name="get_visa_job_search_results", required_inputs=["user_id", "run_id"]),
            tool_contract_entry(name="cancel_visa_job_search", required_inputs=["user_id", "run_id"]),
            tool_contract_entry(name="discover_latest_dol_disclosure_urls", required_inputs=[]),
            tool_contract_entry(name="run_internal_dol_pipeline", required_inputs=[]),
            tool_contract_entry(name="refresh_company_dataset_cache", required_inputs=[]),
        ],
        "search_response_fields_for_agents": [
            "jobs[].result_id",
            "jobs[].job_url",
            "jobs[].employer_contacts",
            "jobs[].visa_counts",
            "jobs[].visas_sponsored",
            "jobs[].visa_match_strength",
            "jobs[].eligibility_reasons",
            "jobs[].confidence_score",
            "jobs[].confidence_model_version",
            "jobs[].contactability_score",
            "jobs[].matched_via_company_dataset",
            "jobs[].matched_via_job_description",
            "jobs[].matches_user_visa_preferences",
            "search_progress",
            "feedback_summary",
            "personalization_notes",
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
            "search_runs_store_default": DEFAULT_SEARCH_RUNS_PATH,
            "saved_jobs_default": DEFAULT_SAVED_JOBS_PATH,
            "ignored_jobs_default": DEFAULT_IGNORED_JOBS_PATH,
            "ignored_companies_default": DEFAULT_IGNORED_COMPANIES_PATH,
            "job_management_db_default": DEFAULT_JOB_DB_PATH,
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
    ignored_companies_entry = _get_ignored_companies_entry(_load_ignored_companies(), uid) or {}
    ignored_companies_count = len(ignored_companies_entry.get("companies", []))
    runs_store = _prune_search_runs(_load_search_runs())
    runs = runs_store.get("runs", {})
    active_search_runs_count = 0
    if isinstance(runs, dict):
        for record in runs.values():
            if not isinstance(record, dict):
                continue
            query = record.get("query", {})
            if not isinstance(query, dict):
                continue
            if str(query.get("user_id", "")).strip() != uid:
                continue
            status = str(record.get("status", "")).strip().lower()
            if status in {"pending", "running", "cancelling"}:
                active_search_runs_count += 1
    _ensure_job_management_ready()
    stage_counts = {stage: 0 for stage in sorted(VALID_JOB_STAGES)}
    with _job_db_conn() as conn:
        stage_rows = conn.execute(
            """
            SELECT stage, COUNT(*) AS count
            FROM job_applications
            WHERE user_id = ?
            GROUP BY stage
            """,
            (uid,),
        ).fetchall()
        for row in stage_rows:
            stage_key = str(row["stage"]).strip().lower()
            if stage_key in stage_counts:
                stage_counts[stage_key] = int(row["count"])

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
            "Call set_user_preferences first (required before start_visa_job_search)."
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
            "ignored_companies_count": int(ignored_companies_count),
            "active_search_runs_count": int(active_search_runs_count),
            "job_stage_counts": stage_counts,
            "applied_jobs_count": int(stage_counts.get("applied", 0)),
        },
        "dataset_freshness": freshness,
        "paths": {
            "dataset_path": dataset_path,
            "manifest_path": manifest_path_resolved,
            "preferences_path": DEFAULT_USER_PREFS_PATH,
            "memory_blob_path": DEFAULT_USER_BLOB_PATH,
            "saved_jobs_path": DEFAULT_SAVED_JOBS_PATH,
            "ignored_jobs_path": DEFAULT_IGNORED_JOBS_PATH,
            "ignored_companies_path": DEFAULT_IGNORED_COMPANIES_PATH,
            "search_runs_path": DEFAULT_SEARCH_RUNS_PATH,
            "job_db_path": DEFAULT_JOB_DB_PATH,
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
