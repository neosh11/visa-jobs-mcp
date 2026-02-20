package user

import (
	"fmt"
	"slices"
	"strings"
)

func SaveJobForLater(args map[string]any) (map[string]any, error) {
	userID := getString(args, "user_id")
	if userID == "" {
		return nil, fmt.Errorf("user_id is required")
	}
	resolved, err := resolveJobReference(args, userID)
	if err != nil {
		return nil, err
	}
	cleanURL := getString(resolved, "job_url")

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
	description := getString(args, "description")
	if description == "" {
		description = getString(resolved, "description")
	}
	descriptionExcerpt := getString(args, "description_excerpt")
	if descriptionExcerpt == "" {
		descriptionExcerpt = getString(resolved, "description_excerpt")
	}
	salaryText := getString(args, "salary_text")
	if salaryText == "" {
		salaryText = getString(resolved, "salary_text")
	}
	salaryCurrency := getString(args, "salary_currency")
	if salaryCurrency == "" {
		salaryCurrency = getString(resolved, "salary_currency")
	}
	salaryInterval := getString(args, "salary_interval")
	if salaryInterval == "" {
		salaryInterval = getString(resolved, "salary_interval")
	}
	salarySource := getString(args, "salary_source")
	if salarySource == "" {
		salarySource = getString(resolved, "salary_source")
	}
	jobType := getString(args, "job_type")
	if jobType == "" {
		jobType = getString(resolved, "job_type")
	}
	jobLevel := getString(args, "job_level")
	if jobLevel == "" {
		jobLevel = getString(resolved, "job_level")
	}
	companyIndustry := getString(args, "company_industry")
	if companyIndustry == "" {
		companyIndustry = getString(resolved, "company_industry")
	}
	jobFunction := getString(args, "job_function")
	if jobFunction == "" {
		jobFunction = getString(resolved, "job_function")
	}
	jobURLDirect := getString(args, "job_url_direct")
	if jobURLDirect == "" {
		jobURLDirect = getString(resolved, "job_url_direct")
	}
	salaryMin := args["salary_min_amount"]
	if salaryMin == nil {
		salaryMin = resolved["salary_min_amount"]
	}
	salaryMax := args["salary_max_amount"]
	if salaryMax == nil {
		salaryMax = resolved["salary_max_amount"]
	}
	isRemote := args["is_remote"]
	if isRemote == nil {
		isRemote = resolved["is_remote"]
	}
	note := getString(args, "note")
	sourceSessionID := getString(args, "source_session_id")
	if sourceSessionID == "" {
		sourceSessionID = getString(resolved, "source_session_id")
	}
	now := utcNowISO()

	store := loadSavedJobs()
	entry := ensureUserListEntry(store, userID, "jobs", normalizeSavedJob)
	jobs := entry["jobs"].([]map[string]any)
	action := "saved_new"
	var savedJob map[string]any
	for _, row := range jobs {
		if !strings.EqualFold(getString(row, "job_url"), cleanURL) {
			continue
		}
		if title != "" {
			row["title"] = title
		}
		if company != "" {
			row["company"] = company
		}
		if location != "" {
			row["location"] = location
		}
		if site != "" {
			row["site"] = site
		}
		if description != "" {
			row["description"] = description
		}
		if descriptionExcerpt != "" {
			row["description_excerpt"] = descriptionExcerpt
		}
		if salaryText != "" {
			row["salary_text"] = salaryText
		}
		if salaryCurrency != "" {
			row["salary_currency"] = salaryCurrency
		}
		if salaryInterval != "" {
			row["salary_interval"] = salaryInterval
		}
		if salarySource != "" {
			row["salary_source"] = salarySource
		}
		if salaryMin != nil {
			row["salary_min_amount"] = salaryMin
		}
		if salaryMax != nil {
			row["salary_max_amount"] = salaryMax
		}
		if jobType != "" {
			row["job_type"] = jobType
		}
		if jobLevel != "" {
			row["job_level"] = jobLevel
		}
		if companyIndustry != "" {
			row["company_industry"] = companyIndustry
		}
		if jobFunction != "" {
			row["job_function"] = jobFunction
		}
		if jobURLDirect != "" {
			row["job_url_direct"] = jobURLDirect
		}
		if isRemote != nil {
			row["is_remote"] = isRemote
		}
		if note != "" {
			row["note"] = note
		}
		if sourceSessionID != "" {
			row["source_session_id"] = sourceSessionID
		}
		row["updated_at_utc"] = now
		savedJob = row
		action = "updated_existing"
		break
	}
	if savedJob == nil {
		nextID, _ := intFromAny(entry["next_id"])
		savedJob = map[string]any{
			"id":                  nextID,
			"job_url":             cleanURL,
			"title":               title,
			"company":             company,
			"location":            location,
			"site":                site,
			"description":         description,
			"description_excerpt": descriptionExcerpt,
			"salary_text":         salaryText,
			"salary_currency":     salaryCurrency,
			"salary_interval":     salaryInterval,
			"salary_min_amount":   salaryMin,
			"salary_max_amount":   salaryMax,
			"salary_source":       salarySource,
			"job_type":            jobType,
			"job_level":           jobLevel,
			"company_industry":    companyIndustry,
			"job_function":        jobFunction,
			"job_url_direct":      jobURLDirect,
			"is_remote":           isRemote,
			"note":                note,
			"source_session_id":   sourceSessionID,
			"saved_at_utc":        now,
			"updated_at_utc":      now,
		}
		entry["jobs"] = append(jobs, savedJob)
		entry["next_id"] = nextID + 1
	}
	entry["updated_at_utc"] = now
	if err := saveSavedJobs(store); err != nil {
		return nil, err
	}

	pipeline := loadJobPipeline()
	pipelineEntry := ensurePipelineEntry(pipeline, userID)
	jobID, _, err := upsertJob(pipelineEntry, userID, resolved, getString(savedJob, "title"), getString(savedJob, "company"), getString(savedJob, "location"), getString(savedJob, "site"))
	if err != nil {
		return nil, err
	}
	application, _, err := setJobStage(
		pipelineEntry,
		userID,
		jobID,
		"saved",
		getString(savedJob, "note"),
		getString(savedJob, "source_session_id"),
		"",
		"save_job_for_later",
	)
	if err != nil {
		return nil, err
	}
	if err := saveJobPipeline(pipeline); err != nil {
		return nil, err
	}

	return map[string]any{
		"user_id":            userID,
		"action":             action,
		"saved_job":          savedJob,
		"resolved_result_id": getString(resolved, "result_id"),
		"total_saved_jobs":   len(entry["jobs"].([]map[string]any)),
		"job_management": map[string]any{
			"job_id":      jobID,
			"stage":       getString(application, "stage"),
			"job_db_path": jobDBPath(),
		},
		"path": savedJobsPath(),
	}, nil
}

func ListSavedJobs(args map[string]any) (map[string]any, error) {
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
	store := loadSavedJobs()
	entry := getUserListEntry(store, userID, "jobs", normalizeSavedJob)
	if entry == nil {
		return map[string]any{
			"user_id":          userID,
			"offset":           offset,
			"limit":            limit,
			"total_saved_jobs": 0,
			"returned_jobs":    0,
			"jobs":             []any{},
			"path":             savedJobsPath(),
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
		"user_id":          userID,
		"offset":           offset,
		"limit":            limit,
		"total_saved_jobs": len(jobs),
		"returned_jobs":    len(page),
		"jobs":             pageAny,
		"path":             savedJobsPath(),
	}, nil
}

func DeleteSavedJob(args map[string]any) (map[string]any, error) {
	userID := getString(args, "user_id")
	if userID == "" {
		return nil, fmt.Errorf("user_id is required")
	}
	targetID, hasID, err := getOptionalInt(args, "saved_job_id")
	if !hasID {
		return nil, fmt.Errorf("saved_job_id is required")
	}
	if err != nil {
		return nil, fmt.Errorf("saved_job_id must be an integer")
	}
	if targetID < 1 {
		return nil, fmt.Errorf("saved_job_id must be a positive integer")
	}

	store := loadSavedJobs()
	entry := getUserListEntry(store, userID, "jobs", normalizeSavedJob)
	if entry == nil {
		return map[string]any{
			"user_id":          userID,
			"saved_job_id":     targetID,
			"deleted":          false,
			"deleted_job":      nil,
			"total_saved_jobs": 0,
			"path":             savedJobsPath(),
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
			"user_id":          userID,
			"saved_job_id":     targetID,
			"deleted":          false,
			"deleted_job":      nil,
			"total_saved_jobs": len(jobs),
			"path":             savedJobsPath(),
		}, nil
	}
	entry["jobs"] = remaining
	entry["updated_at_utc"] = utcNowISO()
	if err := saveSavedJobs(store); err != nil {
		return nil, err
	}

	deletedURL := getString(deleted, "job_url")
	if deletedURL != "" {
		pipeline := loadJobPipeline()
		pipelineEntry := ensurePipelineEntry(pipeline, userID)
		if job := getJobByURL(pipelineEntry, deletedURL); job != nil {
			jobID, _ := intFromAny(job["id"])
			_, _, _ = setJobStage(pipelineEntry, userID, jobID, "new", "", "", "", "delete_saved_job")
			_ = saveJobPipeline(pipeline)
		}
	}

	return map[string]any{
		"user_id":          userID,
		"saved_job_id":     targetID,
		"deleted":          true,
		"deleted_job":      deleted,
		"total_saved_jobs": len(remaining),
		"path":             savedJobsPath(),
	}, nil
}
