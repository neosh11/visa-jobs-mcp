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
}

func (f *fakeLinkedInClient) FetchSearchPage(query linkedInSearchQuery) ([]linkedInJob, error) {
	if f.pageDelay > 0 {
		time.Sleep(f.pageDelay)
	}
	rows := f.pages[query.Start]
	out := make([]linkedInJob, 0, len(rows))
	out = append(out, rows...)
	return out, nil
}

func (f *fakeLinkedInClient) FetchJobDescription(jobURL string) (string, error) {
	if text, ok := f.descriptions[jobURL]; ok {
		return text, nil
	}
	return "", nil
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
