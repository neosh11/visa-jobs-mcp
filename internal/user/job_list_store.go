package user

import (
	"slices"
)

func loadSavedJobs() map[string]any {
	return loadJSONMap(savedJobsPath(), map[string]any{"users": map[string]any{}})
}

func saveSavedJobs(data map[string]any) error {
	return saveJSONMap(savedJobsPath(), data)
}

func loadIgnoredJobs() map[string]any {
	return loadJSONMap(ignoredJobsPath(), map[string]any{"users": map[string]any{}})
}

func saveIgnoredJobs(data map[string]any) error {
	return saveJSONMap(ignoredJobsPath(), data)
}

func loadIgnoredCompanies() map[string]any {
	return loadJSONMap(ignoredCompaniesPath(), map[string]any{"users": map[string]any{}})
}

func saveIgnoredCompanies(data map[string]any) error {
	return saveJSONMap(ignoredCompaniesPath(), data)
}

func normalizeSavedJob(raw any) (map[string]any, bool) {
	item := mapOrNil(raw)
	if item == nil {
		return nil, false
	}
	id, ok := intFromAny(item["id"])
	if !ok || id < 1 {
		return nil, false
	}
	salaryMin := any(nil)
	if value, ok := intFromAny(item["salary_min_amount"]); ok {
		salaryMin = value
	}
	salaryMax := any(nil)
	if value, ok := intFromAny(item["salary_max_amount"]); ok {
		salaryMax = value
	}
	isRemote := any(nil)
	if value, ok := boolFromAny(item["is_remote"]); ok {
		isRemote = value
	}
	return map[string]any{
		"id":                  id,
		"job_url":             getString(item, "job_url"),
		"title":               getString(item, "title"),
		"company":             getString(item, "company"),
		"location":            getString(item, "location"),
		"site":                getString(item, "site"),
		"description":         getString(item, "description"),
		"description_excerpt": getString(item, "description_excerpt"),
		"salary_text":         getString(item, "salary_text"),
		"salary_currency":     getString(item, "salary_currency"),
		"salary_interval":     getString(item, "salary_interval"),
		"salary_min_amount":   salaryMin,
		"salary_max_amount":   salaryMax,
		"salary_source":       getString(item, "salary_source"),
		"job_type":            getString(item, "job_type"),
		"job_level":           getString(item, "job_level"),
		"company_industry":    getString(item, "company_industry"),
		"job_function":        getString(item, "job_function"),
		"job_url_direct":      getString(item, "job_url_direct"),
		"is_remote":           isRemote,
		"note":                getString(item, "note"),
		"source_session_id":   getString(item, "source_session_id"),
		"saved_at_utc":        getString(item, "saved_at_utc"),
		"updated_at_utc":      getString(item, "updated_at_utc"),
	}, true
}

func normalizeIgnoredJob(raw any) (map[string]any, bool) {
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
		"job_url":        getString(item, "job_url"),
		"reason":         getString(item, "reason"),
		"source":         getString(item, "source"),
		"ignored_at_utc": getString(item, "ignored_at_utc"),
		"updated_at_utc": getString(item, "updated_at_utc"),
	}, true
}

func normalizeIgnoredCompany(raw any) (map[string]any, bool) {
	item := mapOrNil(raw)
	if item == nil {
		return nil, false
	}
	id, ok := intFromAny(item["id"])
	if !ok || id < 1 {
		return nil, false
	}
	companyName := getString(item, "company_name")
	normalizedCompany := getString(item, "normalized_company")
	if normalizedCompany == "" {
		normalizedCompany = normalizeCompanyName(companyName)
	}
	if normalizedCompany == "" {
		return nil, false
	}
	return map[string]any{
		"id":                 id,
		"company_name":       companyName,
		"normalized_company": normalizedCompany,
		"reason":             getString(item, "reason"),
		"source":             getString(item, "source"),
		"ignored_at_utc":     getString(item, "ignored_at_utc"),
		"updated_at_utc":     getString(item, "updated_at_utc"),
	}, true
}

func normalizeSorted(list []any, normalizer func(any) (map[string]any, bool)) []map[string]any {
	out := make([]map[string]any, 0, len(list))
	for _, raw := range list {
		normalized, ok := normalizer(raw)
		if ok {
			out = append(out, normalized)
		}
	}
	slices.SortFunc(out, func(a, b map[string]any) int {
		ai, _ := intFromAny(a["id"])
		bi, _ := intFromAny(b["id"])
		return ai - bi
	})
	return out
}

func ensureUserListEntry(
	data map[string]any,
	userID string,
	key string,
	normalizer func(any) (map[string]any, bool),
) map[string]any {
	users := ensureUsersMap(data)
	entry := mapOrNil(users[userID])
	if entry == nil {
		entry = map[string]any{}
		users[userID] = entry
	}

	list := normalizeSorted(listOrEmpty(entry[key]), normalizer)
	entry[key] = list
	maxID := 0
	for _, row := range list {
		if id, ok := intFromAny(row["id"]); ok && id > maxID {
			maxID = id
		}
	}
	nextID, ok := intFromAny(entry["next_id"])
	if !ok || nextID < 1 {
		nextID = 1
	}
	if nextID <= maxID {
		nextID = maxID + 1
	}
	entry["next_id"] = nextID
	return entry
}

func getUserListEntry(
	data map[string]any,
	userID string,
	key string,
	normalizer func(any) (map[string]any, bool),
) map[string]any {
	users := getUsersMap(data)
	entry := mapOrNil(users[userID])
	if entry == nil {
		return nil
	}
	entry[key] = normalizeSorted(listOrEmpty(entry[key]), normalizer)
	return entry
}
