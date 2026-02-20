package user

import (
	"encoding/json"
	"os"
	"path/filepath"
	"testing"
	"time"
)

func TestSetAndGetUserPreferences(t *testing.T) {
	prefsFile := filepath.Join(t.TempDir(), "prefs.json")
	t.Setenv("VISA_USER_PREFS_PATH", prefsFile)

	payload, err := SetUserPreferences(map[string]any{
		"user_id":              "u1",
		"preferred_visa_types": []any{"E-3", "h1b", "H1B"},
	})
	if err != nil {
		t.Fatalf("SetUserPreferences returned error: %v", err)
	}

	prefs, ok := payload["preferences"].(map[string]any)
	if !ok {
		t.Fatalf("expected preferences map, got: %#v", payload["preferences"])
	}
	rawTypes, ok := prefs["preferred_visa_types"].([]string)
	if !ok {
		// json-like maps can also hold []any; handle both for stable assertion.
		typedAny, okAny := prefs["preferred_visa_types"].([]any)
		if !okAny {
			t.Fatalf("expected preferred_visa_types slice, got: %#v", prefs["preferred_visa_types"])
		}
		rawTypes = make([]string, 0, len(typedAny))
		for _, item := range typedAny {
			if s, ok := item.(string); ok {
				rawTypes = append(rawTypes, s)
			}
		}
	}
	if len(rawTypes) != 2 || rawTypes[0] != "e3_australian" || rawTypes[1] != "h1b" {
		t.Fatalf("unexpected normalized visa types: %#v", rawTypes)
	}

	stored, err := GetUserPreferences(map[string]any{"user_id": "u1"})
	if err != nil {
		t.Fatalf("GetUserPreferences returned error: %v", err)
	}
	gotPrefs, _ := stored["preferences"].(map[string]any)
	gotTypesAny, _ := gotPrefs["preferred_visa_types"].([]any)
	if len(gotTypesAny) != 2 {
		t.Fatalf("expected 2 visa types in stored preferences, got %#v", gotPrefs["preferred_visa_types"])
	}
}

func TestSetUserConstraintsValidationAndPersistence(t *testing.T) {
	prefsFile := filepath.Join(t.TempDir(), "prefs.json")
	t.Setenv("VISA_USER_PREFS_PATH", prefsFile)

	if _, err := SetUserConstraints(map[string]any{
		"user_id":        "u2",
		"days_remaining": -1,
	}); err == nil {
		t.Fatal("expected validation error for negative days_remaining")
	}

	payload, err := SetUserConstraints(map[string]any{
		"user_id":             "u2",
		"days_remaining":      30,
		"work_modes":          []any{"Remote", "onsite", "remote"},
		"willing_to_relocate": true,
	})
	if err != nil {
		t.Fatalf("SetUserConstraints returned error: %v", err)
	}

	constraints, ok := payload["constraints"].(map[string]any)
	if !ok {
		t.Fatalf("expected constraints map, got: %#v", payload["constraints"])
	}
	if got, _ := constraints["days_remaining"].(int); got != 30 {
		t.Fatalf("expected days_remaining=30, got %#v", constraints["days_remaining"])
	}
	if got, _ := constraints["willing_to_relocate"].(bool); !got {
		t.Fatalf("expected willing_to_relocate=true, got %#v", constraints["willing_to_relocate"])
	}
	workModes, _ := constraints["work_modes"].([]string)
	if len(workModes) != 2 || workModes[0] != "onsite" || workModes[1] != "remote" {
		t.Fatalf("unexpected normalized work modes: %#v", constraints["work_modes"])
	}
	if _, ok := constraints["updated_at_utc"].(string); !ok {
		t.Fatalf("expected updated_at_utc string, got %#v", constraints["updated_at_utc"])
	}
}

func TestGetUserReadiness(t *testing.T) {
	tmpDir := t.TempDir()
	prefsFile := filepath.Join(tmpDir, "prefs.json")
	datasetPath := filepath.Join(tmpDir, "companies.csv")
	manifestPath := filepath.Join(tmpDir, "last_run.json")

	t.Setenv("VISA_USER_PREFS_PATH", prefsFile)

	if err := os.WriteFile(datasetPath, []byte("company\nacme\n"), 0o644); err != nil {
		t.Fatalf("write dataset: %v", err)
	}
	manifest := map[string]any{
		"run_at_utc": time.Now().UTC().Add(-2 * time.Hour).Format(time.RFC3339),
	}
	manifestBytes, _ := json.Marshal(manifest)
	if err := os.WriteFile(manifestPath, manifestBytes, 0o644); err != nil {
		t.Fatalf("write manifest: %v", err)
	}

	if _, err := SetUserPreferences(map[string]any{
		"user_id":              "u3",
		"preferred_visa_types": []any{"E3"},
	}); err != nil {
		t.Fatalf("SetUserPreferences returned error: %v", err)
	}

	payload, err := GetUserReadiness(map[string]any{
		"user_id":       "u3",
		"dataset_path":  datasetPath,
		"manifest_path": manifestPath,
	})
	if err != nil {
		t.Fatalf("GetUserReadiness returned error: %v", err)
	}

	readiness, ok := payload["readiness"].(map[string]any)
	if !ok {
		t.Fatalf("expected readiness map, got %#v", payload["readiness"])
	}
	if ready, _ := readiness["ready_for_search"].(bool); !ready {
		t.Fatalf("expected ready_for_search=true, got %#v", readiness["ready_for_search"])
	}
	if hasPrefs, _ := readiness["has_preferences"].(bool); !hasPrefs {
		t.Fatalf("expected has_preferences=true, got %#v", readiness["has_preferences"])
	}
	if datasetExists, _ := readiness["dataset_exists"].(bool); !datasetExists {
		t.Fatalf("expected dataset_exists=true, got %#v", readiness["dataset_exists"])
	}

	freshness, ok := payload["dataset_freshness"].(map[string]any)
	if !ok {
		t.Fatalf("expected dataset_freshness map, got %#v", payload["dataset_freshness"])
	}
	if stale, _ := freshness["is_stale"].(bool); stale {
		t.Fatalf("expected is_stale=false, got true with freshness=%#v", freshness)
	}
}
