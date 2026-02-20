package user

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"strconv"
	"strings"
)

func userBlobPath() string {
	return envOrDefault("VISA_USER_BLOB_PATH", defaultUserBlobPath)
}

func savedJobsPath() string {
	return envOrDefault("VISA_SAVED_JOBS_PATH", defaultSavedJobsPath)
}

func ignoredJobsPath() string {
	return envOrDefault("VISA_IGNORED_JOBS_PATH", defaultIgnoredJobsPath)
}

func ignoredCompaniesPath() string {
	return envOrDefault("VISA_IGNORED_COMPANIES_PATH", defaultIgnoredCompaniesPath)
}

func searchSessionsPath() string {
	return envOrDefault("VISA_SEARCH_SESSION_PATH", defaultSearchSessionsPath)
}

func searchRunsPath() string {
	return envOrDefault("VISA_SEARCH_RUNS_PATH", defaultSearchRunsPath)
}

func jobDBPath() string {
	return envOrDefault("VISA_JOB_DB_PATH", defaultJobDBPath)
}

func loadJSONMap(path string, fallback map[string]any) map[string]any {
	raw, err := os.ReadFile(path)
	if err != nil {
		if os.IsNotExist(err) {
			return cloneOrEmptyMap(fallback)
		}
		return cloneOrEmptyMap(fallback)
	}
	var parsed map[string]any
	if err := json.Unmarshal(raw, &parsed); err != nil {
		return cloneOrEmptyMap(fallback)
	}
	if parsed == nil {
		return cloneOrEmptyMap(fallback)
	}
	return parsed
}

func saveJSONMap(path string, data map[string]any) error {
	if err := os.MkdirAll(filepath.Dir(path), 0o755); err != nil {
		return err
	}
	raw, err := json.MarshalIndent(data, "", "  ")
	if err != nil {
		return err
	}
	return os.WriteFile(path, raw, 0o644)
}

func cloneOrEmptyMap(value map[string]any) map[string]any {
	if value == nil {
		return map[string]any{}
	}
	raw, err := json.Marshal(value)
	if err != nil {
		return map[string]any{}
	}
	var out map[string]any
	if err := json.Unmarshal(raw, &out); err != nil {
		return map[string]any{}
	}
	if out == nil {
		return map[string]any{}
	}
	return out
}

func mapOrNil(value any) map[string]any {
	if typed, ok := value.(map[string]any); ok {
		return typed
	}
	return nil
}

func listOrEmpty(value any) []any {
	switch typed := value.(type) {
	case []any:
		return typed
	case []map[string]any:
		out := make([]any, 0, len(typed))
		for _, item := range typed {
			out = append(out, item)
		}
		return out
	case []string:
		out := make([]any, 0, len(typed))
		for _, item := range typed {
			out = append(out, item)
		}
		return out
	}
	return []any{}
}

func intFromAny(value any) (int, bool) {
	switch typed := value.(type) {
	case int:
		return typed, true
	case int64:
		return int(typed), true
	case float64:
		return int(typed), true
	case json.Number:
		n, err := typed.Int64()
		if err != nil {
			return 0, false
		}
		return int(n), true
	case string:
		parsed, err := strconv.Atoi(strings.TrimSpace(typed))
		if err != nil {
			return 0, false
		}
		return parsed, true
	default:
		return 0, false
	}
}

func boolFromAny(value any) (bool, bool) {
	switch typed := value.(type) {
	case bool:
		return typed, true
	case string:
		parsed, err := strconv.ParseBool(strings.TrimSpace(typed))
		if err != nil {
			return false, false
		}
		return parsed, true
	default:
		return false, false
	}
}

func stringFromAny(value any) string {
	switch typed := value.(type) {
	case string:
		return strings.TrimSpace(typed)
	default:
		return strings.TrimSpace(fmt.Sprint(typed))
	}
}

func ensureUsersMap(data map[string]any) map[string]any {
	users := mapOrNil(data["users"])
	if users == nil {
		users = map[string]any{}
		data["users"] = users
	}
	return users
}

func getUsersMap(data map[string]any) map[string]any {
	users := mapOrNil(data["users"])
	if users == nil {
		return map[string]any{}
	}
	return users
}
