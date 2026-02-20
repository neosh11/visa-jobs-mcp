from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor
import threading

from .base import *  # noqa: F401,F403


def label_visa_types_for_feedback(visa_types: list[str]) -> list[str]:
    labels: list[str] = []
    for visa_type in visa_types:
        labels.append(VISA_TYPE_LABELS.get(visa_type, visa_type))
    return labels


def build_personalization_notes(
    *,
    user_id: str,
    desired_visa_types: list[str],
) -> list[str]:
    notes: list[str] = []
    visa_labels = label_visa_types_for_feedback(desired_visa_types)
    if visa_labels:
        notes.append(f"Filtering to requested visa type(s): {', '.join(visa_labels)}.")

    prefs = _load_user_prefs().get(user_id, {})
    if not isinstance(prefs, dict):
        return notes

    constraints = prefs.get("constraints", {})
    if not isinstance(constraints, dict):
        return notes

    days_remaining = constraints.get("days_remaining")
    if isinstance(days_remaining, int):
        if days_remaining <= 30:
            notes.append(f"High urgency profile: user reports {days_remaining} day(s) remaining.")
        else:
            notes.append(f"User reports {days_remaining} day(s) remaining on visa timeline.")

    work_modes = constraints.get("work_modes", [])
    if isinstance(work_modes, list):
        cleaned_modes = [str(mode).strip().lower() for mode in work_modes if str(mode).strip()]
        if cleaned_modes:
            notes.append(f"Preferred work modes: {', '.join(sorted(set(cleaned_modes)))}.")

    if constraints.get("willing_to_relocate") is True:
        notes.append("User is open to relocation.")
    elif constraints.get("willing_to_relocate") is False:
        notes.append("User is not open to relocation.")

    return notes


def build_feedback_summary(
    *,
    location: str,
    job_title: str,
    strictness_mode: str,
    desired_visa_types: list[str],
    returned_jobs: int,
    accepted_jobs_total: int,
    has_next_page: bool,
    next_offset: int | None,
    search_session_id: str,
    call_budget_exhausted: bool,
    recovery_suggestions: list[dict[str, Any]],
    personalization_notes: list[str],
) -> dict[str, Any]:
    visa_labels = label_visa_types_for_feedback(desired_visa_types)
    visa_text = ", ".join(visa_labels) if visa_labels else "visa sponsorship"

    if returned_jobs > 0:
        why_this_set = (
            f"Showing {returned_jobs} role(s) for '{job_title}' in {location} "
            f"using {strictness_mode} matching for {visa_text}."
        )
    else:
        why_this_set = (
            f"No role matched '{job_title}' in {location} for {visa_text} yet. "
            "Use the retry/session guidance to continue the scan."
        )

    actions: list[str] = []
    if returned_jobs > 0:
        actions.append("Ask the user which jobs to save for follow-up.")
        actions.append("Ask the user which jobs to ignore as irrelevant.")
        actions.append("Ask if the user already applied to any and call mark_job_applied.")
    if has_next_page and next_offset is not None:
        actions.append(
            "Fetch the next page using the same session_id "
            f"('{search_session_id}') and offset={int(next_offset)}."
        )
    if returned_jobs == 0:
        actions.append("Retry find_visa_sponsored_jobs with the same session_id to continue scanning.")
    if recovery_suggestions:
        actions.append("If still sparse, ask user approval for one recovery_suggestion.")
    if call_budget_exhausted:
        actions.append("Search hit the tool call time budget; continue with the same session_id.")

    alignment = (
        "High urgency support mode: prioritize immediate outreach and quick apply loops."
        if any("High urgency profile" in note for note in personalization_notes)
        else "Prioritize roles with strong visa evidence and reachable employer contacts."
    )

    return {
        "why_this_set": why_this_set,
        "what_to_do_next": actions,
        "user_goal_alignment": alignment,
        "accepted_jobs_total": int(accepted_jobs_total),
    }


_SEARCH_RUN_WORKER_COUNT = max(1, _env_int("VISA_SEARCH_RUN_WORKERS", 2))
_SEARCH_RUN_EXECUTOR = ThreadPoolExecutor(
    max_workers=_SEARCH_RUN_WORKER_COUNT,
    thread_name_prefix="visa-search-run",
)
_SEARCH_RUN_LOCK = threading.Lock()
_SEARCH_RUN_FUTURES: dict[str, Future[Any]] = {}


def _search_run_is_terminal(status: str) -> bool:
    return status in {"completed", "failed", "cancelled"}


def _clone_run_payload(value: dict[str, Any]) -> dict[str, Any]:
    return json.loads(json.dumps(value))


def _load_pruned_search_runs_store() -> dict[str, Any]:
    return _prune_search_runs(_load_search_runs())


def _save_pruned_search_runs_store(store: dict[str, Any]) -> None:
    _save_search_runs(_prune_search_runs(store))


def _append_search_run_event(
    run: dict[str, Any],
    *,
    phase: str,
    detail: str,
    progress_percent: float | None = None,
    payload: dict[str, Any] | None = None,
) -> None:
    events = run.get("events")
    if not isinstance(events, list):
        events = []
    try:
        event_id = int(run.get("next_event_id", len(events)))
    except (TypeError, ValueError):
        event_id = len(events)
    event = {
        "event_id": int(max(0, event_id)),
        "at_utc": _utcnow_iso(),
        "phase": phase,
        "detail": detail,
    }
    if progress_percent is not None:
        event["progress_percent"] = float(max(0.0, min(100.0, progress_percent)))
    if payload:
        event["payload"] = payload
    events.append(event)
    run["events"] = events
    run["next_event_id"] = event["event_id"] + 1


def _search_run_next_scan_target(
    *,
    current: int,
    max_returned: int,
    scan_multiplier: int,
    max_scan_results: int,
) -> int:
    proposed = max(current * 2, current + (max_returned * scan_multiplier))
    return min(max_scan_results, proposed)


def _search_run_worker(run_id: str) -> None:
    while True:
        with _SEARCH_RUN_LOCK:
            store = _load_pruned_search_runs_store()
            runs = store.setdefault("runs", {})
            run = runs.get(run_id)
            if not isinstance(run, dict):
                return

            status = str(run.get("status", "")).strip().lower()
            if _search_run_is_terminal(status):
                return

            if bool(run.get("cancel_requested", False)):
                run["status"] = "cancelled"
                run["completed_at_utc"] = _utcnow_iso()
                _append_search_run_event(
                    run,
                    phase="cancelled",
                    detail="Search run cancelled.",
                    progress_percent=100.0,
                )
                run["updated_at_utc"] = _utcnow_iso()
                runs[run_id] = run
                store["runs"] = runs
                _save_pruned_search_runs_store(store)
                return

            run["status"] = "running"
            run["updated_at_utc"] = _utcnow_iso()
            runs[run_id] = run
            store["runs"] = runs
            _save_pruned_search_runs_store(store)
            query = run.get("query", {})
            if not isinstance(query, dict):
                query = {}

            location = str(query.get("location", "")).strip()
            job_title = str(query.get("job_title", "")).strip()
            user_id = str(query.get("user_id", "")).strip()
            dataset_path = str(query.get("dataset_path", DEFAULT_DATASET_PATH)).strip() or DEFAULT_DATASET_PATH
            site_name = str(query.get("site", "linkedin")).strip() or "linkedin"
            hours_old = int(query.get("hours_old", 336) or 336)
            require_description_signal = bool(query.get("require_description_signal", False))
            strictness_mode = str(query.get("strictness_mode", "strict")).strip() or "strict"
            requested_offset = int(query.get("offset", 0) or 0)
            requested_max_returned = int(query.get("max_returned", 10) or 10)
            configured_max_scan_results = int(query.get("max_scan_results", DEFAULT_MAX_SCAN_RESULTS) or DEFAULT_MAX_SCAN_RESULTS)
            configured_scan_multiplier = int(query.get("scan_multiplier", DEFAULT_SCAN_MULTIPLIER) or DEFAULT_SCAN_MULTIPLIER)
            refresh_session = bool(query.get("refresh_session", False))
            try:
                current_scan_target = int(run.get("current_scan_target", query.get("results_wanted", 300)) or 300)
            except (TypeError, ValueError):
                current_scan_target = 300
            if current_scan_target < 1:
                current_scan_target = 1
            current_session_id = str(run.get("search_session_id", "")).strip()
            run_attempt = int(run.get("attempt_count", 0) or 0) + 1

        try:
            response = find_visa_sponsored_jobs(
                location=location,
                job_title=job_title,
                user_id=user_id,
                results_wanted=current_scan_target,
                hours_old=hours_old,
                dataset_path=dataset_path,
                sites=[site_name],
                max_returned=requested_max_returned,
                offset=requested_offset,
                require_description_signal=require_description_signal,
                strictness_mode=strictness_mode,
                session_id=current_session_id,
                refresh_session=bool(refresh_session and not current_session_id),
                auto_expand_scan=False,
                scan_multiplier=configured_scan_multiplier,
                max_scan_results=current_scan_target,
            )
        except Exception as exc:
            with _SEARCH_RUN_LOCK:
                store = _load_pruned_search_runs_store()
                runs = store.setdefault("runs", {})
                run = runs.get(run_id)
                if not isinstance(run, dict):
                    return
                run["status"] = "failed"
                run["error"] = str(exc)
                run["completed_at_utc"] = _utcnow_iso()
                run["attempt_count"] = int(run.get("attempt_count", 0) or 0) + 1
                _append_search_run_event(
                    run,
                    phase="failed",
                    detail=f"Search run failed: {exc}",
                    progress_percent=100.0,
                )
                run["updated_at_utc"] = _utcnow_iso()
                runs[run_id] = run
                store["runs"] = runs
                _save_pruned_search_runs_store(store)
            return

        pagination = response.get("pagination", {})
        stats = response.get("stats", {})
        search_session = response.get("search_session", {})
        accepted_total = int(pagination.get("accepted_jobs_total", 0) or 0)
        accepted_needed = int(pagination.get("accepted_jobs_needed_for_page", requested_offset + requested_max_returned) or (requested_offset + requested_max_returned))
        scan_exhausted = bool(pagination.get("scan_exhausted", False))
        next_scan_target = _search_run_next_scan_target(
            current=current_scan_target,
            max_returned=max(1, requested_max_returned),
            scan_multiplier=max(1, configured_scan_multiplier),
            max_scan_results=max(current_scan_target, configured_max_scan_results),
        )
        completed = bool(
            accepted_total >= accepted_needed
            or scan_exhausted
            or next_scan_target <= current_scan_target
            or current_scan_target >= max(current_scan_target, configured_max_scan_results)
        )
        progress_percent = (
            100.0
            if completed
            else min(99.0, round((accepted_total / max(1, accepted_needed)) * 100.0, 2))
        )

        with _SEARCH_RUN_LOCK:
            store = _load_pruned_search_runs_store()
            runs = store.setdefault("runs", {})
            run = runs.get(run_id)
            if not isinstance(run, dict):
                return

            run["attempt_count"] = run_attempt
            run["current_scan_target"] = int(current_scan_target if completed else next_scan_target)
            run["latest_response"] = response
            run["search_session_id"] = str(search_session.get("session_id", "")).strip()
            run["latest_stats"] = {
                "accepted_jobs_total": accepted_total,
                "accepted_jobs_needed_for_page": accepted_needed,
                "returned_jobs": int(stats.get("returned_jobs", 0) or 0),
                "scraped_jobs": int(stats.get("scraped_jobs", 0) or 0),
                "scan_exhausted": scan_exhausted,
                "requested_scan_target": int(pagination.get("requested_scan_target", current_scan_target) or current_scan_target),
            }
            _append_search_run_event(
                run,
                phase="scan_chunk_completed",
                detail=(
                    f"Chunk {run_attempt}: scanned {int(stats.get('scraped_jobs', 0) or 0)} posting(s), "
                    f"accepted {accepted_total} role(s)."
                ),
                progress_percent=progress_percent,
                payload={
                    "attempt": run_attempt,
                    "accepted_jobs_total": accepted_total,
                    "accepted_jobs_needed_for_page": accepted_needed,
                    "scan_target": int(current_scan_target),
                    "next_scan_target": int(next_scan_target),
                    "scan_exhausted": scan_exhausted,
                },
            )

            if completed:
                run["status"] = "completed"
                run["completed_at_utc"] = _utcnow_iso()
            else:
                run["status"] = "running"
            run["updated_at_utc"] = _utcnow_iso()
            runs[run_id] = run
            store["runs"] = runs
            _save_pruned_search_runs_store(store)

        if completed:
            return


def _submit_search_run(run_id: str) -> None:
    future = _SEARCH_RUN_EXECUTOR.submit(_search_run_worker, run_id)
    with _SEARCH_RUN_LOCK:
        _SEARCH_RUN_FUTURES[run_id] = future

    def _cleanup(done_future: Future[Any]) -> None:
        _ = done_future
        with _SEARCH_RUN_LOCK:
            _SEARCH_RUN_FUTURES.pop(run_id, None)

    future.add_done_callback(_cleanup)


def _load_search_run_for_user(*, run_id: str, user_id: str) -> dict[str, Any]:
    with _SEARCH_RUN_LOCK:
        store = _load_pruned_search_runs_store()
        runs = store.get("runs", {})
        if not isinstance(runs, dict):
            raise ValueError("search run store is unavailable")
        record = runs.get(run_id)
        if not isinstance(record, dict):
            raise ValueError(f"Unknown run_id '{run_id}'.")
        query = record.get("query", {})
        owner = str(query.get("user_id", "")).strip() if isinstance(query, dict) else ""
        if owner != user_id.strip():
            raise ValueError("run_id does not belong to this user_id.")
        return _clone_run_payload(record)


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
    call_started_mono = time.monotonic()
    search_progress: list[dict[str, Any]] = []

    def add_progress(phase: str, detail: str, jobs_scanned_so_far: int) -> None:
        search_progress.append(
            {
                "phase": phase,
                "status": "completed",
                "detail": detail,
                "elapsed_seconds": round(max(0.0, time.monotonic() - call_started_mono), 2),
                "jobs_scanned_so_far": int(max(0, jobs_scanned_so_far)),
            }
        )

    soft_timeout_seconds = max(10, int(DEFAULT_TOOL_CALL_SOFT_TIMEOUT_SECONDS))
    deadline_mono = call_started_mono + float(soft_timeout_seconds)
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
    personalization_notes = build_personalization_notes(
        user_id=user_id,
        desired_visa_types=desired_visa_types,
    )
    add_progress(
        "search_started",
        "Validated inputs and initialized search context.",
        jobs_scanned_so_far=0,
    )

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
    call_budget_exhausted = False
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
        add_progress(
            "scraping_linkedin",
            "Reused cached search session results; no new scrape needed.",
            jobs_scanned_so_far=last_scraped_jobs_count,
        )
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
            remaining_budget_seconds = max(0.0, deadline_mono - time.monotonic())
            if remaining_budget_seconds <= 3.0 and scan_attempts:
                call_budget_exhausted = True
                break

            effective_retry_window_seconds = min(
                int(DEFAULT_RATE_LIMIT_RETRY_WINDOW_SECONDS),
                max(0, int(remaining_budget_seconds - 2.0)),
            )
            if effective_retry_window_seconds <= 0:
                call_budget_exhausted = True
                break
            attempt_timeout_seconds = min(
                int(DEFAULT_SCRAPE_ATTEMPT_TIMEOUT_SECONDS),
                max(1, int(remaining_budget_seconds - 2.0)),
            )

            try:
                raw_jobs, scrape_attempts, scrape_backoff_seconds = _scrape_jobs_with_backoff(
                    site_name=chosen_sites,
                    search_term=job_title,
                    location=location,
                    results_wanted=scan_target,
                    hours_old=hours_old,
                    country_indeed=DEFAULT_INDEED_COUNTRY,
                    retry_window_seconds=effective_retry_window_seconds,
                    initial_backoff_seconds=DEFAULT_RATE_LIMIT_INITIAL_BACKOFF_SECONDS,
                    max_backoff_seconds=DEFAULT_RATE_LIMIT_MAX_BACKOFF_SECONDS,
                    attempt_timeout_seconds=attempt_timeout_seconds,
                )
            except Exception as exc:
                if _is_scrape_timeout_error(exc):
                    call_budget_exhausted = True
                    add_progress(
                        "scraping_linkedin",
                        "Current scrape attempt timed out; returning partial results for continuation.",
                        jobs_scanned_so_far=int(last_scraped_jobs_count),
                    )
                    break
                raise
            rate_limit_retry_attempts += max(0, scrape_attempts - 1)
            rate_limit_backoff_seconds += float(scrape_backoff_seconds)
            raw_jobs = _dedupe_raw_jobs(raw_jobs)
            last_raw_jobs = raw_jobs
            add_progress(
                "scraping_linkedin",
                f"Scanned {len(raw_jobs)} posting(s) with results_wanted={int(scan_target)}.",
                jobs_scanned_so_far=int(len(raw_jobs)),
            )

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
            can_expand_scan = (
                auto_expand_scan
                and len(evaluated_results) < required_accepted_for_page
                and len(raw_jobs) >= scan_target
                and scan_target < max_scan_results
            )
            next_scan_target = (
                min(
                    max_scan_results,
                    max(scan_target * 2, scan_target + (max_returned * scan_multiplier)),
                )
                if can_expand_scan
                else scan_target
            )
            if time.monotonic() >= deadline_mono:
                call_budget_exhausted = True
                if next_scan_target > scan_target:
                    # Persist deeper target so the next call with the same session resumes progress.
                    scan_target = next_scan_target
                break

            if not auto_expand_scan:
                break
            if len(evaluated_results) >= required_accepted_for_page:
                break
            if len(raw_jobs) < scan_target:
                break
            if scan_target >= max_scan_results:
                break

            if next_scan_target <= scan_target:
                break
            scan_target = next_scan_target

        accepted_job_dicts = [asdict(job) for job in evaluated_results]
        last_scraped_jobs_count = int(len(last_raw_jobs))
        if scan_attempts:
            last_requested_scan_target = max(int(scan_attempts[-1]["results_wanted"]), int(scan_target))
        else:
            last_requested_scan_target = scan_target
        scan_exhausted = (
            len(accepted_job_dicts) < required_accepted_for_page
            and (
                not auto_expand_scan
                or last_requested_scan_target >= max_scan_results
                or last_scraped_jobs_count < last_requested_scan_target
                or call_budget_exhausted
            )
        )

    accepted_job_dicts = _attach_result_ids(search_session_id, accepted_job_dicts)
    ignored_job_urls = _ignored_job_url_set(user_id)
    ignored_company_names = _ignored_company_name_set(user_id)
    filtered_accepted_job_dicts = (
        [
            job
            for job in accepted_job_dicts
            if (
                str(job.get("job_url", "")).strip().lower() not in ignored_job_urls
                and (
                    not ignored_company_names
                    or normalize_company_name(str(job.get("company", "")).strip())
                    not in ignored_company_names
                )
            )
        ]
        if (ignored_job_urls or ignored_company_names)
        else accepted_job_dicts
    )
    ignored_filtered_count = len(accepted_job_dicts) - len(filtered_accepted_job_dicts)
    ignored_company_filtered_count = sum(
        1
        for job in accepted_job_dicts
        if (
            normalize_company_name(str(job.get("company", "")).strip()) in ignored_company_names
            and str(job.get("job_url", "")).strip().lower() not in ignored_job_urls
        )
    )
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
    add_progress(
        "matching_sponsors",
        f"Matched {len(accepted_job_dicts)} posting(s) against sponsorship evidence.",
        jobs_scanned_so_far=last_scraped_jobs_count,
    )
    add_progress(
        "filtering_by_user_visa",
        (
            f"Filtered to {len(filtered_accepted_job_dicts)} posting(s) after "
            f"user visa preference and ignore rules."
        ),
        jobs_scanned_so_far=last_scraped_jobs_count,
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
        "tool_call_time_budget_exhausted": bool(call_budget_exhausted),
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
    add_progress(
        "done",
        f"Returning {returned_jobs} posting(s) for this page.",
        jobs_scanned_so_far=last_scraped_jobs_count,
    )
    feedback_summary = build_feedback_summary(
        location=location,
        job_title=job_title,
        strictness_mode=normalized_strictness_mode,
        desired_visa_types=desired_visa_types,
        returned_jobs=returned_jobs,
        accepted_jobs_total=len(filtered_accepted_job_dicts),
        has_next_page=has_next_page,
        next_offset=next_offset,
        search_session_id=search_session_id,
        call_budget_exhausted=bool(call_budget_exhausted),
        recovery_suggestions=recovery_suggestions,
        personalization_notes=personalization_notes,
    )

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
            "tool_call_soft_timeout_seconds": int(soft_timeout_seconds),
            "rate_limit_retry_window_seconds": int(DEFAULT_RATE_LIMIT_RETRY_WINDOW_SECONDS),
            "rate_limit_initial_backoff_seconds": int(DEFAULT_RATE_LIMIT_INITIAL_BACKOFF_SECONDS),
            "rate_limit_max_backoff_seconds": int(DEFAULT_RATE_LIMIT_MAX_BACKOFF_SECONDS),
            "scrape_attempt_timeout_seconds": int(DEFAULT_SCRAPE_ATTEMPT_TIMEOUT_SECONDS),
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
            "ignored_company_filtered_count": int(ignored_company_filtered_count),
            "accepted_jobs": int(len(filtered_accepted_job_dicts)),
            "returned_jobs": int(returned_jobs),
            "cache_hit": bool(cache_hit),
            "scan_attempts": int(len(scan_attempts)),
            "scan_attempts_detail": scan_attempts,
            "tool_call_time_budget_exhausted": bool(call_budget_exhausted),
            "rate_limit_retry_attempts": int(rate_limit_retry_attempts),
            "rate_limit_backoff_seconds": float(round(rate_limit_backoff_seconds, 2)),
            "confidence_model_version": CONFIDENCE_MODEL_VERSION,
        },
        "search_progress": search_progress,
        "personalization_notes": personalization_notes,
        "feedback_summary": feedback_summary,
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
            "ask_user_to_ignore_companies_prompt": (
                "Ask the user if they want to hide entire companies from future results. "
                "If yes, call ignore_company with company_name or result_id."
            ),
            "ignore_company_tool": "ignore_company",
            "ask_user_to_mark_applied_prompt": (
                "Ask the user whether they have already applied to any returned jobs. "
                "If yes, call mark_job_applied using result_id (or job_url)."
            ),
            "mark_applied_tool": "mark_job_applied",
            "rate_limit_guidance": (
                "If a search fails with a rate-limit error, wait a few minutes and retry the same call."
            ),
            "if_no_results_retry_same_call": (
                "If no jobs are returned, retry find_visa_sponsored_jobs with the same session_id. "
                "The server will continue the scan from where it left off."
            ),
            "long_search_guidance": (
                "If your MCP client has a short tool timeout, use start_visa_job_search and poll "
                "get_visa_job_search_status for live progress until completed, then call "
                "get_visa_job_search_results."
            ),
            "background_search_tools": {
                "start": "start_visa_job_search",
                "status": "get_visa_job_search_status",
                "results": "get_visa_job_search_results",
                "cancel": "cancel_visa_job_search",
            },
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
            "retry_hint_when_no_results": (
                {
                    "tool": "find_visa_sponsored_jobs",
                    "session_id": search_session_id,
                    "offset": 0,
                    "max_returned": int(max_returned),
                    "results_wanted": int(max(results_wanted, last_requested_scan_target)),
                    "refresh_session": False,
                }
                if len(filtered_accepted_job_dicts) == 0
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
def start_visa_job_search(
    location: str,
    job_title: str,
    user_id: str,
    results_wanted: int = 300,
    hours_old: int = 336,
    dataset_path: str = DEFAULT_DATASET_PATH,
    site: str = "linkedin",
    max_returned: int = 10,
    offset: int = 0,
    require_description_signal: bool = False,
    strictness_mode: str = "strict",
    refresh_session: bool = False,
    scan_multiplier: int = DEFAULT_SCAN_MULTIPLIER,
    max_scan_results: int = DEFAULT_MAX_SCAN_RESULTS,
) -> dict[str, Any]:
    """Start a background visa job search run and return immediately."""
    if not location.strip():
        raise ValueError("location is required")
    if not job_title.strip():
        raise ValueError("job_title is required")
    if not user_id.strip():
        raise ValueError("user_id is required")
    if results_wanted < 1:
        raise ValueError("results_wanted must be >= 1")
    if max_returned < 1:
        raise ValueError("max_returned must be >= 1")
    if offset < 0:
        raise ValueError("offset must be >= 0")
    if scan_multiplier < 1:
        raise ValueError("scan_multiplier must be >= 1")
    if max_scan_results < results_wanted:
        max_scan_results = results_wanted
    clean_site = site.strip().lower()
    if clean_site not in SUPPORTED_SITES:
        raise ValueError(f"Only LinkedIn is supported right now. Invalid site: {clean_site!r}")
    _normalize_strictness_mode(strictness_mode)
    _get_required_user_visa_types(user_id)

    run_id = uuid.uuid4().hex
    created_at_utc = _utcnow_iso()
    expires_at_utc = _future_utc_iso(DEFAULT_SEARCH_RUN_TTL_SECONDS)
    run_record = {
        "run_id": run_id,
        "status": "pending",
        "created_at_utc": created_at_utc,
        "updated_at_utc": created_at_utc,
        "completed_at_utc": "",
        "expires_at_utc": expires_at_utc,
        "cancel_requested": False,
        "attempt_count": 0,
        "current_scan_target": int(results_wanted),
        "search_session_id": "",
        "latest_response": {},
        "latest_stats": {},
        "error": "",
        "next_event_id": 0,
        "events": [],
        "query": {
            "location": location,
            "job_title": job_title,
            "user_id": user_id,
            "results_wanted": int(results_wanted),
            "hours_old": int(hours_old),
            "dataset_path": dataset_path,
            "site": clean_site,
            "max_returned": int(max_returned),
            "offset": int(offset),
            "require_description_signal": bool(require_description_signal),
            "strictness_mode": strictness_mode,
            "refresh_session": bool(refresh_session),
            "scan_multiplier": int(scan_multiplier),
            "max_scan_results": int(max_scan_results),
        },
    }
    _append_search_run_event(
        run_record,
        phase="started",
        detail="Background search started.",
        progress_percent=0.0,
    )

    with _SEARCH_RUN_LOCK:
        store = _load_pruned_search_runs_store()
        runs = store.setdefault("runs", {})
        runs[run_id] = run_record
        store["runs"] = runs
        _save_pruned_search_runs_store(store)

    _submit_search_run(run_id)
    return {
        "run_id": run_id,
        "status": "pending",
        "user_id": user_id,
        "created_at_utc": created_at_utc,
        "expires_at_utc": expires_at_utc,
        "next_cursor": int(run_record.get("next_event_id", 0)),
        "search_runs_path": DEFAULT_SEARCH_RUNS_PATH,
        "poll_tool": "get_visa_job_search_status",
        "results_tool": "get_visa_job_search_results",
        "cancel_tool": "cancel_visa_job_search",
    }


@mcp.tool()
def get_visa_job_search_status(user_id: str, run_id: str, cursor: int = 0) -> dict[str, Any]:
    """Poll an in-progress background search run for incremental progress events."""
    uid = user_id.strip()
    rid = run_id.strip()
    if not uid:
        raise ValueError("user_id is required")
    if not rid:
        raise ValueError("run_id is required")
    if cursor < 0:
        raise ValueError("cursor must be >= 0")

    run = _load_search_run_for_user(run_id=rid, user_id=uid)
    events = run.get("events", [])
    if not isinstance(events, list):
        events = []
    safe_cursor = min(cursor, len(events))
    returned_events = events[safe_cursor:]
    next_cursor = len(events)
    status = str(run.get("status", "")).strip().lower()
    latest_stats = run.get("latest_stats", {})
    if not isinstance(latest_stats, dict):
        latest_stats = {}
    latest_response = run.get("latest_response", {})
    if not isinstance(latest_response, dict):
        latest_response = {}

    return {
        "run_id": rid,
        "user_id": uid,
        "status": status,
        "is_terminal": _search_run_is_terminal(status),
        "cancel_requested": bool(run.get("cancel_requested", False)),
        "attempt_count": int(run.get("attempt_count", 0) or 0),
        "created_at_utc": run.get("created_at_utc"),
        "updated_at_utc": run.get("updated_at_utc"),
        "completed_at_utc": run.get("completed_at_utc") or None,
        "expires_at_utc": run.get("expires_at_utc"),
        "search_session_id": run.get("search_session_id", ""),
        "current_scan_target": int(run.get("current_scan_target", 0) or 0),
        "error": run.get("error", ""),
        "events": returned_events,
        "cursor": int(safe_cursor),
        "next_cursor": int(next_cursor),
        "has_more_events": False,
        "latest_stats": latest_stats,
        "latest_pagination": latest_response.get("pagination", {}),
        "latest_returned_jobs": int((latest_response.get("stats", {}) or {}).get("returned_jobs", 0) or 0),
        "can_fetch_results": bool(latest_response),
        "search_runs_path": DEFAULT_SEARCH_RUNS_PATH,
    }


@mcp.tool()
def get_visa_job_search_results(
    user_id: str,
    run_id: str,
    offset: int | None = None,
    max_returned: int | None = None,
) -> dict[str, Any]:
    """Fetch result page from a background search run."""
    uid = user_id.strip()
    rid = run_id.strip()
    if not uid:
        raise ValueError("user_id is required")
    if not rid:
        raise ValueError("run_id is required")
    run = _load_search_run_for_user(run_id=rid, user_id=uid)
    query = run.get("query", {})
    if not isinstance(query, dict):
        raise ValueError("search run query payload is unavailable")
    latest_response = run.get("latest_response", {})
    if not isinstance(latest_response, dict) or not latest_response:
        raise ValueError("No result snapshot yet. Poll get_visa_job_search_status until results are available.")

    requested_offset = int(offset if offset is not None else int(query.get("offset", 0) or 0))
    requested_page_size = int(max_returned if max_returned is not None else int(query.get("max_returned", 10) or 10))
    if requested_offset < 0:
        raise ValueError("offset must be >= 0")
    if requested_page_size < 1:
        raise ValueError("max_returned must be >= 1")

    query_offset = int(query.get("offset", 0) or 0)
    query_page_size = int(query.get("max_returned", 10) or 10)
    if requested_offset == query_offset and requested_page_size == query_page_size:
        return {
            **latest_response,
            "run": {
                "run_id": rid,
                "status": run.get("status", ""),
                "attempt_count": int(run.get("attempt_count", 0) or 0),
                "search_runs_path": DEFAULT_SEARCH_RUNS_PATH,
            },
        }

    session_id = str(run.get("search_session_id", "")).strip()
    if not session_id:
        raise ValueError("search_session_id is unavailable for this run.")
    min_scan_target = max(
        int(run.get("current_scan_target", 0) or 0),
        int(requested_offset + requested_page_size),
    )
    result = find_visa_sponsored_jobs(
        location=str(query.get("location", "")).strip(),
        job_title=str(query.get("job_title", "")).strip(),
        user_id=uid,
        results_wanted=max(1, min_scan_target),
        hours_old=int(query.get("hours_old", 336) or 336),
        dataset_path=str(query.get("dataset_path", DEFAULT_DATASET_PATH)).strip() or DEFAULT_DATASET_PATH,
        sites=[str(query.get("site", "linkedin")).strip() or "linkedin"],
        max_returned=requested_page_size,
        offset=requested_offset,
        require_description_signal=bool(query.get("require_description_signal", False)),
        strictness_mode=str(query.get("strictness_mode", "strict")).strip() or "strict",
        session_id=session_id,
        refresh_session=False,
        auto_expand_scan=False,
        scan_multiplier=max(1, int(query.get("scan_multiplier", DEFAULT_SCAN_MULTIPLIER) or DEFAULT_SCAN_MULTIPLIER)),
        max_scan_results=max(1, min_scan_target),
    )
    return {
        **result,
        "run": {
            "run_id": rid,
            "status": run.get("status", ""),
            "attempt_count": int(run.get("attempt_count", 0) or 0),
            "search_runs_path": DEFAULT_SEARCH_RUNS_PATH,
        },
    }


@mcp.tool()
def cancel_visa_job_search(user_id: str, run_id: str) -> dict[str, Any]:
    """Cancel an in-progress background search run."""
    uid = user_id.strip()
    rid = run_id.strip()
    if not uid:
        raise ValueError("user_id is required")
    if not rid:
        raise ValueError("run_id is required")

    with _SEARCH_RUN_LOCK:
        store = _load_pruned_search_runs_store()
        runs = store.get("runs", {})
        if not isinstance(runs, dict):
            raise ValueError("search run store is unavailable")
        run = runs.get(rid)
        if not isinstance(run, dict):
            raise ValueError(f"Unknown run_id '{rid}'.")
        query = run.get("query", {})
        owner = str(query.get("user_id", "")).strip() if isinstance(query, dict) else ""
        if owner != uid:
            raise ValueError("run_id does not belong to this user_id.")

        status = str(run.get("status", "")).strip().lower()
        if _search_run_is_terminal(status):
            return {
                "run_id": rid,
                "user_id": uid,
                "status": status,
                "cancel_requested": False,
                "search_runs_path": DEFAULT_SEARCH_RUNS_PATH,
            }

        run["cancel_requested"] = True
        run["status"] = "cancelling"
        _append_search_run_event(
            run,
            phase="cancelling",
            detail="Cancellation requested. The run will stop after the current chunk.",
        )
        run["updated_at_utc"] = _utcnow_iso()
        runs[rid] = run
        store["runs"] = runs
        _save_pruned_search_runs_store(store)

    return {
        "run_id": rid,
        "user_id": uid,
        "status": "cancelling",
        "cancel_requested": True,
        "search_runs_path": DEFAULT_SEARCH_RUNS_PATH,
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
