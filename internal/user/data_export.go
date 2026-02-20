package user

import "fmt"

func loadUserScopedStore(path string) map[string]any {
	return loadJSONMap(path, map[string]any{"users": map[string]any{}})
}

func saveUserScopedStore(path string, data map[string]any) error {
	return saveJSONMap(path, data)
}

func getUserList(path string, userID, listKey string) []any {
	store := loadUserScopedStore(path)
	users := getUsersMap(store)
	entry := mapOrNil(users[userID])
	if entry == nil {
		return []any{}
	}
	return listOrEmpty(entry[listKey])
}

func removeUserFromStore(path string, userID, listKey string) (int, error) {
	store := loadUserScopedStore(path)
	users := getUsersMap(store)
	entry := mapOrNil(users[userID])
	if entry == nil {
		return 0, nil
	}
	count := len(listOrEmpty(entry[listKey]))
	delete(users, userID)
	store["users"] = users
	if err := saveUserScopedStore(path, store); err != nil {
		return 0, err
	}
	return count, nil
}

func loadSearchSessions() map[string]any {
	return loadJSONMap(searchSessionsPath(), map[string]any{"sessions": map[string]any{}})
}

func saveSearchSessions(data map[string]any) error {
	return saveJSONMap(searchSessionsPath(), data)
}

func loadSearchRuns() map[string]any {
	return loadJSONMap(searchRunsPath(), map[string]any{"runs": map[string]any{}})
}

func saveSearchRuns(data map[string]any) error {
	return saveJSONMap(searchRunsPath(), data)
}

func exportSearchSessions(userID string) []any {
	store := loadSearchSessions()
	sessions := mapOrNil(store["sessions"])
	if sessions == nil {
		return []any{}
	}

	out := []any{}
	for sid, recordAny := range sessions {
		record := mapOrNil(recordAny)
		if record == nil {
			continue
		}
		query := mapOrNil(record["query"])
		if query == nil || getString(query, "user_id") != userID {
			continue
		}
		item := map[string]any{
			"session_id":          sid,
			"created_at_utc":      record["created_at_utc"],
			"updated_at_utc":      record["updated_at_utc"],
			"expires_at_utc":      record["expires_at_utc"],
			"query":               query,
			"accepted_jobs_total": intOrZero(record["accepted_jobs_total"]),
			"latest_scan_target":  intOrZero(record["latest_scan_target"]),
			"scan_exhausted":      boolOrFalse(record["scan_exhausted"]),
		}
		out = append(out, item)
	}
	return out
}

func removeSearchSessions(userID string) (int, error) {
	store := loadSearchSessions()
	sessions := mapOrNil(store["sessions"])
	if sessions == nil {
		return 0, nil
	}

	removed := 0
	for sid, recordAny := range sessions {
		record := mapOrNil(recordAny)
		if record == nil {
			continue
		}
		query := mapOrNil(record["query"])
		if query == nil || getString(query, "user_id") != userID {
			continue
		}
		delete(sessions, sid)
		removed++
	}
	if removed == 0 {
		return 0, nil
	}
	store["sessions"] = sessions
	if err := saveSearchSessions(store); err != nil {
		return 0, err
	}
	return removed, nil
}

func exportSearchRuns(userID string) []any {
	store := loadSearchRuns()
	runs := mapOrNil(store["runs"])
	if runs == nil {
		return []any{}
	}

	out := []any{}
	for runID, recordAny := range runs {
		record := mapOrNil(recordAny)
		if record == nil {
			continue
		}
		query := mapOrNil(record["query"])
		if query == nil || getString(query, "user_id") != userID {
			continue
		}
		item := map[string]any{
			"run_id":            runID,
			"status":            getString(record, "status"),
			"created_at_utc":    record["created_at_utc"],
			"updated_at_utc":    record["updated_at_utc"],
			"completed_at_utc":  record["completed_at_utc"],
			"expires_at_utc":    record["expires_at_utc"],
			"attempt_count":     intOrZero(record["attempt_count"]),
			"search_session_id": getString(record, "search_session_id"),
			"query":             query,
		}
		out = append(out, item)
	}
	return out
}

func removeSearchRuns(userID string) (int, error) {
	store := loadSearchRuns()
	runs := mapOrNil(store["runs"])
	if runs == nil {
		return 0, nil
	}

	removed := 0
	for runID, recordAny := range runs {
		record := mapOrNil(recordAny)
		if record == nil {
			continue
		}
		query := mapOrNil(record["query"])
		if query == nil || getString(query, "user_id") != userID {
			continue
		}
		delete(runs, runID)
		removed++
	}
	if removed == 0 {
		return 0, nil
	}
	store["runs"] = runs
	if err := saveSearchRuns(store); err != nil {
		return 0, err
	}
	return removed, nil
}

func intOrZero(value any) int {
	if parsed, ok := intFromAny(value); ok {
		return parsed
	}
	return 0
}

func boolOrFalse(value any) bool {
	if parsed, ok := boolFromAny(value); ok {
		return parsed
	}
	return false
}

func ExportUserData(args map[string]any) (map[string]any, error) {
	userID := getString(args, "user_id")
	if userID == "" {
		return nil, fmt.Errorf("user_id is required")
	}

	prefsStore, err := loadPrefs()
	if err != nil {
		return nil, err
	}
	prefs := asMap(prefsStore[userID])
	memoryLines := getUserList(userBlobPath(), userID, "lines")
	savedJobs := getUserList(savedJobsPath(), userID, "jobs")
	ignoredJobs := getUserList(ignoredJobsPath(), userID, "jobs")
	ignoredCompanies := getUserList(ignoredCompaniesPath(), userID, "companies")
	searchSessions := exportSearchSessions(userID)
	searchRuns := exportSearchRuns(userID)
	jobMgmt := getPipelineEntry(loadJobPipeline(), userID)
	jobMgmtJobs := []any{}
	jobMgmtApplications := []any{}
	jobMgmtEvents := []any{}
	if jobMgmt != nil {
		for _, row := range jobMgmt["jobs"].([]map[string]any) {
			jobMgmtJobs = append(jobMgmtJobs, row)
		}
		for _, row := range jobMgmt["applications"].([]map[string]any) {
			jobMgmtApplications = append(jobMgmtApplications, row)
		}
		for _, row := range jobMgmt["events"].([]map[string]any) {
			jobMgmtEvents = append(jobMgmtEvents, row)
		}
	}

	return map[string]any{
		"user_id":         userID,
		"exported_at_utc": utcNowISO(),
		"data": map[string]any{
			"preferences":       prefs,
			"memory_lines":      memoryLines,
			"saved_jobs":        savedJobs,
			"ignored_jobs":      ignoredJobs,
			"ignored_companies": ignoredCompanies,
			"search_sessions":   searchSessions,
			"search_runs":       searchRuns,
			"job_management": map[string]any{
				"jobs":         jobMgmtJobs,
				"applications": jobMgmtApplications,
				"events":       jobMgmtEvents,
			},
		},
		"counts": map[string]any{
			"memory_lines":                len(memoryLines),
			"saved_jobs":                  len(savedJobs),
			"ignored_jobs":                len(ignoredJobs),
			"ignored_companies":           len(ignoredCompanies),
			"search_sessions":             len(searchSessions),
			"search_runs":                 len(searchRuns),
			"job_management_jobs":         len(jobMgmtJobs),
			"job_management_applications": len(jobMgmtApplications),
			"job_management_events":       len(jobMgmtEvents),
		},
		"paths": map[string]any{
			"preferences_path":       prefsPath(),
			"memory_blob_path":       userBlobPath(),
			"saved_jobs_path":        savedJobsPath(),
			"ignored_jobs_path":      ignoredJobsPath(),
			"ignored_companies_path": ignoredCompaniesPath(),
			"search_sessions_path":   searchSessionsPath(),
			"search_runs_path":       searchRunsPath(),
			"job_db_path":            jobDBPath(),
		},
	}, nil
}

func DeleteUserData(args map[string]any) (map[string]any, error) {
	userID := getString(args, "user_id")
	if userID == "" {
		return nil, fmt.Errorf("user_id is required")
	}
	confirm, hasConfirm, err := getOptionalBool(args, "confirm")
	if !hasConfirm || !confirm {
		return nil, fmt.Errorf("confirm=true is required to delete user data")
	}
	if err != nil {
		return nil, fmt.Errorf("confirm must be a boolean when provided")
	}

	deleted := map[string]any{
		"preferences":                 false,
		"memory_lines":                0,
		"saved_jobs":                  0,
		"ignored_jobs":                0,
		"ignored_companies":           0,
		"search_sessions":             0,
		"search_runs":                 0,
		"job_management_jobs":         0,
		"job_management_applications": 0,
		"job_management_events":       0,
	}

	prefsStore, err := loadPrefs()
	if err != nil {
		return nil, err
	}
	if _, exists := prefsStore[userID]; exists {
		delete(prefsStore, userID)
		if err := savePrefs(prefsStore); err != nil {
			return nil, err
		}
		deleted["preferences"] = true
	}

	if count, err := removeUserFromStore(userBlobPath(), userID, "lines"); err != nil {
		return nil, err
	} else {
		deleted["memory_lines"] = count
	}
	if count, err := removeUserFromStore(savedJobsPath(), userID, "jobs"); err != nil {
		return nil, err
	} else {
		deleted["saved_jobs"] = count
	}
	if count, err := removeUserFromStore(ignoredJobsPath(), userID, "jobs"); err != nil {
		return nil, err
	} else {
		deleted["ignored_jobs"] = count
	}
	if count, err := removeUserFromStore(ignoredCompaniesPath(), userID, "companies"); err != nil {
		return nil, err
	} else {
		deleted["ignored_companies"] = count
	}
	if count, err := removeSearchSessions(userID); err != nil {
		return nil, err
	} else {
		deleted["search_sessions"] = count
	}
	if count, err := removeSearchRuns(userID); err != nil {
		return nil, err
	} else {
		deleted["search_runs"] = count
	}
	pipeline := loadJobPipeline()
	entry := getPipelineEntry(pipeline, userID)
	if entry != nil {
		deleted["job_management_jobs"] = len(entry["jobs"].([]map[string]any))
		deleted["job_management_applications"] = len(entry["applications"].([]map[string]any))
		deleted["job_management_events"] = len(entry["events"].([]map[string]any))
		users := getUsersMap(pipeline)
		delete(users, userID)
		pipeline["users"] = users
		if err := saveJobPipeline(pipeline); err != nil {
			return nil, err
		}
	}

	return map[string]any{
		"user_id": userID,
		"deleted": deleted,
		"paths": map[string]any{
			"preferences_path":       prefsPath(),
			"memory_blob_path":       userBlobPath(),
			"saved_jobs_path":        savedJobsPath(),
			"ignored_jobs_path":      ignoredJobsPath(),
			"ignored_companies_path": ignoredCompaniesPath(),
			"search_sessions_path":   searchSessionsPath(),
			"search_runs_path":       searchRunsPath(),
			"job_db_path":            jobDBPath(),
		},
	}, nil
}
