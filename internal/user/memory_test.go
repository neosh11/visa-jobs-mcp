package user

import (
	"path/filepath"
	"testing"
)

func TestMemoryLifecycle(t *testing.T) {
	blobPath := filepath.Join(t.TempDir(), "user_memory_blob.json")
	t.Setenv("VISA_USER_BLOB_PATH", blobPath)

	if _, err := AddUserMemoryLine(map[string]any{
		"user_id": "u1",
		"content": "Backend engineer with 6 years of Go",
		"kind":    "skills",
		"source":  "onboarding",
	}); err != nil {
		t.Fatalf("first AddUserMemoryLine failed: %v", err)
	}
	if _, err := AddUserMemoryLine(map[string]any{
		"user_id": "u1",
		"content": "Needs E3 visa transfer in 30 days",
		"kind":    "constraint",
		"source":  "chat",
	}); err != nil {
		t.Fatalf("second AddUserMemoryLine failed: %v", err)
	}

	result, err := QueryUserMemoryBlob(map[string]any{
		"user_id": "u1",
		"query":   "e3",
		"limit":   10,
		"offset":  0,
	})
	if err != nil {
		t.Fatalf("QueryUserMemoryBlob failed: %v", err)
	}
	if got, _ := result["total_lines"].(int); got != 2 {
		t.Fatalf("expected total_lines=2, got %#v", result["total_lines"])
	}
	if got, _ := result["total_matches"].(int); got != 1 {
		t.Fatalf("expected total_matches=1, got %#v", result["total_matches"])
	}

	lines, _ := result["lines"].([]any)
	if len(lines) != 1 {
		t.Fatalf("expected 1 filtered line, got %#v", result["lines"])
	}
	line, _ := lines[0].(map[string]any)
	if got, _ := line["id"].(float64); int(got) != 2 {
		// For interface marshaling paths this may stay int; accept either below.
		if gotInt, ok := line["id"].(int); !ok || gotInt != 2 {
			t.Fatalf("expected filtered line id=2, got %#v", line["id"])
		}
	}

	deleted, err := DeleteUserMemoryLine(map[string]any{
		"user_id": "u1",
		"line_id": 2,
	})
	if err != nil {
		t.Fatalf("DeleteUserMemoryLine failed: %v", err)
	}
	if ok, _ := deleted["deleted"].(bool); !ok {
		t.Fatalf("expected deleted=true, got %#v", deleted["deleted"])
	}
	if remaining, _ := deleted["total_lines"].(int); remaining != 1 {
		t.Fatalf("expected total_lines=1 after delete, got %#v", deleted["total_lines"])
	}
}

func TestDeleteUserMemoryLineValidation(t *testing.T) {
	blobPath := filepath.Join(t.TempDir(), "user_memory_blob.json")
	t.Setenv("VISA_USER_BLOB_PATH", blobPath)

	if _, err := DeleteUserMemoryLine(map[string]any{
		"user_id": "u1",
		"line_id": 0,
	}); err == nil {
		t.Fatal("expected error for non-positive line_id")
	}
}
