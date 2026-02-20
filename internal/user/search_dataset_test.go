package user

import (
	"path/filepath"
	"strings"
	"testing"
)

func TestDatasetFallbackCandidates(t *testing.T) {
	exePath := "/opt/homebrew/bin/visa-jobs-mcp"
	candidates := datasetFallbackCandidates(exePath)
	if len(candidates) != 4 {
		t.Fatalf("expected 4 candidates, got %d", len(candidates))
	}

	foundPackagedPath := false
	for _, candidate := range candidates {
		if strings.Contains(candidate, filepath.Join("share", "visa-jobs-mcp", "data", "companies.csv")) {
			foundPackagedPath = true
			break
		}
	}
	if !foundPackagedPath {
		t.Fatalf("expected packaged share data candidate, got %#v", candidates)
	}
}
