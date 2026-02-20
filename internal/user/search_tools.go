package user

import (
	"fmt"
	"strings"
)

type searchToolNames struct {
	PollTool    string
	ResultsTool string
	CancelTool  string
}

func searchRunIsTerminal(status string) bool {
	clean := strings.ToLower(strings.TrimSpace(status))
	return clean == "completed" || clean == "failed" || clean == "cancelled"
}

func StartVisaJobSearch(args map[string]any) (map[string]any, error) {
	return startJobSearchWithMode(args, searchModeVisa, searchToolNames{
		PollTool:    "get_visa_job_search_status",
		ResultsTool: "get_visa_job_search_results",
		CancelTool:  "cancel_visa_job_search",
	})
}

func StartJobSearch(args map[string]any) (map[string]any, error) {
	return startJobSearchWithMode(args, searchModeGeneral, searchToolNames{
		PollTool:    "get_job_search_status",
		ResultsTool: "get_job_search_results",
		CancelTool:  "cancel_job_search",
	})
}

func startJobSearchWithMode(args map[string]any, mode string, names searchToolNames) (map[string]any, error) {
	location := getString(args, "location")
	jobTitle := getString(args, "job_title")
	userID := getString(args, "user_id")
	if location == "" {
		return nil, fmt.Errorf("location is required")
	}
	if jobTitle == "" {
		return nil, fmt.Errorf("job_title is required")
	}
	if userID == "" {
		return nil, fmt.Errorf("user_id is required")
	}

	site, err := normalizeSearchSite(getString(args, "site"))
	if err != nil {
		return nil, err
	}

	strictness := strictnessOrDefault(getString(args, "strictness_mode"))
	if strictness != "strict" && strictness != "balanced" {
		return nil, fmt.Errorf("strictness_mode must be one of [balanced strict]")
	}

	resultsWanted := defaultSearchResultsWanted
	if parsed, has, err := getOptionalInt(args, "results_wanted"); has {
		if err != nil {
			return nil, fmt.Errorf("results_wanted must be an integer when provided")
		}
		if parsed < 1 {
			return nil, fmt.Errorf("results_wanted must be >= 1")
		}
		resultsWanted = parsed
	}
	maxReturned := defaultSearchMaxReturned
	if parsed, has, err := getOptionalInt(args, "max_returned"); has {
		if err != nil {
			return nil, fmt.Errorf("max_returned must be an integer when provided")
		}
		if parsed < 1 {
			return nil, fmt.Errorf("max_returned must be >= 1")
		}
		maxReturned = parsed
	}
	offset := 0
	if parsed, has, err := getOptionalInt(args, "offset"); has {
		if err != nil {
			return nil, fmt.Errorf("offset must be an integer when provided")
		}
		if parsed < 0 {
			return nil, fmt.Errorf("offset must be >= 0")
		}
		offset = parsed
	}
	hoursOld := defaultSearchHoursOld
	if parsed, has, err := getOptionalInt(args, "hours_old"); has {
		if err != nil {
			return nil, fmt.Errorf("hours_old must be an integer when provided")
		}
		if parsed < 1 {
			parsed = 1
		}
		hoursOld = parsed
	}
	requireDescriptionSignal := false
	if parsed, has, err := getOptionalBool(args, "require_description_signal"); has {
		if err != nil {
			return nil, fmt.Errorf("require_description_signal must be a boolean when provided")
		}
		requireDescriptionSignal = parsed
	}
	refreshSession := false
	if parsed, has, err := getOptionalBool(args, "refresh_session"); has {
		if err != nil {
			return nil, fmt.Errorf("refresh_session must be a boolean when provided")
		}
		refreshSession = parsed
	}
	scanMultiplier := defaultSearchScanMultiplier
	if parsed, has, err := getOptionalInt(args, "scan_multiplier"); has {
		if err != nil {
			return nil, fmt.Errorf("scan_multiplier must be an integer when provided")
		}
		if parsed < 1 {
			return nil, fmt.Errorf("scan_multiplier must be >= 1")
		}
		scanMultiplier = parsed
	}
	maxScanResults := defaultSearchMaxScanResults
	if parsed, has, err := getOptionalInt(args, "max_scan_results"); has {
		if err != nil {
			return nil, fmt.Errorf("max_scan_results must be an integer when provided")
		}
		if parsed < resultsWanted {
			parsed = resultsWanted
		}
		maxScanResults = parsed
	}
	datasetPath := datasetPathOrDefault(getString(args, "dataset_path"))

	runID := newRunID()
	createdAt := utcNowISO()
	expiresAt := futureISO(searchRunTTLSeconds())
	query := map[string]any{
		"search_mode":                mode,
		"location":                   location,
		"job_title":                  jobTitle,
		"user_id":                    userID,
		"results_wanted":             resultsWanted,
		"hours_old":                  hoursOld,
		"dataset_path":               datasetPath,
		"site":                       site,
		"max_returned":               maxReturned,
		"offset":                     offset,
		"require_description_signal": requireDescriptionSignal,
		"strictness_mode":            strictness,
		"refresh_session":            refreshSession,
		"scan_multiplier":            scanMultiplier,
		"max_scan_results":           maxScanResults,
	}
	run := map[string]any{
		"run_id":              runID,
		"status":              "pending",
		"created_at_utc":      createdAt,
		"updated_at_utc":      createdAt,
		"completed_at_utc":    "",
		"expires_at_utc":      expiresAt,
		"cancel_requested":    false,
		"attempt_count":       0,
		"current_scan_target": max(resultsWanted, offset+maxReturned),
		"search_session_id":   "",
		"latest_response":     map[string]any{},
		"latest_stats":        map[string]any{},
		"error":               "",
		"next_event_id":       0,
		"events":              []any{},
		"query":               query,
	}
	appendRunEvent(run, "started", "Background search started.", 0, nil)

	if err := withSearchRunStore(true, func(store map[string]any) error {
		runs := mapOrNil(store["runs"])
		if runs == nil {
			runs = map[string]any{}
		}
		runs[runID] = run
		store["runs"] = runs
		return nil
	}); err != nil {
		return nil, err
	}

	go executeSearchRun(runID)
	return map[string]any{
		"run_id":           runID,
		"status":           "pending",
		"user_id":          userID,
		"search_mode":      mode,
		"created_at_utc":   createdAt,
		"expires_at_utc":   expiresAt,
		"next_cursor":      intOrZero(run["next_event_id"]),
		"search_runs_path": searchRunsPath(),
		"poll_tool":        names.PollTool,
		"results_tool":     names.ResultsTool,
		"cancel_tool":      names.CancelTool,
	}, nil
}

func GetVisaJobSearchStatus(args map[string]any) (map[string]any, error) {
	return getJobSearchStatus(args)
}

func GetJobSearchStatus(args map[string]any) (map[string]any, error) {
	return getJobSearchStatus(args)
}

func getJobSearchStatus(args map[string]any) (map[string]any, error) {
	userID := getString(args, "user_id")
	runID := getString(args, "run_id")
	if userID == "" {
		return nil, fmt.Errorf("user_id is required")
	}
	if runID == "" {
		return nil, fmt.Errorf("run_id is required")
	}
	cursor := 0
	if parsed, has, err := getOptionalInt(args, "cursor"); has {
		if err != nil {
			return nil, fmt.Errorf("cursor must be an integer when provided")
		}
		if parsed < 0 {
			return nil, fmt.Errorf("cursor must be >= 0")
		}
		cursor = parsed
	}

	run, err := loadRunForUser(runID, userID)
	if err != nil {
		return nil, err
	}
	events := listOrEmpty(run["events"])
	safeCursor := cursor
	if safeCursor > len(events) {
		safeCursor = len(events)
	}
	status := strings.ToLower(getString(run, "status"))
	latestStats := asMap(run["latest_stats"])
	latestResponse := asMap(run["latest_response"])
	return map[string]any{
		"run_id":           runID,
		"user_id":          userID,
		"status":           status,
		"is_terminal":      searchRunIsTerminal(status),
		"cancel_requested": boolOrFalse(run["cancel_requested"]),
		"attempt_count":    intOrZero(run["attempt_count"]),
		"created_at_utc":   run["created_at_utc"],
		"updated_at_utc":   run["updated_at_utc"],
		"completed_at_utc": func() any {
			text := getString(run, "completed_at_utc")
			if text == "" {
				return nil
			}
			return text
		}(),
		"expires_at_utc":       run["expires_at_utc"],
		"search_session_id":    getString(run, "search_session_id"),
		"current_scan_target":  intOrZero(run["current_scan_target"]),
		"error":                getString(run, "error"),
		"events":               events[safeCursor:],
		"cursor":               safeCursor,
		"next_cursor":          len(events),
		"has_more_events":      false,
		"latest_stats":         latestStats,
		"latest_pagination":    asMap(latestResponse["pagination"]),
		"latest_returned_jobs": intOrZero(asMap(latestResponse["stats"])["returned_jobs"]),
		"can_fetch_results":    len(latestResponse) > 0,
		"search_runs_path":     searchRunsPath(),
	}, nil
}

func GetVisaJobSearchResults(args map[string]any) (map[string]any, error) {
	return getJobSearchResults(args, "get_visa_job_search_status")
}

func GetJobSearchResults(args map[string]any) (map[string]any, error) {
	return getJobSearchResults(args, "get_job_search_status")
}

func getJobSearchResults(args map[string]any, statusToolName string) (map[string]any, error) {
	userID := getString(args, "user_id")
	runID := getString(args, "run_id")
	if userID == "" {
		return nil, fmt.Errorf("user_id is required")
	}
	if runID == "" {
		return nil, fmt.Errorf("run_id is required")
	}
	run, err := loadRunForUser(runID, userID)
	if err != nil {
		return nil, err
	}
	query := mapOrNil(run["query"])
	if query == nil {
		return nil, fmt.Errorf("search run query payload is unavailable")
	}
	latestResponse := asMap(run["latest_response"])
	if len(latestResponse) == 0 {
		return nil, fmt.Errorf("no result snapshot yet; poll %s until results are available", statusToolName)
	}

	requestedOffset := intOrZero(query["offset"])
	if parsed, has, err := getOptionalInt(args, "offset"); has {
		if err != nil {
			return nil, fmt.Errorf("offset must be an integer when provided")
		}
		if parsed < 0 {
			return nil, fmt.Errorf("offset must be >= 0")
		}
		requestedOffset = parsed
	}
	requestedMax := intOrZero(query["max_returned"])
	if requestedMax < 1 {
		requestedMax = defaultSearchMaxReturned
	}
	if parsed, has, err := getOptionalInt(args, "max_returned"); has {
		if err != nil {
			return nil, fmt.Errorf("max_returned must be an integer when provided")
		}
		if parsed < 1 {
			return nil, fmt.Errorf("max_returned must be >= 1")
		}
		requestedMax = parsed
	}

	defaultOffset := intOrZero(query["offset"])
	defaultMax := intOrZero(query["max_returned"])
	if defaultMax < 1 {
		defaultMax = defaultSearchMaxReturned
	}
	response := latestResponse
	if requestedOffset != defaultOffset || requestedMax != defaultMax {
		sessionID := getString(run, "search_session_id")
		if sessionID == "" {
			return nil, fmt.Errorf("search_session_id is unavailable for this run")
		}
		session, err := loadSearchSessionForUser(sessionID, userID)
		if err != nil {
			return nil, err
		}
		accepted := []map[string]any{}
		for _, raw := range listOrEmpty(session["accepted_jobs"]) {
			row := mapOrNil(raw)
			if row != nil {
				accepted = append(accepted, row)
			}
		}
		page, pagination := sliceAcceptedJobs(
			accepted,
			requestedOffset,
			requestedMax,
			intOrZero(session["latest_scan_target"]),
			max(defaultSearchMaxScanResults, intOrZero(query["max_scan_results"])),
			boolOrFalse(session["scan_exhausted"]),
		)
		response = rebuildResponsePage(latestResponse, page, pagination)
	}
	return map[string]any{
		"run": map[string]any{
			"run_id":           runID,
			"status":           getString(run, "status"),
			"attempt_count":    intOrZero(run["attempt_count"]),
			"search_runs_path": searchRunsPath(),
		},
		"status":               asMap(response["status"]),
		"stats":                asMap(response["stats"]),
		"guidance":             asMap(response["guidance"]),
		"dataset_freshness":    asMap(response["dataset_freshness"]),
		"pagination":           asMap(response["pagination"]),
		"recovery_suggestions": listOrEmpty(response["recovery_suggestions"]),
		"jobs":                 listOrEmpty(response["jobs"]),
	}, nil
}

func CancelVisaJobSearch(args map[string]any) (map[string]any, error) {
	return cancelJobSearch(args)
}

func CancelJobSearch(args map[string]any) (map[string]any, error) {
	return cancelJobSearch(args)
}

func cancelJobSearch(args map[string]any) (map[string]any, error) {
	userID := getString(args, "user_id")
	runID := getString(args, "run_id")
	if userID == "" {
		return nil, fmt.Errorf("user_id is required")
	}
	if runID == "" {
		return nil, fmt.Errorf("run_id is required")
	}

	status := ""
	cancelRequested := false
	err := withSearchRunStore(true, func(store map[string]any) error {
		runs := mapOrNil(store["runs"])
		if runs == nil {
			return fmt.Errorf("search run store is unavailable")
		}
		run := mapOrNil(runs[runID])
		if run == nil {
			return fmt.Errorf("unknown run_id '%s'", runID)
		}
		query := mapOrNil(run["query"])
		if query == nil || getString(query, "user_id") != userID {
			return fmt.Errorf("run_id does not belong to this user_id")
		}
		status = strings.ToLower(getString(run, "status"))
		if searchRunIsTerminal(status) {
			cancelRequested = false
			return nil
		}
		run["cancel_requested"] = true
		run["status"] = "cancelling"
		appendRunEvent(run, "cancelling", "Cancellation requested. The run will stop after the current chunk.", -1, nil)
		runs[runID] = run
		store["runs"] = runs
		status = "cancelling"
		cancelRequested = true
		return nil
	})
	if err != nil {
		return nil, err
	}
	return map[string]any{
		"run_id":           runID,
		"user_id":          userID,
		"status":           status,
		"cancel_requested": cancelRequested,
		"search_runs_path": searchRunsPath(),
	}, nil
}
