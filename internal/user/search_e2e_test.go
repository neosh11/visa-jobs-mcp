//go:build e2e

package user

import (
	"os"
	"path/filepath"
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

func waitForTerminalRunStatusE2E(t *testing.T, userID, runID string, timeout time.Duration) map[string]any {
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
			t.Fatalf("GetVisaJobSearchStatus failed: %v", err)
		}
		latest = status
		cursor = intOrZero(status["next_cursor"])

		if searchRunIsTerminal(getString(status, "status")) {
			return status
		}
		time.Sleep(1 * time.Second)
	}
	t.Fatalf("timeout waiting for terminal run status; latest=%v", latest)
	return nil
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
		t.Fatalf("os.Getwd failed: %v", err)
	}
	datasetPath := filepath.Clean(filepath.Join(wd, "..", "..", "data", "companies.csv"))
	if _, err := os.Stat(datasetPath); err != nil {
		t.Fatalf("live dataset not available at %s: %v", datasetPath, err)
	}

	userID := "live-e2e-user"
	_, err = SetUserPreferences(map[string]any{
		"user_id":              userID,
		"preferred_visa_types": []any{"H1B"},
	})
	if err != nil {
		t.Fatalf("SetUserPreferences failed: %v", err)
	}

	started, err := StartVisaJobSearch(map[string]any{
		"user_id":                    userID,
		"location":                   "New York, NY",
		"job_title":                  "Software Engineer",
		"results_wanted":             5,
		"max_returned":               5,
		"scan_multiplier":            4,
		"max_scan_results":           120,
		"strictness_mode":            "balanced",
		"require_description_signal": false,
		"hours_old":                  336,
		"dataset_path":               datasetPath,
	})
	if err != nil {
		t.Fatalf("StartVisaJobSearch failed: %v", err)
	}
	runID := getString(started, "run_id")
	if runID == "" {
		t.Fatalf("missing run_id in start payload: %#v", started)
	}

	finalStatus := waitForTerminalRunStatusE2E(t, userID, runID, 3*time.Minute)
	if got := getString(finalStatus, "status"); got != "completed" {
		t.Fatalf("expected completed status, got %q (%#v)", got, finalStatus)
	}

	results, err := GetVisaJobSearchResults(map[string]any{
		"user_id": userID,
		"run_id":  runID,
		"limit":   5,
		"offset":  0,
	})
	if err != nil {
		t.Fatalf("GetVisaJobSearchResults failed: %v", err)
	}
	stats := mapOrNil(results["stats"])
	if stats == nil {
		t.Fatalf("missing stats in response: %#v", results)
	}
	if intOrZero(stats["raw_jobs_scanned"]) <= 0 {
		t.Fatalf("expected raw_jobs_scanned > 0, got %#v", stats["raw_jobs_scanned"])
	}

	jobs := listOrEmpty(results["jobs"])
	if len(jobs) == 0 {
		t.Fatalf("expected at least 1 returned job, got 0 (stats=%#v status=%#v)", stats, results["status"])
	}
	for _, raw := range jobs {
		job := mapOrNil(raw)
		if getString(job, "site") != "linkedin" {
			t.Fatalf("expected linkedin job site, got %#v", job["site"])
		}
		if getString(job, "job_url") == "" {
			t.Fatalf("expected non-empty job_url in %#v", job)
		}
	}

	t.Logf("live e2e passed: run_id=%s raw_jobs_scanned=%d returned_jobs=%d", runID, intOrZero(stats["raw_jobs_scanned"]), len(jobs))
}
