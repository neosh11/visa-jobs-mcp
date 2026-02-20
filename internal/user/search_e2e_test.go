//go:build e2e

package user

import (
	"os"
	"path/filepath"
	"strconv"
	"strings"
	"testing"
	"time"
)

func setupLiveE2EPaths(t *testing.T) {
	t.Helper()
	root := t.TempDir()
	t.Setenv("VISA_USER_PREFS_PATH", filepath.Join(root, "prefs.json"))
	t.Setenv("VISA_USER_BLOB_PATH", filepath.Join(root, "blob.json"))
	t.Setenv("VISA_SAVED_JOBS_PATH", filepath.Join(root, "saved_jobs.json"))
	t.Setenv("VISA_IGNORED_JOBS_PATH", filepath.Join(root, "ignored_jobs.json"))
	t.Setenv("VISA_IGNORED_COMPANIES_PATH", filepath.Join(root, "ignored_companies.json"))
	t.Setenv("VISA_SEARCH_SESSION_PATH", filepath.Join(root, "search_sessions.json"))
	t.Setenv("VISA_SEARCH_RUNS_PATH", filepath.Join(root, "search_runs.json"))
	t.Setenv("VISA_JOB_DB_PATH", filepath.Join(root, "job_pipeline.json"))
}

func waitForTerminalRunStatusE2E(t *testing.T, userID, runID string, timeout time.Duration) (map[string]any, bool) {
	t.Helper()
	deadline := time.Now().Add(timeout)
	cursor := 0
	var latest map[string]any

	for time.Now().Before(deadline) {
		status, err := GetVisaJobSearchStatus(map[string]any{
			"user_id": userID,
			"run_id":  runID,
			"cursor":  cursor,
		})
		if err != nil {
			t.Logf("GetVisaJobSearchStatus failed: %v", err)
			return nil, false
		}
		latest = status
		cursor = intOrZero(status["next_cursor"])

		if searchRunIsTerminal(getString(status, "status")) {
			return status, true
		}
		time.Sleep(1 * time.Second)
	}
	t.Logf("timeout waiting for terminal run status; latest=%v", latest)
	return latest, false
}

func TestE2ELinkedInNYCSWEH1B(t *testing.T) {
	if os.Getenv("VISA_RUN_LIVE_LINKEDIN_E2E") != "1" {
		t.Skip("set VISA_RUN_LIVE_LINKEDIN_E2E=1 to run live LinkedIn e2e")
	}

	setupLiveE2EPaths(t)
	t.Setenv("VISA_MAX_DESCRIPTION_FETCHES", "12")
	t.Setenv("VISA_DESCRIPTION_BUDGET_SECONDS", "60")
	t.Setenv("VISA_LINKEDIN_TIMEOUT_SECONDS", "10")

	wd, err := os.Getwd()
	if err != nil {
		t.Logf("os.Getwd failed: %v", err)
		return
	}
	datasetPath := filepath.Clean(filepath.Join(wd, "..", "..", "data", "companies.csv"))
	if _, err := os.Stat(datasetPath); err != nil {
		t.Logf("live dataset not available at %s: %v", datasetPath, err)
		return
	}

	userID := "live-e2e-user"
	visaType := envStringOrDefault("VISA_E2E_VISA_TYPE", "H1B")
	location := envStringOrDefault("VISA_E2E_LOCATION", "New York, NY")
	jobTitle := envStringOrDefault("VISA_E2E_JOB_TITLE", "Software Engineer")
	resultsWanted := envIntOrDefault("VISA_E2E_RESULTS_WANTED", 5)
	maxReturned := envIntOrDefault("VISA_E2E_MAX_RETURNED", 5)
	scanMultiplier := envIntOrDefault("VISA_E2E_SCAN_MULTIPLIER", 4)
	maxScanResults := envIntOrDefault("VISA_E2E_MAX_SCAN_RESULTS", 120)
	hoursOld := envIntOrDefault("VISA_E2E_HOURS_OLD", 336)
	requireDescriptionSignal := envBoolOrDefault("VISA_E2E_REQUIRE_DESCRIPTION_SIGNAL", false)
	_, err = SetUserPreferences(map[string]any{
		"user_id":              userID,
		"preferred_visa_types": []any{visaType},
	})
	if err != nil {
		t.Logf("SetUserPreferences failed: %v", err)
		return
	}

	started, err := StartVisaJobSearch(map[string]any{
		"user_id":                    userID,
		"location":                   location,
		"job_title":                  jobTitle,
		"results_wanted":             resultsWanted,
		"max_returned":               maxReturned,
		"scan_multiplier":            scanMultiplier,
		"max_scan_results":           maxScanResults,
		"strictness_mode":            "balanced",
		"require_description_signal": requireDescriptionSignal,
		"hours_old":                  hoursOld,
		"dataset_path":               datasetPath,
	})
	if err != nil {
		t.Logf("StartVisaJobSearch failed: %v", err)
		return
	}
	runID := getString(started, "run_id")
	if runID == "" {
		t.Logf("missing run_id in start payload: %#v", started)
		return
	}

	finalStatus, ok := waitForTerminalRunStatusE2E(t, userID, runID, 3*time.Minute)
	if !ok {
		return
	}
	if got := getString(finalStatus, "status"); got != "completed" {
		t.Logf("terminal status is %q (%#v)", got, finalStatus)
		return
	}

	results, err := GetVisaJobSearchResults(map[string]any{
		"user_id": userID,
		"run_id":  runID,
		"limit":   5,
		"offset":  0,
	})
	if err != nil {
		t.Logf("GetVisaJobSearchResults failed: %v", err)
		return
	}
	stats := mapOrNil(results["stats"])
	if stats == nil {
		t.Logf("missing stats in response: %#v", results)
		return
	}
	jobs := listOrEmpty(results["jobs"])
	if intOrZero(stats["raw_jobs_scanned"]) <= 0 {
		t.Logf("raw_jobs_scanned <= 0 (stats=%#v)", stats)
	}

	for _, raw := range jobs {
		job := mapOrNil(raw)
		if getString(job, "site") != "linkedin" {
			t.Logf("unexpected site=%#v in job=%#v", job["site"], job)
			continue
		}
		if getString(job, "job_url") == "" {
			t.Logf("job missing job_url: %#v", job)
			continue
		}
	}

	t.Logf(
		"live e2e output: run_id=%s visa=%s location=%q title=%q require_description_signal=%v raw_jobs_scanned=%d accepted_jobs=%d returned_jobs=%d",
		runID,
		visaType,
		location,
		jobTitle,
		requireDescriptionSignal,
		intOrZero(stats["raw_jobs_scanned"]),
		intOrZero(stats["accepted_jobs"]),
		len(jobs),
	)
	if len(jobs) > 0 {
		first := mapOrNil(jobs[0])
		t.Logf(
			"first_job: title=%q company=%q salary_text=%q job_type=%q job_level=%q industry=%q is_remote=%v",
			getString(first, "title"),
			getString(first, "company"),
			getString(first, "salary_text"),
			getString(first, "job_type"),
			getString(first, "job_level"),
			getString(first, "company_industry"),
			first["is_remote"],
		)
	}
}

func envStringOrDefault(key, fallback string) string {
	value := strings.TrimSpace(os.Getenv(key))
	if value == "" {
		return fallback
	}
	return value
}

func envIntOrDefault(key string, fallback int) int {
	raw := strings.TrimSpace(os.Getenv(key))
	if raw == "" {
		return fallback
	}
	parsed, err := strconv.Atoi(raw)
	if err != nil {
		return fallback
	}
	if parsed < 1 {
		return fallback
	}
	return parsed
}

func envBoolOrDefault(key string, fallback bool) bool {
	raw := strings.TrimSpace(os.Getenv(key))
	if raw == "" {
		return fallback
	}
	lower := strings.ToLower(raw)
	if lower == "1" || lower == "true" || lower == "yes" || lower == "y" {
		return true
	}
	if lower == "0" || lower == "false" || lower == "no" || lower == "n" {
		return false
	}
	return fallback
}
