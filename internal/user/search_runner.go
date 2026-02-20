package user

import (
	"errors"
)

func runCancelled(runID string) bool {
	cancelRequested := false
	_ = withSearchRunStore(false, func(store map[string]any) error {
		runs := mapOrNil(store["runs"])
		run := mapOrNil(runs[runID])
		if run != nil {
			cancelRequested = boolOrFalse(run["cancel_requested"])
		}
		return nil
	})
	return cancelRequested
}

func executeSearchRun(runID string) {
	_ = updateRun(runID, func(run map[string]any) error {
		run["status"] = "running"
		appendRunEvent(run, "running", "Background search is running.", 2, nil)
		return nil
	})

	run, err := loadRunByID(runID)
	if err != nil {
		_ = updateRun(runID, func(record map[string]any) error {
			record["status"] = "failed"
			record["error"] = err.Error()
			record["completed_at_utc"] = utcNowISO()
			appendRunEvent(record, "failed", err.Error(), 100, nil)
			return nil
		})
		return
	}
	queryMap := mapOrNil(run["query"])
	query := searchQuery{
		RunID:                    runID,
		UserID:                   getString(queryMap, "user_id"),
		SearchMode:               searchModeOrDefault(getString(queryMap, "search_mode")),
		Location:                 getString(queryMap, "location"),
		JobTitle:                 getString(queryMap, "job_title"),
		HoursOld:                 intOrZero(queryMap["hours_old"]),
		DatasetPath:              getString(queryMap, "dataset_path"),
		Site:                     getString(queryMap, "site"),
		ResultsWanted:            intOrZero(queryMap["results_wanted"]),
		MaxReturned:              intOrZero(queryMap["max_returned"]),
		Offset:                   intOrZero(queryMap["offset"]),
		RequireDescriptionSignal: boolOrFalse(queryMap["require_description_signal"]),
		StrictnessMode:           strictnessOrDefault(getString(queryMap, "strictness_mode")),
		RefreshSession:           boolOrFalse(queryMap["refresh_session"]),
		ScanMultiplier:           intOrZero(queryMap["scan_multiplier"]),
		MaxScanResults:           intOrZero(queryMap["max_scan_results"]),
	}
	if query.HoursOld < 1 {
		query.HoursOld = defaultSearchHoursOld
	}
	if query.DatasetPath == "" {
		query.DatasetPath = datasetPathOrDefault("")
	}
	if query.Site == "" {
		query.Site = "linkedin"
	}
	if query.SearchMode == "" {
		query.SearchMode = searchModeGeneral
	}
	if query.ResultsWanted < 1 {
		query.ResultsWanted = defaultSearchResultsWanted
	}
	if query.MaxReturned < 1 {
		query.MaxReturned = defaultSearchMaxReturned
	}
	if query.ScanMultiplier < 1 {
		query.ScanMultiplier = defaultSearchScanMultiplier
	}
	if query.MaxScanResults < query.ResultsWanted {
		query.MaxScanResults = max(defaultSearchMaxScanResults, query.ResultsWanted)
	}

	progress := func(phase, detail string, pct float64, payload map[string]any) {
		_ = updateRun(runID, func(run map[string]any) error {
			appendRunEvent(run, phase, detail, pct, payload)
			return nil
		})
	}

	response, stats, sessionID, err := executeSearchQuery(query, progress, func() bool {
		return runCancelled(runID)
	})
	if err != nil {
		_ = updateRun(runID, func(run map[string]any) error {
			if errors.Is(err, errSearchRunCancelled) || boolOrFalse(run["cancel_requested"]) {
				run["status"] = "cancelled"
				run["error"] = ""
				run["completed_at_utc"] = utcNowISO()
				appendRunEvent(run, "cancelled", "Search run cancelled.", 100, nil)
				return nil
			}
			run["status"] = "failed"
			run["error"] = err.Error()
			run["completed_at_utc"] = utcNowISO()
			appendRunEvent(run, "failed", err.Error(), 100, nil)
			return nil
		})
		return
	}
	_ = updateRun(runID, func(run map[string]any) error {
		run["status"] = "completed"
		run["search_session_id"] = sessionID
		run["latest_response"] = response
		run["latest_stats"] = stats
		run["completed_at_utc"] = utcNowISO()
		run["error"] = ""
		return nil
	})
}
