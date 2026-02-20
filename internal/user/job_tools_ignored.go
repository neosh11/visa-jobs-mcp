package user

import (
	"fmt"
	"slices"
	"strings"
)

func IgnoreJob(args map[string]any) (map[string]any, error) {
	userID := getString(args, "user_id")
	if userID == "" {
		return nil, fmt.Errorf("user_id is required")
	}
	resolved, err := resolveJobReference(args, userID)
	if err != nil {
		return nil, err
	}
	cleanURL := getString(resolved, "job_url")
	reason := getString(args, "reason")
	source := getString(args, "source")
	if source == "" {
		source = getString(resolved, "source_session_id")
	}
	now := utcNowISO()

	store := loadIgnoredJobs()
	entry := ensureUserListEntry(store, userID, "jobs", normalizeIgnoredJob)
	jobs := entry["jobs"].([]map[string]any)
	action := "ignored_new"
	var ignored map[string]any
	for _, row := range jobs {
		if !strings.EqualFold(getString(row, "job_url"), cleanURL) {
			continue
		}
		if reason != "" {
			row["reason"] = reason
		}
		if source != "" {
			row["source"] = source
		}
		row["updated_at_utc"] = now
		ignored = row
		action = "updated_existing"
		break
	}
	if ignored == nil {
		nextID, _ := intFromAny(entry["next_id"])
		ignored = map[string]any{
			"id":             nextID,
			"job_url":        cleanURL,
			"reason":         reason,
			"source":         source,
			"ignored_at_utc": now,
			"updated_at_utc": now,
		}
		entry["jobs"] = append(jobs, ignored)
		entry["next_id"] = nextID + 1
	}
	entry["updated_at_utc"] = now
	if err := saveIgnoredJobs(store); err != nil {
		return nil, err
	}

	pipeline := loadJobPipeline()
	pipelineEntry := ensurePipelineEntry(pipeline, userID)
	jobID, _, err := upsertJob(pipelineEntry, userID, resolved, getString(args, "title"), getString(args, "company"), getString(args, "location"), getString(args, "site"))
	if err != nil {
		return nil, err
	}
	application, _, err := setJobStage(pipelineEntry, userID, jobID, "ignored", getString(ignored, "reason"), getString(ignored, "source"), "", "ignore_job")
	if err != nil {
		return nil, err
	}
	if err := saveJobPipeline(pipeline); err != nil {
		return nil, err
	}

	return map[string]any{
		"user_id":            userID,
		"action":             action,
		"ignored_job":        ignored,
		"resolved_result_id": getString(resolved, "result_id"),
		"total_ignored_jobs": len(entry["jobs"].([]map[string]any)),
		"job_management": map[string]any{
			"job_id":      jobID,
			"stage":       getString(application, "stage"),
			"job_db_path": jobDBPath(),
		},
		"path": ignoredJobsPath(),
	}, nil
}

func ListIgnoredJobs(args map[string]any) (map[string]any, error) {
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
	store := loadIgnoredJobs()
	entry := getUserListEntry(store, userID, "jobs", normalizeIgnoredJob)
	if entry == nil {
		return map[string]any{
			"user_id":            userID,
			"offset":             offset,
			"limit":              limit,
			"total_ignored_jobs": 0,
			"returned_jobs":      0,
			"jobs":               []any{},
			"path":               ignoredJobsPath(),
		}, nil
	}
	jobs := entry["jobs"].([]map[string]any)
	slices.SortFunc(jobs, func(a, b map[string]any) int {
		ai, _ := intFromAny(a["id"])
		bi, _ := intFromAny(b["id"])
		return bi - ai
	})
	if offset > len(jobs) {
		offset = len(jobs)
	}
	end := offset + limit
	if end > len(jobs) {
		end = len(jobs)
	}
	page := jobs[offset:end]
	pageAny := make([]any, 0, len(page))
	for _, row := range page {
		pageAny = append(pageAny, row)
	}
	return map[string]any{
		"user_id":            userID,
		"offset":             offset,
		"limit":              limit,
		"total_ignored_jobs": len(jobs),
		"returned_jobs":      len(page),
		"jobs":               pageAny,
		"path":               ignoredJobsPath(),
	}, nil
}

func UnignoreJob(args map[string]any) (map[string]any, error) {
	userID := getString(args, "user_id")
	if userID == "" {
		return nil, fmt.Errorf("user_id is required")
	}
	targetID, hasID, err := getOptionalInt(args, "ignored_job_id")
	if !hasID {
		return nil, fmt.Errorf("ignored_job_id is required")
	}
	if err != nil {
		return nil, fmt.Errorf("ignored_job_id must be an integer")
	}
	if targetID < 1 {
		return nil, fmt.Errorf("ignored_job_id must be a positive integer")
	}
	store := loadIgnoredJobs()
	entry := getUserListEntry(store, userID, "jobs", normalizeIgnoredJob)
	if entry == nil {
		return map[string]any{
			"user_id":            userID,
			"ignored_job_id":     targetID,
			"deleted":            false,
			"deleted_job":        nil,
			"total_ignored_jobs": 0,
			"path":               ignoredJobsPath(),
		}, nil
	}
	jobs := entry["jobs"].([]map[string]any)
	remaining := make([]map[string]any, 0, len(jobs))
	var deleted map[string]any
	for _, row := range jobs {
		id, _ := intFromAny(row["id"])
		if deleted == nil && id == targetID {
			deleted = row
			continue
		}
		remaining = append(remaining, row)
	}
	if deleted == nil {
		return map[string]any{
			"user_id":            userID,
			"ignored_job_id":     targetID,
			"deleted":            false,
			"deleted_job":        nil,
			"total_ignored_jobs": len(jobs),
			"path":               ignoredJobsPath(),
		}, nil
	}
	entry["jobs"] = remaining
	entry["updated_at_utc"] = utcNowISO()
	if err := saveIgnoredJobs(store); err != nil {
		return nil, err
	}

	deletedURL := getString(deleted, "job_url")
	if deletedURL != "" {
		pipeline := loadJobPipeline()
		pipelineEntry := ensurePipelineEntry(pipeline, userID)
		if job := getJobByURL(pipelineEntry, deletedURL); job != nil {
			jobID, _ := intFromAny(job["id"])
			_, _, _ = setJobStage(pipelineEntry, userID, jobID, "new", "", "", "", "unignore_job")
			_ = saveJobPipeline(pipeline)
		}
	}

	return map[string]any{
		"user_id":            userID,
		"ignored_job_id":     targetID,
		"deleted":            true,
		"deleted_job":        deleted,
		"total_ignored_jobs": len(remaining),
		"path":               ignoredJobsPath(),
	}, nil
}

func IgnoreCompany(args map[string]any) (map[string]any, error) {
	userID := getString(args, "user_id")
	if userID == "" {
		return nil, fmt.Errorf("user_id is required")
	}

	companyName := getString(args, "company_name")
	source := getString(args, "source")
	resolved := map[string]any{}
	if getString(args, "result_id") != "" || getString(args, "session_id") != "" {
		var err error
		resolved, err = resolveJobReference(args, userID)
		if err != nil {
			return nil, err
		}
		if companyName == "" {
			companyName = getString(resolved, "company")
		}
		if source == "" {
			source = getString(resolved, "source_session_id")
		}
	}
	if companyName == "" {
		return nil, fmt.Errorf("company_name is required (or provide result_id/session_id)")
	}
	normalizedCompany := normalizeCompanyName(companyName)
	if normalizedCompany == "" {
		return nil, fmt.Errorf("company_name could not be normalized; provide a valid company name")
	}
	reason := getString(args, "reason")
	now := utcNowISO()

	store := loadIgnoredCompanies()
	entry := ensureUserListEntry(store, userID, "companies", normalizeIgnoredCompany)
	companies := entry["companies"].([]map[string]any)
	action := "ignored_new"
	var ignored map[string]any
	for _, row := range companies {
		if getString(row, "normalized_company") != normalizedCompany {
			continue
		}
		row["company_name"] = companyName
		if reason != "" {
			row["reason"] = reason
		}
		if source != "" {
			row["source"] = source
		}
		row["updated_at_utc"] = now
		ignored = row
		action = "updated_existing"
		break
	}
	if ignored == nil {
		nextID, _ := intFromAny(entry["next_id"])
		ignored = map[string]any{
			"id":                 nextID,
			"company_name":       companyName,
			"normalized_company": normalizedCompany,
			"reason":             reason,
			"source":             source,
			"ignored_at_utc":     now,
			"updated_at_utc":     now,
		}
		entry["companies"] = append(companies, ignored)
		entry["next_id"] = nextID + 1
	}
	entry["updated_at_utc"] = now
	if err := saveIgnoredCompanies(store); err != nil {
		return nil, err
	}
	return map[string]any{
		"user_id":                 userID,
		"action":                  action,
		"ignored_company":         ignored,
		"resolved_result_id":      getString(resolved, "result_id"),
		"total_ignored_companies": len(entry["companies"].([]map[string]any)),
		"path":                    ignoredCompaniesPath(),
	}, nil
}

func ListIgnoredCompanies(args map[string]any) (map[string]any, error) {
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
	store := loadIgnoredCompanies()
	entry := getUserListEntry(store, userID, "companies", normalizeIgnoredCompany)
	if entry == nil {
		return map[string]any{
			"user_id":                 userID,
			"offset":                  offset,
			"limit":                   limit,
			"total_ignored_companies": 0,
			"returned_companies":      0,
			"companies":               []any{},
			"path":                    ignoredCompaniesPath(),
		}, nil
	}
	companies := entry["companies"].([]map[string]any)
	slices.SortFunc(companies, func(a, b map[string]any) int {
		ai, _ := intFromAny(a["id"])
		bi, _ := intFromAny(b["id"])
		return bi - ai
	})
	if offset > len(companies) {
		offset = len(companies)
	}
	end := offset + limit
	if end > len(companies) {
		end = len(companies)
	}
	page := companies[offset:end]
	pageAny := make([]any, 0, len(page))
	for _, row := range page {
		pageAny = append(pageAny, row)
	}
	return map[string]any{
		"user_id":                 userID,
		"offset":                  offset,
		"limit":                   limit,
		"total_ignored_companies": len(companies),
		"returned_companies":      len(page),
		"companies":               pageAny,
		"path":                    ignoredCompaniesPath(),
	}, nil
}

func UnignoreCompany(args map[string]any) (map[string]any, error) {
	userID := getString(args, "user_id")
	if userID == "" {
		return nil, fmt.Errorf("user_id is required")
	}
	targetID, hasID, err := getOptionalInt(args, "ignored_company_id")
	if !hasID {
		return nil, fmt.Errorf("ignored_company_id is required")
	}
	if err != nil {
		return nil, fmt.Errorf("ignored_company_id must be an integer")
	}
	if targetID < 1 {
		return nil, fmt.Errorf("ignored_company_id must be a positive integer")
	}
	store := loadIgnoredCompanies()
	entry := getUserListEntry(store, userID, "companies", normalizeIgnoredCompany)
	if entry == nil {
		return map[string]any{
			"user_id":                 userID,
			"ignored_company_id":      targetID,
			"deleted":                 false,
			"deleted_company":         nil,
			"total_ignored_companies": 0,
			"path":                    ignoredCompaniesPath(),
		}, nil
	}
	companies := entry["companies"].([]map[string]any)
	remaining := make([]map[string]any, 0, len(companies))
	var deleted map[string]any
	for _, row := range companies {
		id, _ := intFromAny(row["id"])
		if deleted == nil && id == targetID {
			deleted = row
			continue
		}
		remaining = append(remaining, row)
	}
	if deleted == nil {
		return map[string]any{
			"user_id":                 userID,
			"ignored_company_id":      targetID,
			"deleted":                 false,
			"deleted_company":         nil,
			"total_ignored_companies": len(companies),
			"path":                    ignoredCompaniesPath(),
		}, nil
	}
	entry["companies"] = remaining
	entry["updated_at_utc"] = utcNowISO()
	if err := saveIgnoredCompanies(store); err != nil {
		return nil, err
	}
	return map[string]any{
		"user_id":                 userID,
		"ignored_company_id":      targetID,
		"deleted":                 true,
		"deleted_company":         deleted,
		"total_ignored_companies": len(remaining),
		"path":                    ignoredCompaniesPath(),
	}, nil
}
