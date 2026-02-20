package user

import (
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

func TestDiscoverLatestDolDisclosureURLs(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		_, _ = w.Write([]byte(`
			<html><body>
				<a href="/docs/LCA_Disclosure_Data_FY2025_Q4.xlsx">LCA FY2025 Q4</a>
				<a href="/docs/PERM_Disclosure_Data_FY2024.xlsx">PERM FY2024</a>
				<a href="https://example.org/not-related">Ignore me</a>
			</body></html>
		`))
	}))
	defer server.Close()

	result, err := DiscoverLatestDolDisclosureURLs(map[string]any{
		"performance_url": server.URL + "/performance",
	})
	if err != nil {
		t.Fatalf("DiscoverLatestDolDisclosureURLs failed: %v", err)
	}
	if got := getString(result, "status"); got != "ok" {
		t.Fatalf("expected status=ok, got %q (%#v)", got, result)
	}
	if got, _ := intFromAny(result["total_disclosures_found"]); got != 2 {
		t.Fatalf("expected total_disclosures_found=2, got %#v", result["total_disclosures_found"])
	}

	lca := getStringList(result, "lca_disclosure_urls")
	perm := getStringList(result, "perm_disclosure_urls")
	if len(lca) == 0 || len(perm) == 0 {
		t.Fatalf("expected lca and perm urls, got lca=%#v perm=%#v", lca, perm)
	}
}

func TestRunInternalDolPipeline(t *testing.T) {
	success, err := RunInternalDolPipeline(map[string]any{
		"command": "echo pipeline-ok",
	})
	if err != nil {
		t.Fatalf("RunInternalDolPipeline success path failed: %v", err)
	}
	if got := getString(success, "status"); got != "completed" {
		t.Fatalf("expected completed status, got %q (%#v)", got, success)
	}
	if out := getString(success, "stdout_tail"); !strings.Contains(out, "pipeline-ok") {
		t.Fatalf("expected stdout_tail to include pipeline-ok, got %q", out)
	}

	failed, err := RunInternalDolPipeline(map[string]any{
		"command": "echo broken 1>&2; exit 7",
	})
	if err != nil {
		t.Fatalf("RunInternalDolPipeline failure path should still return payload: %v", err)
	}
	if got := getString(failed, "status"); got != "failed" {
		t.Fatalf("expected failed status, got %q (%#v)", got, failed)
	}
	if got, _ := intFromAny(failed["exit_code"]); got != 7 {
		t.Fatalf("expected exit_code=7, got %#v", failed["exit_code"])
	}
}
