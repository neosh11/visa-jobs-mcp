package user

import (
	"fmt"
	"slices"
	"strings"
)

func MarkJobApplied(args map[string]any) (map[string]any, error) {
	userID := getString(args, "user_id")
	if userID == "" {
		return nil, fmt.Errorf("user_id is required")
	}
	pipeline := loadJobPipeline()
	entry := ensurePipelineEntry(pipeline, userID)
	jobID, _, err := resolveJobManagementTarget(entry, args, userID)
	if err != nil {
		return nil, err
	}

	sourceSessionID := getString(args, "session_id")
	resultID := getString(args, "result_id")
	if sourceSessionID == "" && strings.Contains(resultID, ":") {
		sourceSessionID = strings.TrimSpace(strings.SplitN(resultID, ":", 2)[0])
	}
	application, event, err := setJobStage(
		entry,
		userID,
		jobID,
		"applied",
		getString(args, "note"),
		sourceSessionID,
		getString(args, "applied_at_utc"),
		"mark_job_applied",
	)
	if err != nil {
		return nil, err
	}
	if err := saveJobPipeline(pipeline); err != nil {
		return nil, err
	}
	snapshot, err := jobSnapshot(entry, userID, jobID)
	if err != nil {
		return nil, err
	}
	return map[string]any{
		"user_id":     userID,
		"job":         snapshot,
		"application": application,
		"event":       event,
		"job_db_path": jobDBPath(),
	}, nil
}

func UpdateJobStage(args map[string]any) (map[string]any, error) {
	userID := getString(args, "user_id")
	if userID == "" {
		return nil, fmt.Errorf("user_id is required")
	}
	cleanStage, err := validateJobStage(getString(args, "stage"))
	if err != nil {
		return nil, err
	}
	pipeline := loadJobPipeline()
	entry := ensurePipelineEntry(pipeline, userID)
	jobID, _, err := resolveJobManagementTarget(entry, args, userID)
	if err != nil {
		return nil, err
	}

	sourceSessionID := getString(args, "session_id")
	resultID := getString(args, "result_id")
	if sourceSessionID == "" && strings.Contains(resultID, ":") {
		sourceSessionID = strings.TrimSpace(strings.SplitN(resultID, ":", 2)[0])
	}
	application, event, err := setJobStage(
		entry,
		userID,
		jobID,
		cleanStage,
		getString(args, "note"),
		sourceSessionID,
		"",
		"update_job_stage",
	)
	if err != nil {
		return nil, err
	}
	if err := saveJobPipeline(pipeline); err != nil {
		return nil, err
	}
	snapshot, err := jobSnapshot(entry, userID, jobID)
	if err != nil {
		return nil, err
	}
	return map[string]any{
		"user_id":     userID,
		"job":         snapshot,
		"application": application,
		"event":       event,
		"job_db_path": jobDBPath(),
	}, nil
}

func AddJobNote(args map[string]any) (map[string]any, error) {
	userID := getString(args, "user_id")
	if userID == "" {
		return nil, fmt.Errorf("user_id is required")
	}
	note := getString(args, "note")
	if note == "" {
		return nil, fmt.Errorf("note is required")
	}
	pipeline := loadJobPipeline()
	entry := ensurePipelineEntry(pipeline, userID)
	jobID, _, err := resolveJobManagementTarget(entry, args, userID)
	if err != nil {
		return nil, err
	}
	application, event, err := appendJobNote(entry, userID, jobID, note)
	if err != nil {
		return nil, err
	}
	if err := saveJobPipeline(pipeline); err != nil {
		return nil, err
	}
	snapshot, err := jobSnapshot(entry, userID, jobID)
	if err != nil {
		return nil, err
	}
	return map[string]any{
		"user_id":     userID,
		"job":         snapshot,
		"application": application,
		"event":       event,
		"job_db_path": jobDBPath(),
	}, nil
}

func ListJobsByStage(args map[string]any) (map[string]any, error) {
	userID := getString(args, "user_id")
	if userID == "" {
		return nil, fmt.Errorf("user_id is required")
	}
	stage, err := validateJobStage(getString(args, "stage"))
	if err != nil {
		return nil, err
	}
	limit := 50
	if parsed, has, err := getOptionalInt(args, "limit"); has {
		if err != nil {
			return nil, fmt.Errorf("limit must be an integer when provided")
		}
		if parsed < 1 {
			parsed = 1
		}
		if parsed > 200 {
			parsed = 200
		}
		limit = parsed
	}
	offset := 0
	if parsed, has, err := getOptionalInt(args, "offset"); has {
		if err != nil {
			return nil, fmt.Errorf("offset must be an integer when provided")
		}
		if parsed < 0 {
			parsed = 0
		}
		offset = parsed
	}

	pipeline := loadJobPipeline()
	entry := getPipelineEntry(pipeline, userID)
	if entry == nil {
		return map[string]any{
			"user_id":       userID,
			"stage":         stage,
			"offset":        offset,
			"limit":         limit,
			"total_jobs":    0,
			"returned_jobs": 0,
			"jobs":          []any{},
			"job_db_path":   jobDBPath(),
		}, nil
	}

	jobs := entry["jobs"].([]map[string]any)
	filtered := []map[string]any{}
	for _, app := range entry["applications"].([]map[string]any) {
		if getString(app, "stage") != stage {
			continue
		}
		jobID, _ := intFromAny(app["job_id"])
		job := getJobByID(entry, jobID)
		if job == nil {
			continue
		}
		filtered = append(filtered, map[string]any{
			"job_id":               jobID,
			"result_id":            getString(job, "result_id"),
			"job_url":              getString(job, "job_url"),
			"title":                getString(job, "title"),
			"company":              getString(job, "company"),
			"location":             getString(job, "location"),
			"site":                 getString(job, "site"),
			"stage":                getString(app, "stage"),
			"applied_at_utc":       getString(app, "applied_at_utc"),
			"source_session_id":    getString(app, "source_session_id"),
			"note":                 getString(app, "note"),
			"stage_updated_at_utc": getString(app, "updated_at_utc"),
		})
	}
	_ = jobs
	slices.SortFunc(filtered, func(a, b map[string]any) int {
		av := getString(a, "stage_updated_at_utc")
		bv := getString(b, "stage_updated_at_utc")
		return strings.Compare(bv, av)
	})
	if offset > len(filtered) {
		offset = len(filtered)
	}
	end := offset + limit
	if end > len(filtered) {
		end = len(filtered)
	}
	page := filtered[offset:end]
	pageAny := make([]any, 0, len(page))
	for _, row := range page {
		pageAny = append(pageAny, row)
	}
	return map[string]any{
		"user_id":       userID,
		"stage":         stage,
		"offset":        offset,
		"limit":         limit,
		"total_jobs":    len(filtered),
		"returned_jobs": len(page),
		"jobs":          pageAny,
		"job_db_path":   jobDBPath(),
	}, nil
}

func ListRecentJobEvents(args map[string]any) (map[string]any, error) {
	userID := getString(args, "user_id")
	if userID == "" {
		return nil, fmt.Errorf("user_id is required")
	}
	limit := 50
	if parsed, has, err := getOptionalInt(args, "limit"); has {
		if err != nil {
			return nil, fmt.Errorf("limit must be an integer when provided")
		}
		if parsed < 1 {
			parsed = 1
		}
		if parsed > 200 {
			parsed = 200
		}
		limit = parsed
	}
	offset := 0
	if parsed, has, err := getOptionalInt(args, "offset"); has {
		if err != nil {
			return nil, fmt.Errorf("offset must be an integer when provided")
		}
		if parsed < 0 {
			parsed = 0
		}
		offset = parsed
	}

	pipeline := loadJobPipeline()
	entry := getPipelineEntry(pipeline, userID)
	if entry == nil {
		return map[string]any{
			"user_id":         userID,
			"offset":          offset,
			"limit":           limit,
			"total_events":    0,
			"returned_events": 0,
			"events":          []any{},
			"job_db_path":     jobDBPath(),
		}, nil
	}
	events := entry["events"].([]map[string]any)
	slices.SortFunc(events, func(a, b map[string]any) int {
		aCreated := getString(a, "created_at_utc")
		bCreated := getString(b, "created_at_utc")
		if aCreated == bCreated {
			ai, _ := intFromAny(a["id"])
			bi, _ := intFromAny(b["id"])
			return bi - ai
		}
		return strings.Compare(bCreated, aCreated)
	})
	enriched := make([]map[string]any, 0, len(events))
	for _, event := range events {
		jobID, _ := intFromAny(event["job_id"])
		job := getJobByID(entry, jobID)
		if job == nil {
			continue
		}
		eventID, _ := intFromAny(event["id"])
		enriched = append(enriched, map[string]any{
			"event_id":       eventID,
			"user_id":        userID,
			"job_id":         jobID,
			"result_id":      getString(job, "result_id"),
			"job_url":        getString(job, "job_url"),
			"title":          getString(job, "title"),
			"company":        getString(job, "company"),
			"from_stage":     event["from_stage"],
			"to_stage":       event["to_stage"],
			"reason":         event["reason"],
			"note":           event["note"],
			"created_at_utc": event["created_at_utc"],
		})
	}

	if offset > len(enriched) {
		offset = len(enriched)
	}
	end := offset + limit
	if end > len(enriched) {
		end = len(enriched)
	}
	page := enriched[offset:end]
	pageAny := make([]any, 0, len(page))
	for _, row := range page {
		pageAny = append(pageAny, row)
	}

	return map[string]any{
		"user_id":         userID,
		"offset":          offset,
		"limit":           limit,
		"total_events":    len(enriched),
		"returned_events": len(page),
		"events":          pageAny,
		"job_db_path":     jobDBPath(),
	}, nil
}

func GetJobPipelineSummary(args map[string]any) (map[string]any, error) {
	userID := getString(args, "user_id")
	if userID == "" {
		return nil, fmt.Errorf("user_id is required")
	}
	stageCounts := map[string]int{
		"new": 0, "saved": 0, "applied": 0, "interview": 0, "offer": 0, "rejected": 0, "ignored": 0,
	}
	recentEvents := []any{}
	totalTrackedJobs := 0
	pipeline := loadJobPipeline()
	entry := getPipelineEntry(pipeline, userID)
	if entry != nil {
		for _, app := range entry["applications"].([]map[string]any) {
			stage := getString(app, "stage")
			if _, ok := stageCounts[stage]; ok {
				stageCounts[stage]++
			}
		}
		totalTrackedJobs = len(entry["jobs"].([]map[string]any))
		eventsResult, err := ListRecentJobEvents(map[string]any{
			"user_id": userID,
			"limit":   10,
			"offset":  0,
		})
		if err == nil {
			recentEvents = listOrEmpty(eventsResult["events"])
		}
	}
	return map[string]any{
		"user_id":            userID,
		"stage_counts":       stageCounts,
		"applied_jobs_count": stageCounts["applied"],
		"total_tracked_jobs": totalTrackedJobs,
		"recent_events":      recentEvents,
		"job_db_path":        jobDBPath(),
	}, nil
}

func ClearSearchSession(args map[string]any) (map[string]any, error) {
	userID := getString(args, "user_id")
	if userID == "" {
		return nil, fmt.Errorf("user_id is required")
	}
	sessionID := getString(args, "session_id")
	clearAll := false
	if parsed, has, err := getOptionalBool(args, "clear_all_for_user"); has {
		if err != nil {
			return nil, fmt.Errorf("clear_all_for_user must be a boolean when provided")
		}
		clearAll = parsed
	}

	store := loadSearchSessions()
	sessions := mapOrNil(store["sessions"])
	if sessions == nil {
		sessions = map[string]any{}
	}
	deletedIDs := []string{}
	if clearAll {
		for sid, raw := range sessions {
			record := mapOrNil(raw)
			if record == nil {
				continue
			}
			query := mapOrNil(record["query"])
			if query != nil && getString(query, "user_id") == userID {
				delete(sessions, sid)
				deletedIDs = append(deletedIDs, sid)
			}
		}
	} else {
		if sessionID == "" {
			return nil, fmt.Errorf("session_id is required unless clear_all_for_user=true")
		}
		record := mapOrNil(sessions[sessionID])
		if record == nil {
			return map[string]any{
				"user_id":                 userID,
				"session_id":              sessionID,
				"deleted":                 false,
				"deleted_session_ids":     []any{},
				"remaining_user_sessions": 0,
				"path":                    searchSessionsPath(),
			}, nil
		}
		query := mapOrNil(record["query"])
		if query == nil || getString(query, "user_id") != userID {
			return nil, fmt.Errorf("session_id does not belong to this user_id")
		}
		delete(sessions, sessionID)
		deletedIDs = append(deletedIDs, sessionID)
	}
	store["sessions"] = sessions
	if err := saveSearchSessions(store); err != nil {
		return nil, err
	}

	remaining := 0
	for _, raw := range sessions {
		record := mapOrNil(raw)
		if record == nil {
			continue
		}
		query := mapOrNil(record["query"])
		if query != nil && getString(query, "user_id") == userID {
			remaining++
		}
	}
	deletedAny := make([]any, 0, len(deletedIDs))
	for _, id := range deletedIDs {
		deletedAny = append(deletedAny, id)
	}
	return map[string]any{
		"user_id":                 userID,
		"session_id":              sessionID,
		"clear_all_for_user":      clearAll,
		"deleted":                 len(deletedIDs) > 0,
		"deleted_session_ids":     deletedAny,
		"deleted_count":           len(deletedIDs),
		"remaining_user_sessions": remaining,
		"path":                    searchSessionsPath(),
	}, nil
}
