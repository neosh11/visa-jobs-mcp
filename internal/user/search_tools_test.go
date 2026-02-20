package user

import (
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"
)

type fakeLinkedInClient struct {
	pages        map[int][]linkedInJob
	descriptions map[string]string
	pageDelay    time.Duration
	descCalls    int
}

func (f *fakeLinkedInClient) FetchSearchPage(query linkedInSearchQuery, _ func() bool) ([]linkedInJob, error) {
	if f.pageDelay > 0 {
		time.Sleep(f.pageDelay)
	}
	rows := f.pages[query.Start]
	out := make([]linkedInJob, 0, len(rows))
	out = append(out, rows...)
	return out, nil
}

func (f *fakeLinkedInClient) FetchJobDetails(jobURL, _, _ string, _ func() bool) (linkedInJobDetails, error) {
	f.descCalls++
	if text, ok := f.descriptions[jobURL]; ok {
		return linkedInJobDetails{
			Description: text,
			IsRemote:    boolPtr(detectLinkedInRemote("", "", text)),
		}, nil
	}
	return linkedInJobDetails{}, nil
}

func writeTestDataset(t *testing.T, path string) {
	t.Helper()
	body := strings.Join([]string{
		"company_name,h1b,h1b1_chile,h1b1_singapore,e3_australian,green_card,contact_1,contact_1_title,email_1,contact_1_phone",
		"Acme Inc,10,0,0,5,0,Alice Recruiter,Talent Partner,alice@acme.com,111-111-1111",
		"Beta LLC,0,0,0,0,0,,,,",
	}, "\n")
	if err := os.WriteFile(path, []byte(body), 0o644); err != nil {
		t.Fatalf("write dataset: %v", err)
	}
}

func waitForTerminalRunStatus(t *testing.T, userID, runID string, timeout time.Duration) map[string]any {
	t.Helper()
	deadline := time.Now().Add(timeout)
	var latest map[string]any
	for time.Now().Before(deadline) {
		status, err := GetVisaJobSearchStatus(map[string]any{
			"user_id": userID,
			"run_id":  runID,
			"cursor":  0,
		})
		if err != nil {
			t.Fatalf("GetVisaJobSearchStatus failed: %v", err)
		}
		latest = status
		if searchRunIsTerminal(getString(status, "status")) {
			return status
		}
		time.Sleep(20 * time.Millisecond)
	}
	t.Fatalf("timeout waiting for terminal run status; latest=%v", latest)
	return nil
}

func waitForTerminalRunStatusGeneric(t *testing.T, userID, runID string, timeout time.Duration) map[string]any {
	t.Helper()
	deadline := time.Now().Add(timeout)
	var latest map[string]any
	for time.Now().Before(deadline) {
		status, err := GetJobSearchStatus(map[string]any{
			"user_id": userID,
			"run_id":  runID,
			"cursor":  0,
		})
		if err != nil {
			t.Fatalf("GetJobSearchStatus failed: %v", err)
		}
		latest = status
		if searchRunIsTerminal(getString(status, "status")) {
			return status
		}
		time.Sleep(20 * time.Millisecond)
	}
	t.Fatalf("timeout waiting for terminal run status; latest=%v", latest)
	return nil
}

func TestStartSearchAndFetchResults(t *testing.T) {
	setupUserToolPaths(t)
	root := t.TempDir()
	datasetPath := filepath.Join(root, "companies.csv")
	writeTestDataset(t, datasetPath)

	if _, err := SetUserPreferences(map[string]any{
		"user_id":              "u1",
		"preferred_visa_types": []any{"E3"},
	}); err != nil {
		t.Fatalf("SetUserPreferences failed: %v", err)
	}

	originalFactory := linkedInClientFactory
	defer func() {
		linkedInClientFactory = originalFactory
	}()
	linkedInClientFactory = func() linkedInClient {
		return &fakeLinkedInClient{
			pages: map[int][]linkedInJob{
				0: {
					{
						JobURL:     "https://www.linkedin.com/jobs/view/1/",
						Title:      "Software Engineer",
						Company:    "Acme",
						Location:   "New York, NY",
						Site:       "linkedin",
						DatePosted: "2026-02-20",
					},
				},
			},
			descriptions: map[string]string{
				"https://www.linkedin.com/jobs/view/1/": "E-3 visa sponsorship available.",
			},
		}
	}

	started, err := StartVisaJobSearch(map[string]any{
		"user_id":                    "u1",
		"location":                   "New York, NY",
		"job_title":                  "Software Engineer",
		"dataset_path":               datasetPath,
		"results_wanted":             1,
		"max_returned":               1,
		"scan_multiplier":            1,
		"max_scan_results":           1,
		"strictness_mode":            "strict",
		"require_description_signal": false,
		"hours_old":                  72,
	})
	if err != nil {
		t.Fatalf("StartVisaJobSearch failed: %v", err)
	}
	runID := getString(started, "run_id")
	if runID == "" {
		t.Fatalf("missing run_id in start payload: %#v", started)
	}

	finalStatus := waitForTerminalRunStatus(t, "u1", runID, 3*time.Second)
	if got := getString(finalStatus, "status"); got != "completed" {
		t.Fatalf("expected completed status, got %q (%#v)", got, finalStatus)
	}

	results, err := GetVisaJobSearchResults(map[string]any{
		"user_id": "u1",
		"run_id":  runID,
	})
	if err != nil {
		t.Fatalf("GetVisaJobSearchResults failed: %v", err)
	}
	jobs := listOrEmpty(results["jobs"])
	if len(jobs) != 1 {
		t.Fatalf("expected 1 job, got %d (%#v)", len(jobs), results["jobs"])
	}
	first := mapOrNil(jobs[0])
	if first == nil {
		t.Fatalf("expected map job payload, got %#v", jobs[0])
	}
	resultID := getString(first, "result_id")
	if resultID == "" {
		t.Fatalf("missing result_id in job: %#v", first)
	}

	saveResult, err := SaveJobForLater(map[string]any{
		"user_id":   "u1",
		"result_id": resultID,
	})
	if err != nil {
		t.Fatalf("SaveJobForLater via result_id failed: %v", err)
	}
	if got := getString(saveResult, "action"); got != "saved_new" {
		t.Fatalf("expected action=saved_new, got %q", got)
	}
}

func TestCancelVisaJobSearch(t *testing.T) {
	setupUserToolPaths(t)
	root := t.TempDir()
	datasetPath := filepath.Join(root, "companies.csv")
	writeTestDataset(t, datasetPath)

	if _, err := SetUserPreferences(map[string]any{
		"user_id":              "u1",
		"preferred_visa_types": []any{"E3"},
	}); err != nil {
		t.Fatalf("SetUserPreferences failed: %v", err)
	}

	originalFactory := linkedInClientFactory
	defer func() {
		linkedInClientFactory = originalFactory
	}()
	linkedInClientFactory = func() linkedInClient {
		rows := make([]linkedInJob, 0, 80)
		for idx := 0; idx < 80; idx++ {
			rows = append(rows, linkedInJob{
				JobURL:   fmt.Sprintf("https://www.linkedin.com/jobs/view/%d/", idx+1),
				Title:    "Software Engineer",
				Company:  "Acme",
				Location: "New York, NY",
				Site:     "linkedin",
			})
		}
		return &fakeLinkedInClient{
			pages: map[int][]linkedInJob{
				0: rows,
			},
			pageDelay: 250 * time.Millisecond,
		}
	}

	started, err := StartVisaJobSearch(map[string]any{
		"user_id":          "u1",
		"location":         "New York, NY",
		"job_title":        "Software Engineer",
		"dataset_path":     datasetPath,
		"results_wanted":   20,
		"max_returned":     10,
		"scan_multiplier":  4,
		"max_scan_results": 400,
	})
	if err != nil {
		t.Fatalf("StartVisaJobSearch failed: %v", err)
	}
	runID := getString(started, "run_id")
	if runID == "" {
		t.Fatalf("missing run_id in start payload")
	}

	cancelled, err := CancelVisaJobSearch(map[string]any{
		"user_id": "u1",
		"run_id":  runID,
	})
	if err != nil {
		t.Fatalf("CancelVisaJobSearch failed: %v", err)
	}
	if ok := boolOrFalse(cancelled["cancel_requested"]); !ok {
		t.Fatalf("expected cancel_requested=true, got %#v", cancelled)
	}

	finalStatus := waitForTerminalRunStatus(t, "u1", runID, 5*time.Second)
	if got := getString(finalStatus, "status"); got != "cancelled" {
		t.Fatalf("expected cancelled status, got %q (%#v)", got, finalStatus)
	}
}

func TestDescriptionFetchBudgetCapsRuntimeWork(t *testing.T) {
	setupUserToolPaths(t)
	t.Setenv("VISA_MAX_DESCRIPTION_FETCHES", "7")
	root := t.TempDir()
	datasetPath := filepath.Join(root, "companies.csv")
	writeTestDataset(t, datasetPath)

	if _, err := SetUserPreferences(map[string]any{
		"user_id":              "u2",
		"preferred_visa_types": []any{"E3"},
	}); err != nil {
		t.Fatalf("SetUserPreferences failed: %v", err)
	}

	rows := make([]linkedInJob, 0, 20)
	for idx := 0; idx < 20; idx++ {
		rows = append(rows, linkedInJob{
			JobURL:   fmt.Sprintf("https://www.linkedin.com/jobs/view/desc-%d/", idx+1),
			Title:    "Software Engineer",
			Company:  "Unknown Co",
			Location: "New York, NY",
			Site:     "linkedin",
		})
	}

	originalFactory := linkedInClientFactory
	defer func() {
		linkedInClientFactory = originalFactory
	}()
	fake := &fakeLinkedInClient{
		pages: map[int][]linkedInJob{
			0: rows,
		},
		descriptions: map[string]string{},
	}
	linkedInClientFactory = func() linkedInClient { return fake }

	started, err := StartVisaJobSearch(map[string]any{
		"user_id":          "u2",
		"location":         "New York, NY",
		"job_title":        "Software Engineer",
		"dataset_path":     datasetPath,
		"results_wanted":   5,
		"max_returned":     5,
		"scan_multiplier":  4,
		"max_scan_results": 20,
		"strictness_mode":  "balanced",
	})
	if err != nil {
		t.Fatalf("StartVisaJobSearch failed: %v", err)
	}
	runID := getString(started, "run_id")
	if runID == "" {
		t.Fatalf("missing run_id in start payload")
	}

	finalStatus := waitForTerminalRunStatus(t, "u2", runID, 3*time.Second)
	if got := getString(finalStatus, "status"); got != "completed" {
		t.Fatalf("expected completed status, got %q (%#v)", got, finalStatus)
	}

	results, err := GetVisaJobSearchResults(map[string]any{
		"user_id": "u2",
		"run_id":  runID,
	})
	if err != nil {
		t.Fatalf("GetVisaJobSearchResults failed: %v", err)
	}
	stats := mapOrNil(results["stats"])
	if stats == nil {
		t.Fatalf("missing stats in response: %#v", results)
	}
	if got := intOrZero(stats["description_fetches"]); got != 7 {
		t.Fatalf("expected description_fetches=7, got %d (stats=%#v)", got, stats)
	}
	if got := intOrZero(stats["description_fetch_skipped"]); got == 0 {
		t.Fatalf("expected description_fetch_skipped > 0, got %d (stats=%#v)", got, stats)
	}
	if fake.descCalls != 7 {
		t.Fatalf("expected fake description calls=7, got %d", fake.descCalls)
	}
}

func TestStartSearchDefaultsResultsWantedToFive(t *testing.T) {
	setupUserToolPaths(t)
	root := t.TempDir()
	datasetPath := filepath.Join(root, "companies.csv")
	writeTestDataset(t, datasetPath)

	if _, err := SetUserPreferences(map[string]any{
		"user_id":              "u3",
		"preferred_visa_types": []any{"E3"},
	}); err != nil {
		t.Fatalf("SetUserPreferences failed: %v", err)
	}

	originalFactory := linkedInClientFactory
	defer func() {
		linkedInClientFactory = originalFactory
	}()
	linkedInClientFactory = func() linkedInClient {
		return &fakeLinkedInClient{
			pages: map[int][]linkedInJob{
				0: {},
			},
		}
	}

	started, err := StartVisaJobSearch(map[string]any{
		"user_id":      "u3",
		"location":     "New York, NY",
		"job_title":    "Software Engineer",
		"dataset_path": datasetPath,
	})
	if err != nil {
		t.Fatalf("StartVisaJobSearch failed: %v", err)
	}
	runID := getString(started, "run_id")
	run, err := loadRunForUser(runID, "u3")
	if err != nil {
		t.Fatalf("loadRunForUser failed: %v", err)
	}
	query := mapOrNil(run["query"])
	if got := intOrZero(query["results_wanted"]); got != 5 {
		t.Fatalf("expected default results_wanted=5, got %d", got)
	}
}

func TestStartJobSearchWithoutVisaPreferences(t *testing.T) {
	setupUserToolPaths(t)
	root := t.TempDir()
	datasetPath := filepath.Join(root, "companies.csv")
	writeTestDataset(t, datasetPath)

	originalFactory := linkedInClientFactory
	defer func() {
		linkedInClientFactory = originalFactory
	}()
	linkedInClientFactory = func() linkedInClient {
		return &fakeLinkedInClient{
			pages: map[int][]linkedInJob{
				0: {
					{
						JobURL:     "https://www.linkedin.com/jobs/view/nonvisa-1/",
						Title:      "Software Engineer",
						Company:    "Beta LLC",
						Location:   "Bengaluru, India",
						Site:       "linkedin",
						DatePosted: "2026-02-20",
					},
				},
			},
		}
	}

	started, err := StartJobSearch(map[string]any{
		"user_id":          "u-no-visa",
		"location":         "Bengaluru, India",
		"job_title":        "Software Engineer",
		"dataset_path":     datasetPath,
		"results_wanted":   1,
		"max_returned":     1,
		"scan_multiplier":  1,
		"max_scan_results": 1,
	})
	if err != nil {
		t.Fatalf("StartJobSearch failed: %v", err)
	}
	runID := getString(started, "run_id")
	if runID == "" {
		t.Fatalf("missing run_id in start payload")
	}

	finalStatus := waitForTerminalRunStatusGeneric(t, "u-no-visa", runID, 3*time.Second)
	if got := getString(finalStatus, "status"); got != "completed" {
		t.Fatalf("expected completed status, got %q (%#v)", got, finalStatus)
	}

	results, err := GetJobSearchResults(map[string]any{
		"user_id": "u-no-visa",
		"run_id":  runID,
	})
	if err != nil {
		t.Fatalf("GetJobSearchResults failed: %v", err)
	}
	jobs := listOrEmpty(results["jobs"])
	if len(jobs) != 1 {
		t.Fatalf("expected 1 job, got %d", len(jobs))
	}
	status := asMap(results["status"])
	if enabled, _ := status["visa_filtering"].(bool); enabled {
		t.Fatalf("expected visa_filtering=false, got %#v", status["visa_filtering"])
	}
	first := mapOrNil(jobs[0])
	if got := getString(first, "visa_match_strength"); got != "not_requested" {
		t.Fatalf("expected visa_match_strength=not_requested, got %q", got)
	}
}

func TestStartVisaJobSearchWithoutPreferencesIsNotBlocked(t *testing.T) {
	setupUserToolPaths(t)
	root := t.TempDir()
	datasetPath := filepath.Join(root, "companies.csv")
	writeTestDataset(t, datasetPath)

	originalFactory := linkedInClientFactory
	defer func() {
		linkedInClientFactory = originalFactory
	}()
	linkedInClientFactory = func() linkedInClient {
		return &fakeLinkedInClient{
			pages: map[int][]linkedInJob{
				0: {
					{
						JobURL:     "https://www.linkedin.com/jobs/view/nonvisa-2/",
						Title:      "Software Engineer",
						Company:    "Beta LLC",
						Location:   "Mumbai, India",
						Site:       "linkedin",
						DatePosted: "2026-02-20",
					},
				},
			},
		}
	}

	started, err := StartVisaJobSearch(map[string]any{
		"user_id":          "u-no-visa-2",
		"location":         "Mumbai, India",
		"job_title":        "Software Engineer",
		"dataset_path":     datasetPath,
		"results_wanted":   1,
		"max_returned":     1,
		"scan_multiplier":  1,
		"max_scan_results": 1,
	})
	if err != nil {
		t.Fatalf("StartVisaJobSearch should not require preferences: %v", err)
	}
	runID := getString(started, "run_id")
	if runID == "" {
		t.Fatalf("missing run_id in start payload")
	}
	waitForTerminalRunStatus(t, "u-no-visa-2", runID, 3*time.Second)
}
