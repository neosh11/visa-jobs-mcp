from __future__ import annotations

from .base import *  # noqa: F401,F403

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
            "fresh_search": True,
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


