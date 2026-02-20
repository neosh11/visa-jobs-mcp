package user

import (
	"slices"
	"strings"
)

func loadJobPipeline() map[string]any {
	return loadJSONMap(jobDBPath(), map[string]any{"users": map[string]any{}})
}

func saveJobPipeline(data map[string]any) error {
	return saveJSONMap(jobDBPath(), data)
}

func normalizePipelineJob(raw any, userID string) (map[string]any, bool) {
	item := mapOrNil(raw)
	if item == nil {
		return nil, false
	}
	id, ok := intFromAny(item["id"])
	if !ok || id < 1 {
		return nil, false
	}
	return map[string]any{
		"id":             id,
		"user_id":        userID,
		"result_id":      getString(item, "result_id"),
		"job_url":        getString(item, "job_url"),
		"title":          getString(item, "title"),
		"company":        getString(item, "company"),
		"location":       getString(item, "location"),
		"site":           getString(item, "site"),
		"created_at_utc": getString(item, "created_at_utc"),
		"updated_at_utc": getString(item, "updated_at_utc"),
	}, true
}

func normalizePipelineApplication(raw any, userID string) (map[string]any, bool) {
	item := mapOrNil(raw)
	if item == nil {
		return nil, false
	}
	id, ok := intFromAny(item["id"])
	if !ok || id < 1 {
		return nil, false
	}
	jobID, ok := intFromAny(item["job_id"])
	if !ok || jobID < 1 {
		return nil, false
	}
	stage := getString(item, "stage")
	if stage == "" {
		stage = "new"
	}
	stage, err := validateJobStage(stage)
	if err != nil {
		stage = "new"
	}
	return map[string]any{
		"id":                id,
		"user_id":           userID,
		"job_id":            jobID,
		"stage":             stage,
		"applied_at_utc":    getString(item, "applied_at_utc"),
		"source_session_id": getString(item, "source_session_id"),
		"note":              getString(item, "note"),
		"updated_at_utc":    getString(item, "updated_at_utc"),
	}, true
}

func normalizePipelineEvent(raw any, userID string) (map[string]any, bool) {
	item := mapOrNil(raw)
	if item == nil {
		return nil, false
	}
	id, ok := intFromAny(item["id"])
	if !ok || id < 1 {
		return nil, false
	}
	jobID, ok := intFromAny(item["job_id"])
	if !ok || jobID < 1 {
		return nil, false
	}
	return map[string]any{
		"id":             id,
		"user_id":        userID,
		"job_id":         jobID,
		"from_stage":     getString(item, "from_stage"),
		"to_stage":       getString(item, "to_stage"),
		"reason":         getString(item, "reason"),
		"note":           getString(item, "note"),
		"created_at_utc": getString(item, "created_at_utc"),
	}, true
}

func normalizePipelineJobs(list []any, userID string) []map[string]any {
	out := make([]map[string]any, 0, len(list))
	for _, raw := range list {
		row, ok := normalizePipelineJob(raw, userID)
		if ok {
			out = append(out, row)
		}
	}
	slices.SortFunc(out, func(a, b map[string]any) int {
		ai, _ := intFromAny(a["id"])
		bi, _ := intFromAny(b["id"])
		return ai - bi
	})
	return out
}

func normalizePipelineApplications(list []any, userID string) []map[string]any {
	out := make([]map[string]any, 0, len(list))
	for _, raw := range list {
		row, ok := normalizePipelineApplication(raw, userID)
		if ok {
			out = append(out, row)
		}
	}
	slices.SortFunc(out, func(a, b map[string]any) int {
		ai, _ := intFromAny(a["id"])
		bi, _ := intFromAny(b["id"])
		return ai - bi
	})
	return out
}

func normalizePipelineEvents(list []any, userID string) []map[string]any {
	out := make([]map[string]any, 0, len(list))
	for _, raw := range list {
		row, ok := normalizePipelineEvent(raw, userID)
		if ok {
			out = append(out, row)
		}
	}
	slices.SortFunc(out, func(a, b map[string]any) int {
		ai, _ := intFromAny(a["id"])
		bi, _ := intFromAny(b["id"])
		return ai - bi
	})
	return out
}

func ensurePipelineEntry(data map[string]any, userID string) map[string]any {
	users := ensureUsersMap(data)
	entry := mapOrNil(users[userID])
	if entry == nil {
		entry = map[string]any{}
		users[userID] = entry
	}

	jobs := normalizePipelineJobs(listOrEmpty(entry["jobs"]), userID)
	apps := normalizePipelineApplications(listOrEmpty(entry["applications"]), userID)
	events := normalizePipelineEvents(listOrEmpty(entry["events"]), userID)
	entry["jobs"] = jobs
	entry["applications"] = apps
	entry["events"] = events

	maxJobID := 0
	for _, row := range jobs {
		if id, ok := intFromAny(row["id"]); ok && id > maxJobID {
			maxJobID = id
		}
	}
	maxAppID := 0
	for _, row := range apps {
		if id, ok := intFromAny(row["id"]); ok && id > maxAppID {
			maxAppID = id
		}
	}
	maxEventID := 0
	for _, row := range events {
		if id, ok := intFromAny(row["id"]); ok && id > maxEventID {
			maxEventID = id
		}
	}

	nextJobID, ok := intFromAny(entry["next_job_id"])
	if !ok || nextJobID < 1 {
		nextJobID = 1
	}
	if nextJobID <= maxJobID {
		nextJobID = maxJobID + 1
	}
	entry["next_job_id"] = nextJobID

	nextAppID, ok := intFromAny(entry["next_application_id"])
	if !ok || nextAppID < 1 {
		nextAppID = 1
	}
	if nextAppID <= maxAppID {
		nextAppID = maxAppID + 1
	}
	entry["next_application_id"] = nextAppID

	nextEventID, ok := intFromAny(entry["next_event_id"])
	if !ok || nextEventID < 1 {
		nextEventID = 1
	}
	if nextEventID <= maxEventID {
		nextEventID = maxEventID + 1
	}
	entry["next_event_id"] = nextEventID
	return entry
}

func getPipelineEntry(data map[string]any, userID string) map[string]any {
	users := getUsersMap(data)
	entry := mapOrNil(users[userID])
	if entry == nil {
		return nil
	}
	entry["jobs"] = normalizePipelineJobs(listOrEmpty(entry["jobs"]), userID)
	entry["applications"] = normalizePipelineApplications(listOrEmpty(entry["applications"]), userID)
	entry["events"] = normalizePipelineEvents(listOrEmpty(entry["events"]), userID)
	return entry
}

func getJobByID(entry map[string]any, jobID int) map[string]any {
	for _, row := range entry["jobs"].([]map[string]any) {
		id, _ := intFromAny(row["id"])
		if id == jobID {
			return row
		}
	}
	return nil
}

func getJobByURL(entry map[string]any, jobURL string) map[string]any {
	clean := strings.ToLower(strings.TrimSpace(jobURL))
	for _, row := range entry["jobs"].([]map[string]any) {
		if strings.ToLower(getString(row, "job_url")) == clean {
			return row
		}
	}
	return nil
}
