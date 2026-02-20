package user

import (
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestFindRelatedTitles(t *testing.T) {
	result, err := FindRelatedTitles(map[string]any{
		"job_title": "Software Engineer",
		"limit":     5,
	})
	if err != nil {
		t.Fatalf("FindRelatedTitles failed: %v", err)
	}
	if got, _ := result["count"].(int); got == 0 {
		t.Fatalf("expected count > 0, got %#v", result["count"])
	}
}

func TestGetBestContactStrategy(t *testing.T) {
	setupUserToolPaths(t)

	plain, err := GetBestContactStrategy(map[string]any{
		"user_id": "u1",
		"job_url": "https://example.com/jobs/1",
	})
	if err != nil {
		t.Fatalf("GetBestContactStrategy (no contacts) failed: %v", err)
	}
	if got := getString(plain, "recommended_channel"); got != "application_plus_linkedin" {
		t.Fatalf("expected application_plus_linkedin channel, got %q", got)
	}

	store := map[string]any{
		"sessions": map[string]any{
			"s1": map[string]any{
				"query": map[string]any{"user_id": "u1"},
				"accepted_jobs": []any{
					map[string]any{
						"job_url": "https://example.com/jobs/2",
						"title":   "SWE",
						"company": "Acme",
						"employer_contacts": []any{
							map[string]any{
								"name":  "Recruiter",
								"email": "r@example.com",
							},
						},
					},
				},
			},
		},
	}
	if err := saveSearchSessions(store); err != nil {
		t.Fatalf("saveSearchSessions failed: %v", err)
	}
	withContact, err := GetBestContactStrategy(map[string]any{
		"user_id":   "u1",
		"result_id": "s1:1",
	})
	if err != nil {
		t.Fatalf("GetBestContactStrategy (contact) failed: %v", err)
	}
	if got := getString(withContact, "recommended_channel"); got != "email" {
		t.Fatalf("expected email channel, got %q", got)
	}
}

func TestGenerateOutreachMessageUsesPreferences(t *testing.T) {
	setupUserToolPaths(t)

	if _, err := SetUserPreferences(map[string]any{
		"user_id":              "u1",
		"preferred_visa_types": []any{"E3"},
	}); err != nil {
		t.Fatalf("SetUserPreferences failed: %v", err)
	}

	message, err := GenerateOutreachMessage(map[string]any{
		"user_id":        "u1",
		"job_url":        "https://example.com/jobs/1",
		"recipient_name": "Alex",
	})
	if err != nil {
		t.Fatalf("GenerateOutreachMessage failed: %v", err)
	}
	body := getString(message, "message")
	if body == "" {
		t.Fatalf("expected non-empty message body")
	}
	if want := "E-3 Australian"; !containsIgnoreCase(body, want) {
		t.Fatalf("expected message to mention %q, got %q", want, body)
	}
}

func TestRefreshCompanyDatasetCache(t *testing.T) {
	tmp := t.TempDir()
	datasetPath := filepath.Join(tmp, "companies.csv")
	csv := "company_name,h1b,h1b1_chile,h1b1_singapore,e3_australian,green_card\nAcme Inc,10,0,0,0,0\nAcme LLC,8,0,0,0,0\nBeta Corp,5,0,0,0,0\n"
	if err := os.WriteFile(datasetPath, []byte(csv), 0o644); err != nil {
		t.Fatalf("write dataset: %v", err)
	}

	result, err := RefreshCompanyDatasetCache(map[string]any{
		"dataset_path": datasetPath,
	})
	if err != nil {
		t.Fatalf("RefreshCompanyDatasetCache failed: %v", err)
	}
	if got, _ := result["rows"].(int); got != 3 {
		t.Fatalf("expected rows=3, got %#v", result["rows"])
	}
	if got, _ := result["distinct_normalized_companies"].(int); got != 2 {
		t.Fatalf("expected distinct_normalized_companies=2, got %#v", result["distinct_normalized_companies"])
	}
}

func containsIgnoreCase(text, sub string) bool {
	return strings.Contains(strings.ToLower(text), strings.ToLower(sub))
}
