package user

import (
	"path/filepath"
	"testing"
)

func TestSaveListDeleteSavedJobs(t *testing.T) {
	setupUserToolPaths(t)

	first, err := SaveJobForLater(map[string]any{
		"user_id": "u1",
		"job_url": "https://example.com/jobs/1",
		"title":   "Software Engineer",
		"company": "Acme",
		"site":    "linkedin",
	})
	if err != nil {
		t.Fatalf("SaveJobForLater first call failed: %v", err)
	}
	if got := getString(first, "action"); got != "saved_new" {
		t.Fatalf("expected action=saved_new, got %q", got)
	}

	second, err := SaveJobForLater(map[string]any{
		"user_id": "u1",
		"job_url": "https://example.com/jobs/1",
		"note":    "follow up this week",
	})
	if err != nil {
		t.Fatalf("SaveJobForLater second call failed: %v", err)
	}
	if got := getString(second, "action"); got != "updated_existing" {
		t.Fatalf("expected action=updated_existing, got %q", got)
	}
	if got, _ := second["total_saved_jobs"].(int); got != 1 {
		t.Fatalf("expected total_saved_jobs=1, got %#v", second["total_saved_jobs"])
	}

	listed, err := ListSavedJobs(map[string]any{"user_id": "u1"})
	if err != nil {
		t.Fatalf("ListSavedJobs failed: %v", err)
	}
	if got, _ := listed["total_saved_jobs"].(int); got != 1 {
		t.Fatalf("expected total_saved_jobs=1, got %#v", listed["total_saved_jobs"])
	}

	deleted, err := DeleteSavedJob(map[string]any{
		"user_id":      "u1",
		"saved_job_id": 1,
	})
	if err != nil {
		t.Fatalf("DeleteSavedJob failed: %v", err)
	}
	if ok, _ := deleted["deleted"].(bool); !ok {
		t.Fatalf("expected deleted=true, got %#v", deleted["deleted"])
	}
}

func TestIgnoreAndUnignoreJob(t *testing.T) {
	setupUserToolPaths(t)

	ignored, err := IgnoreJob(map[string]any{
		"user_id": "u1",
		"job_url": "https://example.com/jobs/ignored",
		"reason":  "not a fit",
	})
	if err != nil {
		t.Fatalf("IgnoreJob failed: %v", err)
	}
	if got := getString(ignored, "action"); got != "ignored_new" {
		t.Fatalf("expected action=ignored_new, got %q", got)
	}

	listed, err := ListIgnoredJobs(map[string]any{"user_id": "u1"})
	if err != nil {
		t.Fatalf("ListIgnoredJobs failed: %v", err)
	}
	if got, _ := listed["total_ignored_jobs"].(int); got != 1 {
		t.Fatalf("expected total_ignored_jobs=1, got %#v", listed["total_ignored_jobs"])
	}

	unignored, err := UnignoreJob(map[string]any{
		"user_id":        "u1",
		"ignored_job_id": 1,
	})
	if err != nil {
		t.Fatalf("UnignoreJob failed: %v", err)
	}
	if ok, _ := unignored["deleted"].(bool); !ok {
		t.Fatalf("expected deleted=true, got %#v", unignored["deleted"])
	}
}

func TestIgnoreAndUnignoreCompany(t *testing.T) {
	setupUserToolPaths(t)

	ignored, err := IgnoreCompany(map[string]any{
		"user_id":      "u1",
		"company_name": "Acme Inc.",
	})
	if err != nil {
		t.Fatalf("IgnoreCompany failed: %v", err)
	}
	ignoredCompany, _ := ignored["ignored_company"].(map[string]any)
	if got := getString(ignoredCompany, "normalized_company"); got != "acme" {
		t.Fatalf("expected normalized_company=acme, got %q", got)
	}

	listed, err := ListIgnoredCompanies(map[string]any{"user_id": "u1"})
	if err != nil {
		t.Fatalf("ListIgnoredCompanies failed: %v", err)
	}
	if got, _ := listed["total_ignored_companies"].(int); got != 1 {
		t.Fatalf("expected total_ignored_companies=1, got %#v", listed["total_ignored_companies"])
	}

	unignored, err := UnignoreCompany(map[string]any{
		"user_id":            "u1",
		"ignored_company_id": 1,
	})
	if err != nil {
		t.Fatalf("UnignoreCompany failed: %v", err)
	}
	if ok, _ := unignored["deleted"].(bool); !ok {
		t.Fatalf("expected deleted=true, got %#v", unignored["deleted"])
	}
}

func TestJobPipelineLifecycle(t *testing.T) {
	setupUserToolPaths(t)

	applied, err := MarkJobApplied(map[string]any{
		"user_id": "u1",
		"job_url": "https://example.com/jobs/pipeline-1",
		"note":    "application submitted",
	})
	if err != nil {
		t.Fatalf("MarkJobApplied failed: %v", err)
	}
	application, _ := applied["application"].(map[string]any)
	if got := getString(application, "stage"); got != "applied" {
		t.Fatalf("expected stage=applied, got %q", got)
	}

	updated, err := UpdateJobStage(map[string]any{
		"user_id": "u1",
		"job_url": "https://example.com/jobs/pipeline-1",
		"stage":   "interview",
		"note":    "phone screen booked",
	})
	if err != nil {
		t.Fatalf("UpdateJobStage failed: %v", err)
	}
	updatedApplication, _ := updated["application"].(map[string]any)
	if got := getString(updatedApplication, "stage"); got != "interview" {
		t.Fatalf("expected stage=interview, got %q", got)
	}

	if _, err := AddJobNote(map[string]any{
		"user_id": "u1",
		"job_url": "https://example.com/jobs/pipeline-1",
		"note":    "research interviewer profile",
	}); err != nil {
		t.Fatalf("AddJobNote failed: %v", err)
	}

	stageRows, err := ListJobsByStage(map[string]any{
		"user_id": "u1",
		"stage":   "interview",
	})
	if err != nil {
		t.Fatalf("ListJobsByStage failed: %v", err)
	}
	if got, _ := stageRows["total_jobs"].(int); got != 1 {
		t.Fatalf("expected total_jobs=1, got %#v", stageRows["total_jobs"])
	}

	events, err := ListRecentJobEvents(map[string]any{"user_id": "u1"})
	if err != nil {
		t.Fatalf("ListRecentJobEvents failed: %v", err)
	}
	if got, _ := events["total_events"].(int); got < 3 {
		t.Fatalf("expected at least 3 events, got %#v", events["total_events"])
	}

	summary, err := GetJobPipelineSummary(map[string]any{"user_id": "u1"})
	if err != nil {
		t.Fatalf("GetJobPipelineSummary failed: %v", err)
	}
	stageCounts, _ := summary["stage_counts"].(map[string]int)
	if stageCounts == nil {
		stageCountsAny, _ := summary["stage_counts"].(map[string]any)
		if got, _ := stageCountsAny["interview"].(int); got != 1 {
			t.Fatalf("expected interview count=1, got %#v", stageCountsAny["interview"])
		}
	} else if stageCounts["interview"] != 1 {
		t.Fatalf("expected interview count=1, got %#v", stageCounts["interview"])
	}
}

func TestResolveByResultIDAndClearSearchSession(t *testing.T) {
	setupUserToolPaths(t)

	store := map[string]any{
		"sessions": map[string]any{
			"s1": map[string]any{
				"query": map[string]any{
					"user_id": "u1",
				},
				"accepted_jobs": []any{
					map[string]any{
						"job_url":  "https://example.com/jobs/from-session",
						"title":    "Backend Engineer",
						"company":  "Acme",
						"location": "New York, NY",
						"site":     "linkedin",
					},
				},
			},
		},
	}
	if err := saveSearchSessions(store); err != nil {
		t.Fatalf("saveSearchSessions failed: %v", err)
	}

	saved, err := SaveJobForLater(map[string]any{
		"user_id":   "u1",
		"result_id": "s1:1",
	})
	if err != nil {
		t.Fatalf("SaveJobForLater via result_id failed: %v", err)
	}
	savedJob, _ := saved["saved_job"].(map[string]any)
	if got := getString(savedJob, "job_url"); got != "https://example.com/jobs/from-session" {
		t.Fatalf("unexpected job_url resolved from result_id: %q", got)
	}

	cleared, err := ClearSearchSession(map[string]any{
		"user_id":    "u1",
		"session_id": "s1",
	})
	if err != nil {
		t.Fatalf("ClearSearchSession failed: %v", err)
	}
	if ok, _ := cleared["deleted"].(bool); !ok {
		t.Fatalf("expected deleted=true, got %#v", cleared["deleted"])
	}
}

func setupUserToolPaths(t *testing.T) {
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
