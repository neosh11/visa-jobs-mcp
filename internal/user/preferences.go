package user

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"slices"
	"strconv"
	"strings"
	"time"
)

const (
	defaultUserPrefsPath = "data/config/user_preferences.json"
)

var visaTypeAliases = map[string]string{
	"h1b":                  "h1b",
	"h-1b":                 "h1b",
	"h1b1_chile":           "h1b1_chile",
	"h-1b1 chile":          "h1b1_chile",
	"h1b1 chile":           "h1b1_chile",
	"h1b1_chile/singapore": "h1b1_chile",
	"h1b1_singapore":       "h1b1_singapore",
	"h-1b1 singapore":      "h1b1_singapore",
	"h1b1 singapore":       "h1b1_singapore",
	"e3":                   "e3_australian",
	"e-3":                  "e3_australian",
	"e3_australian":        "e3_australian",
	"e-3 australian":       "e3_australian",
	"green_card":           "green_card",
	"green card":           "green_card",
	"perm":                 "green_card",
}

var supportedWorkModes = map[string]struct{}{
	"remote": {},
	"hybrid": {},
	"onsite": {},
}

func prefsPath() string {
	if value := strings.TrimSpace(os.Getenv("VISA_USER_PREFS_PATH")); value != "" {
		return value
	}
	return defaultUserPrefsPath
}

func loadPrefs() (map[string]map[string]any, error) {
	path := prefsPath()
	raw, err := os.ReadFile(path)
	if err != nil {
		if os.IsNotExist(err) {
			return map[string]map[string]any{}, nil
		}
		return nil, err
	}
	var parsed map[string]map[string]any
	if err := json.Unmarshal(raw, &parsed); err != nil {
		return map[string]map[string]any{}, nil
	}
	if parsed == nil {
		return map[string]map[string]any{}, nil
	}
	return parsed, nil
}

func savePrefs(data map[string]map[string]any) error {
	path := prefsPath()
	if err := os.MkdirAll(filepath.Dir(path), 0o755); err != nil {
		return err
	}
	raw, err := json.MarshalIndent(data, "", "  ")
	if err != nil {
		return err
	}
	return os.WriteFile(path, raw, 0o644)
}

func getString(args map[string]any, key string) string {
	value, ok := args[key]
	if !ok || value == nil {
		return ""
	}
	switch typed := value.(type) {
	case string:
		return strings.TrimSpace(typed)
	default:
		return strings.TrimSpace(fmt.Sprint(typed))
	}
}

func getStringList(args map[string]any, key string) []string {
	value, ok := args[key]
	if !ok || value == nil {
		return nil
	}
	switch typed := value.(type) {
	case []any:
		out := make([]string, 0, len(typed))
		for _, item := range typed {
			text := strings.TrimSpace(fmt.Sprint(item))
			if text != "" {
				out = append(out, text)
			}
		}
		return out
	case []string:
		out := make([]string, 0, len(typed))
		for _, item := range typed {
			text := strings.TrimSpace(item)
			if text != "" {
				out = append(out, text)
			}
		}
		return out
	case string:
		text := strings.TrimSpace(typed)
		if text == "" {
			return nil
		}
		return []string{text}
	default:
		return nil
	}
}

func hasKey(args map[string]any, key string) bool {
	_, ok := args[key]
	return ok
}

func getOptionalInt(args map[string]any, key string) (int, bool, error) {
	value, ok := args[key]
	if !ok || value == nil {
		return 0, false, nil
	}
	switch typed := value.(type) {
	case float64:
		return int(typed), true, nil
	case int:
		return typed, true, nil
	case string:
		parsed, err := strconv.Atoi(strings.TrimSpace(typed))
		if err != nil {
			return 0, true, err
		}
		return parsed, true, nil
	default:
		return 0, true, fmt.Errorf("%s must be an integer", key)
	}
}

func getOptionalBool(args map[string]any, key string) (bool, bool, error) {
	value, ok := args[key]
	if !ok || value == nil {
		return false, false, nil
	}
	switch typed := value.(type) {
	case bool:
		return typed, true, nil
	case string:
		parsed, err := strconv.ParseBool(strings.TrimSpace(typed))
		if err != nil {
			return false, true, err
		}
		return parsed, true, nil
	default:
		return false, true, fmt.Errorf("%s must be a boolean", key)
	}
}

func normalizeVisaType(value string) (string, error) {
	key := strings.ToLower(strings.TrimSpace(value))
	normalized, ok := visaTypeAliases[key]
	if !ok {
		return "", fmt.Errorf("unsupported visa type '%s'", value)
	}
	return normalized, nil
}

func normalizeWorkMode(value string) (string, error) {
	mode := strings.ToLower(strings.TrimSpace(value))
	if _, ok := supportedWorkModes[mode]; !ok {
		return "", fmt.Errorf("unsupported work mode '%s'", value)
	}
	return mode, nil
}

func utcNowISO() string {
	return time.Now().UTC().Truncate(time.Second).Format(time.RFC3339)
}

func asMap(value any) map[string]any {
	if typed, ok := value.(map[string]any); ok {
		return typed
	}
	return map[string]any{}
}

func SetUserPreferences(args map[string]any) (map[string]any, error) {
	uid := getString(args, "user_id")
	if uid == "" {
		return nil, fmt.Errorf("user_id is required")
	}
	visaTypes := getStringList(args, "preferred_visa_types")
	normalizedSet := map[string]struct{}{}
	for _, value := range visaTypes {
		normalized, err := normalizeVisaType(value)
		if err != nil {
			return nil, err
		}
		normalizedSet[normalized] = struct{}{}
	}
	normalizedTypes := make([]string, 0, len(normalizedSet))
	for value := range normalizedSet {
		normalizedTypes = append(normalizedTypes, value)
	}
	slices.Sort(normalizedTypes)

	prefs, err := loadPrefs()
	if err != nil {
		return nil, err
	}
	user := prefs[uid]
	if user == nil {
		user = map[string]any{}
	}
	user["preferred_visa_types"] = normalizedTypes
	prefs[uid] = user
	if err := savePrefs(prefs); err != nil {
		return nil, err
	}

	return map[string]any{
		"user_id":     uid,
		"preferences": user,
		"path":        prefsPath(),
	}, nil
}

func SetUserConstraints(args map[string]any) (map[string]any, error) {
	uid := getString(args, "user_id")
	if uid == "" {
		return nil, fmt.Errorf("user_id is required")
	}

	prefs, err := loadPrefs()
	if err != nil {
		return nil, err
	}
	user := prefs[uid]
	if user == nil {
		user = map[string]any{}
	}

	constraints := asMap(user["constraints"])

	if parsedDays, hasDays, err := getOptionalInt(args, "days_remaining"); hasDays {
		if err != nil {
			return nil, fmt.Errorf("days_remaining must be an integer when provided")
		}
		if parsedDays < 0 {
			return nil, fmt.Errorf("days_remaining must be >= 0")
		}
		constraints["days_remaining"] = parsedDays
	}

	if hasKey(args, "work_modes") {
		modes := getStringList(args, "work_modes")
		normalizedSet := map[string]struct{}{}
		for _, mode := range modes {
			normalized, err := normalizeWorkMode(mode)
			if err != nil {
				return nil, err
			}
			normalizedSet[normalized] = struct{}{}
		}
		normalizedModes := make([]string, 0, len(normalizedSet))
		for mode := range normalizedSet {
			normalizedModes = append(normalizedModes, mode)
		}
		slices.Sort(normalizedModes)
		constraints["work_modes"] = normalizedModes
	}

	if relocate, hasRelocate, err := getOptionalBool(args, "willing_to_relocate"); hasRelocate {
		if err != nil {
			return nil, fmt.Errorf("willing_to_relocate must be a boolean when provided")
		}
		constraints["willing_to_relocate"] = relocate
	}

	constraints["updated_at_utc"] = utcNowISO()
	user["constraints"] = constraints
	prefs[uid] = user
	if err := savePrefs(prefs); err != nil {
		return nil, err
	}

	return map[string]any{
		"user_id":     uid,
		"constraints": constraints,
		"path":        prefsPath(),
	}, nil
}

func GetUserPreferences(args map[string]any) (map[string]any, error) {
	uid := getString(args, "user_id")
	if uid == "" {
		return nil, fmt.Errorf("user_id is required")
	}
	prefs, err := loadPrefs()
	if err != nil {
		return nil, err
	}
	user := prefs[uid]
	if user == nil {
		user = map[string]any{}
	}
	return map[string]any{
		"user_id":     uid,
		"preferences": user,
		"path":        prefsPath(),
	}, nil
}

func getRequiredUserVisaTypes(userID string) ([]string, error) {
	uid := strings.TrimSpace(userID)
	if uid == "" {
		return nil, fmt.Errorf("user_id is required; set visa preferences first using set_user_preferences")
	}
	prefs, err := loadPrefs()
	if err != nil {
		return nil, err
	}
	user := prefs[uid]
	if user == nil {
		return nil, fmt.Errorf("no saved preferences for user_id='%s'; set visa preferences first using set_user_preferences", uid)
	}
	rawTypes := getStringList(user, "preferred_visa_types")
	if len(rawTypes) == 0 {
		return nil, fmt.Errorf("user_id='%s' has no preferred_visa_types; set visa preferences first using set_user_preferences", uid)
	}
	normalizedSet := map[string]struct{}{}
	for _, raw := range rawTypes {
		normalized, err := normalizeVisaType(raw)
		if err != nil {
			return nil, err
		}
		normalizedSet[normalized] = struct{}{}
	}
	normalized := make([]string, 0, len(normalizedSet))
	for key := range normalizedSet {
		normalized = append(normalized, key)
	}
	slices.Sort(normalized)
	return normalized, nil
}
