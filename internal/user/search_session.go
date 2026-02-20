package user

import (
	"fmt"
	"strings"
)

func ignoredJobURLSet(userID string) map[string]struct{} {
	store := loadIgnoredJobs()
	entry := getUserListEntry(store, userID, "jobs", normalizeIgnoredJob)
	if entry == nil {
		return map[string]struct{}{}
	}
	out := map[string]struct{}{}
	for _, row := range entry["jobs"].([]map[string]any) {
		url := strings.ToLower(getString(row, "job_url"))
		if url != "" {
			out[url] = struct{}{}
		}
	}
	return out
}

func ignoredCompanySet(userID string) map[string]struct{} {
	store := loadIgnoredCompanies()
	entry := getUserListEntry(store, userID, "companies", normalizeIgnoredCompany)
	if entry == nil {
		return map[string]struct{}{}
	}
	out := map[string]struct{}{}
	for _, row := range entry["companies"].([]map[string]any) {
		name := getString(row, "normalized_company")
		if name != "" {
			out[name] = struct{}{}
		}
	}
	return out
}

func attachResultIDs(sessionID string, jobs []map[string]any) []map[string]any {
	out := make([]map[string]any, 0, len(jobs))
	for idx, item := range jobs {
		job := cloneMap(item)
		resultID := getString(job, "result_id")
		if resultID == "" {
			resultID = fmt.Sprintf("%s:%d", sessionID, idx+1)
		}
		job["result_id"] = resultID
		out = append(out, job)
	}
	return out
}

func buildResultIndex(jobs []map[string]any) map[string]any {
	index := map[string]any{}
	for _, job := range jobs {
		resultID := getString(job, "result_id")
		if resultID == "" {
			continue
		}
		index[resultID] = map[string]any{
			"result_id":                resultID,
			"job_url":                  getString(job, "job_url"),
			"title":                    getString(job, "title"),
			"company":                  getString(job, "company"),
			"location":                 getString(job, "location"),
			"site":                     getString(job, "site"),
			"employer_contacts":        listOrEmpty(job["employer_contacts"]),
			"visa_counts":              asMap(job["visa_counts"]),
			"visas_sponsored":          listOrEmpty(job["visas_sponsored"]),
			"visa_match_strength":      getString(job, "visa_match_strength"),
			"eligibility_reasons":      listOrEmpty(job["eligibility_reasons"]),
			"confidence_score":         job["confidence_score"],
			"confidence_model_version": job["confidence_model_version"],
		}
	}
	return index
}

func saveSearchSessionRecord(
	query searchQuery,
	desiredVisaTypes []string,
	acceptedJobs []map[string]any,
	scanExhausted bool,
	rawScanTarget int,
) (map[string]any, error) {
	sessionID := newRunID()
	now := utcNowISO()
	expiresAt := futureISO(searchSessionTTLSeconds())
	accepted := attachResultIDs(sessionID, acceptedJobs)
	index := buildResultIndex(accepted)

	record := map[string]any{
		"created_at_utc": now,
		"updated_at_utc": now,
		"expires_at_utc": expiresAt,
		"query": map[string]any{
			"user_id":                    query.UserID,
			"location":                   query.Location,
			"job_title":                  query.JobTitle,
			"hours_old":                  query.HoursOld,
			"dataset_path":               query.DatasetPath,
			"site":                       query.Site,
			"results_wanted":             query.ResultsWanted,
			"max_returned":               query.MaxReturned,
			"offset":                     query.Offset,
			"require_description_signal": query.RequireDescriptionSignal,
			"strictness_mode":            query.StrictnessMode,
			"preferred_visa_types":       desiredVisaTypes,
		},
		"accepted_jobs": func() []any {
			out := []any{}
			for _, job := range accepted {
				out = append(out, job)
			}
			return out
		}(),
		"result_id_index":     index,
		"accepted_jobs_total": len(accepted),
		"latest_scan_target":  rawScanTarget,
		"scan_exhausted":      scanExhausted,
	}

	err := withSearchSessionStore(true, func(store map[string]any) error {
		sessions := mapOrNil(store["sessions"])
		if sessions == nil {
			sessions = map[string]any{}
		}
		sessions[sessionID] = record
		store["sessions"] = sessions
		enforceUserSessionLimitLocked(store, query.UserID)
		return nil
	})
	if err != nil {
		return nil, err
	}
	return map[string]any{
		"session_id":      sessionID,
		"expires_at_utc":  expiresAt,
		"accepted_jobs":   accepted,
		"result_id_index": index,
	}, nil
}

func loadSearchSessionForUser(sessionID, userID string) (map[string]any, error) {
	var record map[string]any
	err := withSearchSessionStore(false, func(store map[string]any) error {
		sessions := mapOrNil(store["sessions"])
		if sessions == nil {
			return fmt.Errorf("unknown session_id '%s'", sessionID)
		}
		session := mapOrNil(sessions[sessionID])
		if session == nil {
			return fmt.Errorf("unknown session_id '%s'", sessionID)
		}
		query := mapOrNil(session["query"])
		if query == nil || getString(query, "user_id") != userID {
			return fmt.Errorf("session_id does not belong to this user_id")
		}
		record = cloneMap(session)
		return nil
	})
	if err != nil {
		return nil, err
	}
	return record, nil
}

func sliceAcceptedJobs(
	accepted []map[string]any,
	offset int,
	maxReturned int,
	rawScanTarget int,
	maxScanResults int,
	scanExhausted bool,
) (page []map[string]any, pagination map[string]any) {
	safeOffset := offset
	if safeOffset < 0 {
		safeOffset = 0
	}
	pageSize := maxReturned
	if pageSize < 1 {
		pageSize = defaultSearchMaxReturned
	}
	total := len(accepted)
	if safeOffset > total {
		safeOffset = total
	}
	end := safeOffset + pageSize
	if end > total {
		end = total
	}
	page = accepted[safeOffset:end]
	nextOffset := any(nil)
	hasNext := false
	if end < total {
		nextOffset = end
		hasNext = true
	}
	pagination = map[string]any{
		"offset":                        safeOffset,
		"page_size":                     pageSize,
		"returned_jobs":                 len(page),
		"next_offset":                   nextOffset,
		"has_next_page":                 hasNext,
		"accepted_jobs_total":           total,
		"accepted_jobs_needed_for_page": safeOffset + pageSize,
		"requested_scan_target":         rawScanTarget,
		"max_scan_results":              maxScanResults,
		"scan_exhausted":                scanExhausted,
	}
	return page, pagination
}

func rebuildResponsePage(base map[string]any, page []map[string]any, pagination map[string]any) map[string]any {
	out := cloneMap(base)
	jobs := []any{}
	for _, item := range page {
		jobs = append(jobs, item)
	}
	out["jobs"] = jobs
	out["pagination"] = pagination
	stats := asMap(out["stats"])
	stats["returned_jobs"] = len(page)
	out["stats"] = stats
	return out
}
