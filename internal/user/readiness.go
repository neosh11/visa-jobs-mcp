package user

import (
	"encoding/json"
	"os"
	"strings"
	"time"
)

const (
	defaultDatasetPath          = "data/companies.csv"
	defaultManifestPath         = "data/pipeline/last_run.json"
	defaultUserBlobPath         = "data/config/user_memory_blob.json"
	defaultSavedJobsPath        = "data/config/saved_jobs.json"
	defaultIgnoredJobsPath      = "data/config/ignored_jobs.json"
	defaultIgnoredCompaniesPath = "data/config/ignored_companies.json"
	defaultSearchSessionsPath   = "data/config/search_sessions.json"
	defaultSearchRunsPath       = "data/config/search_runs.json"
	defaultJobDBPath            = "data/app/visa_jobs.db"
)

func envOrDefault(name, fallback string) string {
	if value := os.Getenv(name); value != "" {
		return value
	}
	return fallback
}

func parseManifestTime(path string) time.Time {
	raw, err := os.ReadFile(path)
	if err != nil {
		return time.Time{}
	}
	var parsed map[string]any
	if err := json.Unmarshal(raw, &parsed); err != nil {
		return time.Time{}
	}
	text, ok := parsed["run_at_utc"].(string)
	if !ok || text == "" {
		return time.Time{}
	}
	t, err := time.Parse(time.RFC3339, text)
	if err != nil {
		return time.Time{}
	}
	return t.UTC()
}

func datasetFreshness(datasetPath, manifestPath string) map[string]any {
	now := time.Now().UTC()
	manifestTime := parseManifestTime(manifestPath)

	datasetExists := false
	var fileTime time.Time
	if info, err := os.Stat(datasetPath); err == nil {
		datasetExists = true
		fileTime = info.ModTime().UTC()
	}

	refTime := manifestTime
	source := "manifest"
	if refTime.IsZero() {
		refTime = fileTime
		source = "filesystem_mtime"
	}
	if refTime.IsZero() {
		source = "unknown"
	}

	var ageSeconds any = nil
	var daysSinceRefresh any = nil
	isStale := true
	if !refTime.IsZero() {
		seconds := now.Sub(refTime).Seconds()
		if seconds < 0 {
			seconds = 0
		}
		ageSeconds = seconds
		daysSinceRefresh = seconds / 86400.0
		isStale = (seconds / 86400.0) >= 30.0
	}

	lastUpdated := any(nil)
	if !refTime.IsZero() {
		lastUpdated = refTime.Format(time.RFC3339)
	}

	manifestRun := any(nil)
	if !manifestTime.IsZero() {
		manifestRun = manifestTime.Format(time.RFC3339)
	}

	return map[string]any{
		"dataset_exists":                  datasetExists,
		"dataset_path":                    datasetPath,
		"manifest_path":                   manifestPath,
		"manifest_run_at_utc":             manifestRun,
		"dataset_last_updated_at_utc":     lastUpdated,
		"days_since_refresh":              daysSinceRefresh,
		"age_seconds":                     ageSeconds,
		"stale_after_days":                30,
		"is_stale":                        isStale,
		"source":                          source,
		"manifest_output_matches_dataset": false,
	}
}

func GetUserReadiness(args map[string]any) (map[string]any, error) {
	uid := getString(args, "user_id")
	if uid == "" {
		return nil, errRequired("user_id")
	}

	datasetPath := datasetPathOrDefault(getString(args, "dataset_path"))
	manifestPath := getString(args, "manifest_path")
	if manifestPath == "" {
		manifestPath = envOrDefault("VISA_DOL_MANIFEST_PATH", defaultManifestPath)
	}

	prefs, err := loadPrefs()
	if err != nil {
		return nil, err
	}
	user := prefs[uid]
	if user == nil {
		user = map[string]any{}
	}

	preferred, _ := user["preferred_visa_types"].([]any)
	preferredVisaTypes := make([]string, 0, len(preferred))
	for _, item := range preferred {
		text := getString(map[string]any{"value": item}, "value")
		if text != "" {
			preferredVisaTypes = append(preferredVisaTypes, text)
		}
	}
	if len(preferredVisaTypes) == 0 {
		// keep compatibility with map unmarshalling into []string
		if typed, ok := user["preferred_visa_types"].([]string); ok {
			preferredVisaTypes = append(preferredVisaTypes, typed...)
		}
	}
	hasPreferences := len(preferredVisaTypes) > 0
	constraints := asMap(user["constraints"])
	memoryLinesCount := len(getUserList(userBlobPath(), uid, "lines"))
	savedJobsCount := len(getUserList(savedJobsPath(), uid, "jobs"))
	ignoredJobsCount := len(getUserList(ignoredJobsPath(), uid, "jobs"))
	ignoredCompaniesCount := len(getUserList(ignoredCompaniesPath(), uid, "companies"))

	activeSearchRunsCount := 0
	runs := mapOrNil(loadSearchRuns()["runs"])
	for _, runAny := range runs {
		run := mapOrNil(runAny)
		if run == nil {
			continue
		}
		query := mapOrNil(run["query"])
		if query == nil || getString(query, "user_id") != uid {
			continue
		}
		status := strings.ToLower(getString(run, "status"))
		if status == "pending" || status == "running" || status == "cancelling" {
			activeSearchRunsCount++
		}
	}

	datasetExists := false
	if _, err := os.Stat(datasetPath); err == nil {
		datasetExists = true
	}

	freshness := datasetFreshness(datasetPath, manifestPath)

	nextActions := []string{}
	if !hasPreferences {
		nextActions = append(nextActions, "Call set_user_preferences first (required before start_visa_job_search).")
	}
	if !datasetExists {
		nextActions = append(nextActions, "Dataset CSV missing; run pipeline script before searching.")
	}
	if stale, _ := freshness["is_stale"].(bool); stale && datasetExists {
		nextActions = append(nextActions, "Dataset may be stale; refresh data/companies.csv via pipeline.")
	}

	stageCounts := map[string]int{
		"new": 0, "saved": 0, "applied": 0, "interview": 0, "offer": 0, "rejected": 0, "ignored": 0,
	}
	pipeline := getPipelineEntry(loadJobPipeline(), uid)
	if pipeline != nil {
		for _, app := range pipeline["applications"].([]map[string]any) {
			stage := getString(app, "stage")
			if _, ok := stageCounts[stage]; ok {
				stageCounts[stage]++
			}
		}
	}

	return map[string]any{
		"user_id": uid,
		"readiness": map[string]any{
			"ready_for_search":         hasPreferences,
			"has_preferences":          hasPreferences,
			"preferred_visa_types":     preferredVisaTypes,
			"dataset_exists":           datasetExists,
			"constraints":              constraints,
			"memory_lines_count":       memoryLinesCount,
			"saved_jobs_count":         savedJobsCount,
			"ignored_jobs_count":       ignoredJobsCount,
			"ignored_companies_count":  ignoredCompaniesCount,
			"active_search_runs_count": activeSearchRunsCount,
			"job_stage_counts":         stageCounts,
			"applied_jobs_count":       0,
		},
		"dataset_freshness": freshness,
		"paths": map[string]any{
			"dataset_path":           datasetPath,
			"manifest_path":          manifestPath,
			"preferences_path":       prefsPath(),
			"memory_blob_path":       userBlobPath(),
			"saved_jobs_path":        savedJobsPath(),
			"ignored_jobs_path":      ignoredJobsPath(),
			"ignored_companies_path": ignoredCompaniesPath(),
			"search_runs_path":       searchRunsPath(),
			"job_db_path":            jobDBPath(),
		},
		"next_actions": nextActions,
	}, nil
}

func errRequired(name string) error {
	return &requiredFieldError{name: name}
}

type requiredFieldError struct {
	name string
}

func (e *requiredFieldError) Error() string {
	return e.name + " is required"
}
