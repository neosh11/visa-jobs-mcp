package user

import (
	"encoding/json"
	"os"
	"path/filepath"
	"testing"
)

func TestExportAndDeleteUserData(t *testing.T) {
	tmpDir := t.TempDir()
	prefsPath := filepath.Join(tmpDir, "prefs.json")
	blobPath := filepath.Join(tmpDir, "blob.json")
	savedPath := filepath.Join(tmpDir, "saved.json")
	ignoredPath := filepath.Join(tmpDir, "ignored.json")
	ignoredCompaniesPathValue := filepath.Join(tmpDir, "ignored_companies.json")
	sessionsPath := filepath.Join(tmpDir, "sessions.json")
	runsPath := filepath.Join(tmpDir, "runs.json")
	jobDBPathValue := filepath.Join(tmpDir, "jobs.db")

	t.Setenv("VISA_USER_PREFS_PATH", prefsPath)
	t.Setenv("VISA_USER_BLOB_PATH", blobPath)
	t.Setenv("VISA_SAVED_JOBS_PATH", savedPath)
	t.Setenv("VISA_IGNORED_JOBS_PATH", ignoredPath)
	t.Setenv("VISA_IGNORED_COMPANIES_PATH", ignoredCompaniesPathValue)
	t.Setenv("VISA_SEARCH_SESSION_PATH", sessionsPath)
	t.Setenv("VISA_SEARCH_RUNS_PATH", runsPath)
	t.Setenv("VISA_JOB_DB_PATH", jobDBPathValue)

	if _, err := SetUserPreferences(map[string]any{
		"user_id":              "u1",
		"preferred_visa_types": []any{"E3"},
	}); err != nil {
		t.Fatalf("SetUserPreferences failed: %v", err)
	}
	if _, err := AddUserMemoryLine(map[string]any{
		"user_id": "u1",
		"content": "Wants NYC hybrid roles",
	}); err != nil {
		t.Fatalf("AddUserMemoryLine failed: %v", err)
	}

	writeJSONFile(t, savedPath, map[string]any{
		"users": map[string]any{
			"u1": map[string]any{
				"jobs": []any{map[string]any{"id": 1, "job_url": "https://example.com/j/1"}},
			},
		},
	})
	writeJSONFile(t, ignoredPath, map[string]any{
		"users": map[string]any{
			"u1": map[string]any{
				"jobs": []any{map[string]any{"id": 1, "job_url": "https://example.com/j/2"}},
			},
		},
	})
	writeJSONFile(t, ignoredCompaniesPathValue, map[string]any{
		"users": map[string]any{
			"u1": map[string]any{
				"companies": []any{map[string]any{"id": 1, "company_name": "Acme"}},
			},
		},
	})
	writeJSONFile(t, sessionsPath, map[string]any{
		"sessions": map[string]any{
			"s1": map[string]any{
				"query": map[string]any{
					"user_id": "u1",
				},
				"accepted_jobs_total": 4,
			},
		},
	})
	writeJSONFile(t, runsPath, map[string]any{
		"runs": map[string]any{
			"r1": map[string]any{
				"status": "running",
				"query": map[string]any{
					"user_id": "u1",
				},
			},
		},
	})

	exported, err := ExportUserData(map[string]any{"user_id": "u1"})
	if err != nil {
		t.Fatalf("ExportUserData failed: %v", err)
	}
	counts, _ := exported["counts"].(map[string]any)
	if got, _ := counts["memory_lines"].(int); got != 1 {
		t.Fatalf("expected memory_lines=1, got %#v", counts["memory_lines"])
	}
	if got, _ := counts["saved_jobs"].(int); got != 1 {
		t.Fatalf("expected saved_jobs=1, got %#v", counts["saved_jobs"])
	}
	if got, _ := counts["ignored_jobs"].(int); got != 1 {
		t.Fatalf("expected ignored_jobs=1, got %#v", counts["ignored_jobs"])
	}
	if got, _ := counts["ignored_companies"].(int); got != 1 {
		t.Fatalf("expected ignored_companies=1, got %#v", counts["ignored_companies"])
	}
	if got, _ := counts["search_sessions"].(int); got != 1 {
		t.Fatalf("expected search_sessions=1, got %#v", counts["search_sessions"])
	}
	if got, _ := counts["search_runs"].(int); got != 1 {
		t.Fatalf("expected search_runs=1, got %#v", counts["search_runs"])
	}

	if _, err := DeleteUserData(map[string]any{
		"user_id": "u1",
		"confirm": true,
	}); err != nil {
		t.Fatalf("DeleteUserData failed: %v", err)
	}

	afterDelete, err := ExportUserData(map[string]any{"user_id": "u1"})
	if err != nil {
		t.Fatalf("ExportUserData after delete failed: %v", err)
	}
	afterCounts, _ := afterDelete["counts"].(map[string]any)
	for _, key := range []string{
		"memory_lines",
		"saved_jobs",
		"ignored_jobs",
		"ignored_companies",
		"search_sessions",
		"search_runs",
	} {
		if got, _ := afterCounts[key].(int); got != 0 {
			t.Fatalf("expected %s=0 after delete, got %#v", key, afterCounts[key])
		}
	}
}

func TestDeleteUserDataRequiresConfirm(t *testing.T) {
	if _, err := DeleteUserData(map[string]any{
		"user_id": "u1",
		"confirm": false,
	}); err == nil {
		t.Fatal("expected confirm=true validation error")
	}
}

func writeJSONFile(t *testing.T, path string, payload map[string]any) {
	t.Helper()
	raw, err := json.MarshalIndent(payload, "", "  ")
	if err != nil {
		t.Fatalf("marshal json payload: %v", err)
	}
	if err := os.WriteFile(path, raw, 0o644); err != nil {
		t.Fatalf("write json file %s: %v", path, err)
	}
}
