package user

import (
	"fmt"
	"strings"
)

func upsertJob(entry map[string]any, userID string, resolved map[string]any, title, company, location, site string) (int, map[string]any, error) {
	cleanURL := getString(resolved, "job_url")
	if cleanURL == "" {
		return 0, nil, fmt.Errorf("job_url is required")
	}
	now := utcNowISO()
	resultID := getString(resolved, "result_id")
	if existing := getJobByURL(entry, cleanURL); existing != nil {
		if strings.TrimSpace(title) != "" {
			existing["title"] = strings.TrimSpace(title)
		}
		if strings.TrimSpace(company) != "" {
			existing["company"] = strings.TrimSpace(company)
		}
		if strings.TrimSpace(location) != "" {
			existing["location"] = strings.TrimSpace(location)
		}
		if strings.TrimSpace(site) != "" {
			existing["site"] = strings.TrimSpace(site)
		}
		if strings.TrimSpace(resultID) != "" {
			existing["result_id"] = strings.TrimSpace(resultID)
		}
		existing["updated_at_utc"] = now
		id, _ := intFromAny(existing["id"])
		return id, existing, nil
	}

	nextID, _ := intFromAny(entry["next_job_id"])
	job := map[string]any{
		"id":             nextID,
		"user_id":        userID,
		"result_id":      strings.TrimSpace(resultID),
		"job_url":        cleanURL,
		"title":          strings.TrimSpace(title),
		"company":        strings.TrimSpace(company),
		"location":       strings.TrimSpace(location),
		"site":           strings.TrimSpace(site),
		"created_at_utc": now,
		"updated_at_utc": now,
	}
	entry["jobs"] = append(entry["jobs"].([]map[string]any), job)
	entry["next_job_id"] = nextID + 1
	return nextID, job, nil
}

func findApplicationIndex(entry map[string]any, jobID int) (int, map[string]any) {
	apps := entry["applications"].([]map[string]any)
	for idx, app := range apps {
		id, _ := intFromAny(app["job_id"])
		if id == jobID {
			return idx, app
		}
	}
	return -1, nil
}

func setJobStage(
	entry map[string]any,
	userID string,
	jobID int,
	stage string,
	note string,
	sourceSessionID string,
	appliedAtUTC string,
	reason string,
) (map[string]any, map[string]any, error) {
	cleanStage, err := validateJobStage(stage)
	if err != nil {
		return nil, nil, err
	}
	if jobID < 1 {
		return nil, nil, fmt.Errorf("job_id must be a positive integer")
	}

	appIndex, existing := findApplicationIndex(entry, jobID)
	var priorStage any = nil
	priorNote := ""
	priorAppliedAt := ""
	priorSource := ""
	if existing != nil {
		priorStage = getString(existing, "stage")
		priorNote = getString(existing, "note")
		priorAppliedAt = getString(existing, "applied_at_utc")
		priorSource = getString(existing, "source_session_id")
	}

	newNote := strings.TrimSpace(note)
	mergedNote := priorNote
	if newNote != "" {
		if mergedNote == "" {
			mergedNote = newNote
		} else {
			mergedNote = strings.TrimSpace(mergedNote + "\n" + newNote)
		}
	}

	finalAppliedAt := priorAppliedAt
	if cleanStage == "applied" {
		explicitApplied := strings.TrimSpace(appliedAtUTC)
		if explicitApplied != "" {
			finalAppliedAt = explicitApplied
		} else if finalAppliedAt == "" {
			finalAppliedAt = utcNowISO()
		}
	}
	finalSource := strings.TrimSpace(sourceSessionID)
	if finalSource == "" {
		finalSource = priorSource
	}

	now := utcNowISO()
	var application map[string]any
	if existing == nil {
		nextAppID, _ := intFromAny(entry["next_application_id"])
		application = map[string]any{
			"id":                nextAppID,
			"user_id":           userID,
			"job_id":            jobID,
			"stage":             cleanStage,
			"applied_at_utc":    finalAppliedAt,
			"source_session_id": finalSource,
			"note":              mergedNote,
			"updated_at_utc":    now,
		}
		entry["applications"] = append(entry["applications"].([]map[string]any), application)
		entry["next_application_id"] = nextAppID + 1
	} else {
		existing["stage"] = cleanStage
		existing["applied_at_utc"] = finalAppliedAt
		existing["source_session_id"] = finalSource
		existing["note"] = mergedNote
		existing["updated_at_utc"] = now
		entry["applications"].([]map[string]any)[appIndex] = existing
		application = existing
	}

	nextEventID, _ := intFromAny(entry["next_event_id"])
	event := map[string]any{
		"id":             nextEventID,
		"user_id":        userID,
		"job_id":         jobID,
		"from_stage":     priorStage,
		"to_stage":       cleanStage,
		"reason":         strings.TrimSpace(reason),
		"note":           newNote,
		"created_at_utc": now,
	}
	if getString(event, "reason") == "" {
		event["reason"] = "stage_update"
	}
	entry["events"] = append(entry["events"].([]map[string]any), event)
	entry["next_event_id"] = nextEventID + 1
	return application, event, nil
}

func appendJobNote(entry map[string]any, userID string, jobID int, note string) (map[string]any, map[string]any, error) {
	cleanNote := strings.TrimSpace(note)
	if cleanNote == "" {
		return nil, nil, fmt.Errorf("note is required")
	}
	appIndex, existing := findApplicationIndex(entry, jobID)
	currentStage := "new"
	existingNote := ""
	if existing == nil {
		_, _, err := setJobStage(entry, userID, jobID, "new", "", "", "", "initialize_application")
		if err != nil {
			return nil, nil, err
		}
		appIndex, existing = findApplicationIndex(entry, jobID)
	}
	if existing != nil {
		currentStage = getString(existing, "stage")
		existingNote = getString(existing, "note")
	}
	mergedNote := cleanNote
	if existingNote != "" {
		mergedNote = strings.TrimSpace(existingNote + "\n" + cleanNote)
	}
	now := utcNowISO()
	existing["note"] = mergedNote
	existing["updated_at_utc"] = now
	entry["applications"].([]map[string]any)[appIndex] = existing

	nextEventID, _ := intFromAny(entry["next_event_id"])
	event := map[string]any{
		"id":             nextEventID,
		"user_id":        userID,
		"job_id":         jobID,
		"from_stage":     currentStage,
		"to_stage":       currentStage,
		"reason":         "note_added",
		"note":           cleanNote,
		"created_at_utc": now,
	}
	entry["events"] = append(entry["events"].([]map[string]any), event)
	entry["next_event_id"] = nextEventID + 1
	return existing, event, nil
}

func jobSnapshot(entry map[string]any, userID string, jobID int) (map[string]any, error) {
	job := getJobByID(entry, jobID)
	if job == nil {
		return nil, fmt.Errorf("job record not found")
	}
	_, app := findApplicationIndex(entry, jobID)
	if app == nil {
		return map[string]any{
			"job_id":               jobID,
			"user_id":              userID,
			"result_id":            getString(job, "result_id"),
			"job_url":              getString(job, "job_url"),
			"title":                getString(job, "title"),
			"company":              getString(job, "company"),
			"location":             getString(job, "location"),
			"site":                 getString(job, "site"),
			"created_at_utc":       getString(job, "created_at_utc"),
			"updated_at_utc":       getString(job, "updated_at_utc"),
			"stage":                "new",
			"applied_at_utc":       "",
			"source_session_id":    "",
			"note":                 "",
			"stage_updated_at_utc": nil,
		}, nil
	}
	return map[string]any{
		"job_id":               jobID,
		"user_id":              userID,
		"result_id":            getString(job, "result_id"),
		"job_url":              getString(job, "job_url"),
		"title":                getString(job, "title"),
		"company":              getString(job, "company"),
		"location":             getString(job, "location"),
		"site":                 getString(job, "site"),
		"created_at_utc":       getString(job, "created_at_utc"),
		"updated_at_utc":       getString(job, "updated_at_utc"),
		"stage":                getString(app, "stage"),
		"applied_at_utc":       getString(app, "applied_at_utc"),
		"source_session_id":    getString(app, "source_session_id"),
		"note":                 getString(app, "note"),
		"stage_updated_at_utc": app["updated_at_utc"],
	}, nil
}

func resolveJobManagementTarget(entry map[string]any, args map[string]any, userID string) (int, map[string]any, error) {
	jobID, hasJobID, err := getOptionalInt(args, "job_id")
	if hasJobID {
		if err != nil {
			return 0, nil, fmt.Errorf("job_id must be an integer")
		}
		if jobID > 0 {
			existing := getJobByID(entry, jobID)
			if existing == nil {
				return 0, nil, fmt.Errorf("job_id=%d not found for user_id='%s'", jobID, userID)
			}
			return jobID, existing, nil
		}
	}

	resolved, err := resolveJobReference(args, userID)
	if err != nil {
		return 0, nil, err
	}
	title := getString(args, "title")
	if title == "" {
		title = getString(resolved, "title")
	}
	company := getString(args, "company")
	if company == "" {
		company = getString(resolved, "company")
	}
	location := getString(args, "location")
	if location == "" {
		location = getString(resolved, "location")
	}
	site := getString(args, "site")
	if site == "" {
		site = getString(resolved, "site")
	}
	id, job, err := upsertJob(entry, userID, resolved, title, company, location, site)
	if err != nil {
		return 0, nil, err
	}
	return id, job, nil
}
