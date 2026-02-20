package mcp

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"slices"
	"strings"
	"sync"
	"testing"
	"time"

	mcpSDK "github.com/modelcontextprotocol/go-sdk/mcp"

	"github.com/neosh11/visa-jobs-mcp/internal/user"
)

func TestInitializeAndListTools(t *testing.T) {
	_, session, cleanup := connectTestSession(t)
	defer cleanup()

	initResult := session.InitializeResult()
	if initResult == nil || initResult.ServerInfo == nil {
		t.Fatalf("initialize result missing server info: %#v", initResult)
	}
	if initResult.ServerInfo.Name != "visa-jobs-mcp" {
		t.Fatalf("unexpected server name: %q", initResult.ServerInfo.Name)
	}
	if got := strings.TrimSpace(initResult.ServerInfo.Version); got == "" {
		t.Fatalf("expected non-empty server version")
	}

	tools, err := session.ListTools(context.Background(), &mcpSDK.ListToolsParams{})
	if err != nil {
		t.Fatalf("ListTools failed: %v", err)
	}
	if len(tools.Tools) == 0 {
		t.Fatal("expected at least one tool")
	}
	foundReadiness := false
	foundLegacyFind := false
	foundSetPrefsSchema := false
	for _, tool := range tools.Tools {
		if tool.Name == "get_user_readiness" {
			foundReadiness = true
		}
		if tool.Name == "find_visa_sponsored_jobs" {
			foundLegacyFind = true
		}
		if tool.Name == "set_user_preferences" {
			schema := toSchemaMap(t, tool.InputSchema)
			required := toStringSlice(schema["required"])
			if !slices.Contains(required, "user_id") || !slices.Contains(required, "preferred_visa_types") {
				t.Fatalf("set_user_preferences schema missing required fields: %#v", schema["required"])
			}
			props := toMap(schema["properties"])
			prefsProp := toMap(props["preferred_visa_types"])
			if got := getStringFromAnyMap(prefsProp, "type"); got != "array" {
				t.Fatalf("preferred_visa_types should be array in schema, got %#v", prefsProp)
			}
			foundSetPrefsSchema = true
		}
	}
	if !foundReadiness {
		t.Fatal("expected get_user_readiness in tools/list")
	}
	if foundLegacyFind {
		t.Fatal("legacy find_visa_sponsored_jobs should not be exposed")
	}
	if !foundSetPrefsSchema {
		t.Fatal("expected set_user_preferences in tools/list")
	}
}

func TestCapabilitiesVersionUsesRuntimeVersion(t *testing.T) {
	_, session, cleanup := connectTestSession(t)
	defer cleanup()

	result, err := session.CallTool(context.Background(), &mcpSDK.CallToolParams{
		Name:      "get_mcp_capabilities",
		Arguments: map[string]any{},
	})
	if err != nil {
		t.Fatalf("get_mcp_capabilities call failed: %v", err)
	}
	if result.IsError {
		t.Fatalf("get_mcp_capabilities returned tool error: %#v", result)
	}
	structured, _ := result.StructuredContent.(map[string]any)
	if got := getStringFromAnyMap(structured, "version"); got != Version {
		t.Fatalf("expected version=%q, got %q", Version, got)
	}
}

func TestCallPortedTools(t *testing.T) {
	tmpDir := t.TempDir()
	prefsPath := filepath.Join(tmpDir, "prefs.json")
	datasetPath := filepath.Join(tmpDir, "companies.csv")
	manifestPath := filepath.Join(tmpDir, "last_run.json")
	t.Setenv("VISA_USER_PREFS_PATH", prefsPath)

	if err := os.WriteFile(datasetPath, []byte("company\nacme\n"), 0o644); err != nil {
		t.Fatalf("write dataset: %v", err)
	}
	manifest := fmt.Sprintf("{\"run_at_utc\":\"%s\"}", time.Now().UTC().Format(time.RFC3339))
	if err := os.WriteFile(manifestPath, []byte(manifest), 0o644); err != nil {
		t.Fatalf("write manifest: %v", err)
	}

	_, session, cleanup := connectTestSession(t)
	defer cleanup()

	setPrefsResult, err := session.CallTool(context.Background(), &mcpSDK.CallToolParams{
		Name: "set_user_preferences",
		Arguments: map[string]any{
			"user_id":              "default",
			"preferred_visa_types": []any{"E3"},
		},
	})
	if err != nil {
		t.Fatalf("set_user_preferences call failed: %v", err)
	}
	if setPrefsResult.IsError {
		t.Fatalf("set_user_preferences returned tool error: %v", setPrefsResult.GetError())
	}

	readinessResult, err := session.CallTool(context.Background(), &mcpSDK.CallToolParams{
		Name: "get_user_readiness",
		Arguments: map[string]any{
			"user_id":       "default",
			"dataset_path":  datasetPath,
			"manifest_path": manifestPath,
		},
	})
	if err != nil {
		t.Fatalf("get_user_readiness call failed: %v", err)
	}
	if readinessResult.IsError {
		t.Fatalf("get_user_readiness returned tool error: %v", readinessResult.GetError())
	}
	structured, _ := readinessResult.StructuredContent.(map[string]any)
	readiness, _ := structured["readiness"].(map[string]any)
	if ready, _ := readiness["ready_for_search"].(bool); !ready {
		t.Fatalf("expected ready_for_search=true, got %#v", readiness["ready_for_search"])
	}
}

func TestUnknownToolReturnsProtocolError(t *testing.T) {
	_, session, cleanup := connectTestSession(t)
	defer cleanup()

	_, err := session.CallTool(context.Background(), &mcpSDK.CallToolParams{
		Name: "unknown_tool_name_for_test",
		Arguments: map[string]any{
			"user_id":   "default",
			"location":  "New York, NY",
			"job_title": "software engineer",
		},
	})
	if err == nil {
		t.Fatal("expected protocol error for unknown tool")
	}
	if got := strings.ToLower(err.Error()); !strings.Contains(got, "unknown tool") {
		t.Fatalf("expected unknown tool error, got %q", got)
	}
}

func TestCallJobManagementTool(t *testing.T) {
	tmpDir := t.TempDir()
	t.Setenv("VISA_SAVED_JOBS_PATH", filepath.Join(tmpDir, "saved_jobs.json"))
	t.Setenv("VISA_JOB_DB_PATH", filepath.Join(tmpDir, "job_pipeline.json"))

	_, session, cleanup := connectTestSession(t)
	defer cleanup()

	saveResult, err := session.CallTool(context.Background(), &mcpSDK.CallToolParams{
		Name: "save_job_for_later",
		Arguments: map[string]any{
			"user_id": "default",
			"job_url": "https://example.com/jobs/123",
			"title":   "Software Engineer",
			"site":    "linkedin",
		},
	})
	if err != nil {
		t.Fatalf("save_job_for_later call failed: %v", err)
	}
	if saveResult.IsError {
		t.Fatalf("save_job_for_later returned tool error: %#v", saveResult)
	}
	structured, _ := saveResult.StructuredContent.(map[string]any)
	if got := getStringFromAnyMap(structured, "action"); got != "saved_new" {
		t.Fatalf("expected action=saved_new, got %q", got)
	}
}

func TestConcurrentSaveJobForLaterMaintainsAllRows(t *testing.T) {
	tmpDir := t.TempDir()
	t.Setenv("VISA_SAVED_JOBS_PATH", filepath.Join(tmpDir, "saved_jobs.json"))
	t.Setenv("VISA_JOB_DB_PATH", filepath.Join(tmpDir, "job_pipeline.json"))

	_, session, cleanup := connectTestSession(t)
	defer cleanup()

	const calls = 20
	var wg sync.WaitGroup
	errCh := make(chan error, calls)
	for i := 0; i < calls; i++ {
		wg.Add(1)
		idx := i
		go func() {
			defer wg.Done()
			_, err := session.CallTool(context.Background(), &mcpSDK.CallToolParams{
				Name: "save_job_for_later",
				Arguments: map[string]any{
					"user_id": "default",
					"job_url": fmt.Sprintf("https://example.com/jobs/concurrent-%d", idx),
					"title":   "Software Engineer",
					"site":    "linkedin",
				},
			})
			if err != nil {
				errCh <- err
			}
		}()
	}
	wg.Wait()
	close(errCh)

	for err := range errCh {
		if err != nil {
			t.Fatalf("concurrent save call failed: %v", err)
		}
	}

	listed, err := session.CallTool(context.Background(), &mcpSDK.CallToolParams{
		Name: "list_saved_jobs",
		Arguments: map[string]any{
			"user_id": "default",
			"limit":   200,
			"offset":  0,
		},
	})
	if err != nil {
		t.Fatalf("list_saved_jobs failed: %v", err)
	}
	if listed.IsError {
		t.Fatalf("list_saved_jobs returned tool error: %#v", listed)
	}
	structured, _ := listed.StructuredContent.(map[string]any)
	total, ok := intFromAny(structured["total_saved_jobs"])
	if !ok {
		t.Fatalf("expected integer total_saved_jobs, got %#v", structured["total_saved_jobs"])
	}
	if total != calls {
		t.Fatalf("expected total_saved_jobs=%d, got %d", calls, total)
	}
}

func TestStartVisaJobSearchReturnsRunMetadata(t *testing.T) {
	tmpDir := t.TempDir()
	t.Setenv("VISA_USER_PREFS_PATH", filepath.Join(tmpDir, "prefs.json"))
	t.Setenv("VISA_SEARCH_RUNS_PATH", filepath.Join(tmpDir, "search_runs.json"))
	t.Setenv("VISA_SEARCH_SESSION_PATH", filepath.Join(tmpDir, "search_sessions.json"))
	t.Setenv("VISA_COMPANY_DATASET_PATH", filepath.Join(tmpDir, "missing.csv"))

	_, err := user.SetUserPreferences(map[string]any{
		"user_id":              "default",
		"preferred_visa_types": []any{"E3"},
	})
	if err != nil {
		t.Fatalf("SetUserPreferences failed: %v", err)
	}

	_, session, cleanup := connectTestSession(t)
	defer cleanup()

	result, err := session.CallTool(context.Background(), &mcpSDK.CallToolParams{
		Name: "start_visa_job_search",
		Arguments: map[string]any{
			"user_id":   "default",
			"location":  "New York, NY",
			"job_title": "software engineer",
		},
	})
	if err != nil {
		t.Fatalf("start_visa_job_search call failed unexpectedly: %v", err)
	}
	if result.IsError {
		t.Fatalf("expected non-error tool result, got %#v", result)
	}
	structured, _ := result.StructuredContent.(map[string]any)
	runID := getStringFromAnyMap(structured, "run_id")
	if runID == "" {
		t.Fatalf("expected run_id in response, got %#v", structured)
	}
	status := strings.ToLower(getStringFromAnyMap(structured, "status"))
	switch status {
	case "pending", "running", "failed", "completed":
	default:
		t.Fatalf("unexpected start status %q", status)
	}
	if got := getStringFromAnyMap(structured, "poll_tool"); got != "get_visa_job_search_status" {
		t.Fatalf("expected poll_tool=get_visa_job_search_status, got %q", got)
	}
	waitForTerminalRunStatusViaTool(t, session, "default", runID, 5*time.Second)
}

func connectTestSession(t *testing.T) (*mcpSDK.Server, *mcpSDK.ClientSession, func()) {
	t.Helper()
	ensureMCPTestPaths(t)

	server, err := newServer()
	if err != nil {
		t.Fatalf("newServer failed: %v", err)
	}
	client := mcpSDK.NewClient(&mcpSDK.Implementation{
		Name:    "mcp-test-client",
		Version: "test",
	}, nil)

	ctx, cancel := context.WithCancel(context.Background())
	clientTransport, serverTransport := mcpSDK.NewInMemoryTransports()
	serverErr := make(chan error, 1)
	go func() {
		serverErr <- server.Run(ctx, serverTransport)
	}()

	session, err := client.Connect(ctx, clientTransport, nil)
	if err != nil {
		cancel()
		t.Fatalf("client.Connect failed: %v", err)
	}

	cleanup := func() {
		_ = session.Close()
		cancel()
		select {
		case err := <-serverErr:
			if err != nil && !errors.Is(err, context.Canceled) && !strings.Contains(strings.ToLower(err.Error()), "closing") {
				t.Fatalf("server.Run returned unexpected error: %v", err)
			}
		case <-time.After(2 * time.Second):
			t.Fatalf("timeout waiting for server shutdown")
		}
	}
	return server, session, cleanup
}

func ensureMCPTestPaths(t *testing.T) {
	t.Helper()
	root := t.TempDir()
	setEnvIfUnset(t, "VISA_USER_PREFS_PATH", filepath.Join(root, "prefs.json"))
	setEnvIfUnset(t, "VISA_USER_BLOB_PATH", filepath.Join(root, "blob.json"))
	setEnvIfUnset(t, "VISA_SAVED_JOBS_PATH", filepath.Join(root, "saved_jobs.json"))
	setEnvIfUnset(t, "VISA_IGNORED_JOBS_PATH", filepath.Join(root, "ignored_jobs.json"))
	setEnvIfUnset(t, "VISA_IGNORED_COMPANIES_PATH", filepath.Join(root, "ignored_companies.json"))
	setEnvIfUnset(t, "VISA_SEARCH_SESSION_PATH", filepath.Join(root, "search_sessions.json"))
	setEnvIfUnset(t, "VISA_SEARCH_RUNS_PATH", filepath.Join(root, "search_runs.json"))
	setEnvIfUnset(t, "VISA_JOB_DB_PATH", filepath.Join(root, "job_pipeline.json"))
}

func setEnvIfUnset(t *testing.T, key, value string) {
	t.Helper()
	if strings.TrimSpace(os.Getenv(key)) != "" {
		return
	}
	t.Setenv(key, value)
}

func getStringFromAnyMap(m map[string]any, key string) string {
	if m == nil {
		return ""
	}
	value, ok := m[key]
	if !ok || value == nil {
		return ""
	}
	typed, ok := value.(string)
	if !ok {
		return ""
	}
	return typed
}

func toSchemaMap(t *testing.T, value any) map[string]any {
	t.Helper()
	raw, err := json.Marshal(value)
	if err != nil {
		t.Fatalf("marshal schema: %v", err)
	}
	var out map[string]any
	if err := json.Unmarshal(raw, &out); err != nil {
		t.Fatalf("unmarshal schema: %v", err)
	}
	return out
}

func toMap(value any) map[string]any {
	m, _ := value.(map[string]any)
	return m
}

func toStringSlice(value any) []string {
	list, ok := value.([]any)
	if !ok {
		return nil
	}
	out := make([]string, 0, len(list))
	for _, item := range list {
		text, _ := item.(string)
		if text != "" {
			out = append(out, text)
		}
	}
	return out
}

func intFromAny(value any) (int, bool) {
	switch typed := value.(type) {
	case int:
		return typed, true
	case float64:
		return int(typed), true
	default:
		return 0, false
	}
}

func waitForTerminalRunStatusViaTool(t *testing.T, session *mcpSDK.ClientSession, userID, runID string, timeout time.Duration) {
	t.Helper()
	deadline := time.Now().Add(timeout)
	for time.Now().Before(deadline) {
		statusResult, err := session.CallTool(context.Background(), &mcpSDK.CallToolParams{
			Name: "get_visa_job_search_status",
			Arguments: map[string]any{
				"user_id": userID,
				"run_id":  runID,
				"cursor":  0,
			},
		})
		if err != nil {
			t.Fatalf("get_visa_job_search_status failed: %v", err)
		}
		if statusResult.IsError {
			t.Fatalf("get_visa_job_search_status returned tool error: %#v", statusResult)
		}
		structured, _ := statusResult.StructuredContent.(map[string]any)
		terminal, _ := structured["is_terminal"].(bool)
		if terminal {
			return
		}
		time.Sleep(20 * time.Millisecond)
	}

	_, _ = session.CallTool(context.Background(), &mcpSDK.CallToolParams{
		Name: "cancel_visa_job_search",
		Arguments: map[string]any{
			"user_id": userID,
			"run_id":  runID,
		},
	})
	t.Fatalf("timeout waiting for search run to reach terminal status: run_id=%s", runID)
}
