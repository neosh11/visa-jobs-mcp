package mcp

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"strings"
	"sync"

	mcpSDK "github.com/modelcontextprotocol/go-sdk/mcp"

	"github.com/neosh11/visa-jobs-mcp/internal/contract"
	"github.com/neosh11/visa-jobs-mcp/internal/user"
)

type toolHandler func(args map[string]any) (map[string]any, error)

var (
	userToolLocks   sync.Map
	sharedToolMutex sync.Mutex
)

var implementedToolHandlers = map[string]toolHandler{
	"get_mcp_capabilities":                getMCPCapabilities,
	"set_user_preferences":                user.SetUserPreferences,
	"set_user_constraints":                user.SetUserConstraints,
	"get_user_preferences":                user.GetUserPreferences,
	"get_user_readiness":                  user.GetUserReadiness,
	"find_related_titles":                 user.FindRelatedTitles,
	"get_best_contact_strategy":           user.GetBestContactStrategy,
	"generate_outreach_message":           user.GenerateOutreachMessage,
	"add_user_memory_line":                user.AddUserMemoryLine,
	"query_user_memory_blob":              user.QueryUserMemoryBlob,
	"delete_user_memory_line":             user.DeleteUserMemoryLine,
	"export_user_data":                    user.ExportUserData,
	"delete_user_data":                    user.DeleteUserData,
	"save_job_for_later":                  user.SaveJobForLater,
	"list_saved_jobs":                     user.ListSavedJobs,
	"delete_saved_job":                    user.DeleteSavedJob,
	"ignore_job":                          user.IgnoreJob,
	"list_ignored_jobs":                   user.ListIgnoredJobs,
	"unignore_job":                        user.UnignoreJob,
	"ignore_company":                      user.IgnoreCompany,
	"list_ignored_companies":              user.ListIgnoredCompanies,
	"unignore_company":                    user.UnignoreCompany,
	"mark_job_applied":                    user.MarkJobApplied,
	"update_job_stage":                    user.UpdateJobStage,
	"list_jobs_by_stage":                  user.ListJobsByStage,
	"add_job_note":                        user.AddJobNote,
	"list_recent_job_events":              user.ListRecentJobEvents,
	"get_job_pipeline_summary":            user.GetJobPipelineSummary,
	"clear_search_session":                user.ClearSearchSession,
	"refresh_company_dataset_cache":       user.RefreshCompanyDatasetCache,
	"start_visa_job_search":               user.StartVisaJobSearch,
	"get_visa_job_search_status":          user.GetVisaJobSearchStatus,
	"get_visa_job_search_results":         user.GetVisaJobSearchResults,
	"cancel_visa_job_search":              user.CancelVisaJobSearch,
	"discover_latest_dol_disclosure_urls": user.DiscoverLatestDolDisclosureURLs,
	"run_internal_dol_pipeline":           user.RunInternalDolPipeline,
}

func Run(in io.Reader, out io.Writer) error {
	server, err := newServer()
	if err != nil {
		return err
	}
	err = server.Run(context.Background(), &mcpSDK.IOTransport{
		Reader: asReadCloser(in),
		Writer: asWriteCloser(out),
	})
	if err == nil {
		return nil
	}
	if errors.Is(err, io.EOF) || strings.Contains(err.Error(), "server is closing: EOF") {
		return nil
	}
	return err
}

func newServer() (*mcpSDK.Server, error) {
	caps, err := contract.Capabilities()
	if err != nil {
		return nil, err
	}
	serverName := "visa-jobs-mcp"
	if value, ok := caps["server"].(string); ok && value != "" {
		serverName = value
	}
	serverVersion := "0.1.0-dev"
	if value, ok := caps["version"].(string); ok && value != "" {
		serverVersion = value
	}

	server := mcpSDK.NewServer(&mcpSDK.Implementation{
		Name:    serverName,
		Version: serverVersion,
	}, nil)

	tools, err := contract.ToolContracts()
	if err != nil {
		return nil, err
	}
	for _, tc := range tools {
		tool := tc
		handler := resolveToolHandler(tool.Name)
		mcpSDK.AddTool(server, &mcpSDK.Tool{
			Name:        tool.Name,
			Description: tool.Description,
			InputSchema: buildInputSchema(tool),
		}, func(
			_ context.Context,
			_ *mcpSDK.CallToolRequest,
			input map[string]any,
		) (*mcpSDK.CallToolResult, map[string]any, error) {
			if input == nil {
				input = map[string]any{}
			}
			payload, err := withRequestLock(input, func() (map[string]any, error) {
				return handler(input)
			})
			if err != nil {
				return nil, nil, err
			}

			contentText, err := prettyJSON(payload)
			if err != nil {
				contentText = fmt.Sprintf("%v", payload)
			}
			return &mcpSDK.CallToolResult{
				Content: []mcpSDK.Content{
					&mcpSDK.TextContent{Text: contentText},
				},
			}, payload, nil
		})
	}

	return server, nil
}

func resolveToolHandler(name string) toolHandler {
	handler, ok := implementedToolHandlers[name]
	if ok {
		return handler
	}
	return func(_ map[string]any) (map[string]any, error) {
		return nil, fmt.Errorf("tool '%s' is not implemented in Go runtime yet", name)
	}
}

func buildInputSchema(tool contract.ToolContract) map[string]any {
	required := make([]string, 0, len(tool.RequiredInputs))
	required = append(required, tool.RequiredInputs...)
	return map[string]any{
		"type":                 "object",
		"properties":           map[string]any{},
		"required":             required,
		"additionalProperties": true,
	}
}

func prettyJSON(value map[string]any) (string, error) {
	content, err := json.MarshalIndent(value, "", "  ")
	if err != nil {
		return "", err
	}
	return string(content), nil
}

func getMCPCapabilities(_ map[string]any) (map[string]any, error) {
	payload, err := contract.Capabilities()
	if err != nil {
		return nil, fmt.Errorf("failed to load capabilities: %w", err)
	}
	return payload, nil
}

func asReadCloser(in io.Reader) io.ReadCloser {
	if rc, ok := in.(io.ReadCloser); ok {
		return rc
	}
	return io.NopCloser(in)
}

type nopWriteCloser struct {
	io.Writer
}

func (w *nopWriteCloser) Close() error {
	return nil
}

func asWriteCloser(out io.Writer) io.WriteCloser {
	if wc, ok := out.(io.WriteCloser); ok {
		return wc
	}
	return &nopWriteCloser{Writer: out}
}

func withRequestLock(input map[string]any, fn func() (map[string]any, error)) (map[string]any, error) {
	uid := requestUserID(input)
	if uid == "" {
		sharedToolMutex.Lock()
		defer sharedToolMutex.Unlock()
		return fn()
	}
	lock := userLock(uid)
	lock.Lock()
	defer lock.Unlock()
	return fn()
}

func requestUserID(input map[string]any) string {
	if input == nil {
		return ""
	}
	value, ok := input["user_id"]
	if !ok || value == nil {
		return ""
	}
	text := strings.TrimSpace(fmt.Sprint(value))
	if text == "" {
		return ""
	}
	return text
}

func userLock(userID string) *sync.Mutex {
	if existing, ok := userToolLocks.Load(userID); ok {
		if lock, ok := existing.(*sync.Mutex); ok {
			return lock
		}
	}
	fresh := &sync.Mutex{}
	actual, _ := userToolLocks.LoadOrStore(userID, fresh)
	lock, ok := actual.(*sync.Mutex)
	if !ok {
		return fresh
	}
	return lock
}
