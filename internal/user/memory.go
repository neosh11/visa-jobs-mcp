package user

import (
	"fmt"
	"slices"
	"strings"
)

func loadUserBlob() map[string]any {
	return loadJSONMap(userBlobPath(), map[string]any{"users": map[string]any{}})
}

func saveUserBlob(data map[string]any) error {
	return saveJSONMap(userBlobPath(), data)
}

func normalizeMemoryLine(raw any) (map[string]any, bool) {
	line := mapOrNil(raw)
	if line == nil {
		return nil, false
	}
	lineID, ok := intFromAny(line["id"])
	if !ok || lineID < 1 {
		return nil, false
	}
	return map[string]any{
		"id":             lineID,
		"text":           stringFromAny(line["text"]),
		"kind":           stringFromAny(line["kind"]),
		"source":         stringFromAny(line["source"]),
		"created_at_utc": stringFromAny(line["created_at_utc"]),
	}, true
}

func normalizeMemoryLines(value any) []map[string]any {
	raw := listOrEmpty(value)
	out := make([]map[string]any, 0, len(raw))
	for _, item := range raw {
		line, ok := normalizeMemoryLine(item)
		if ok {
			out = append(out, line)
		}
	}
	slices.SortFunc(out, func(a, b map[string]any) int {
		ai, _ := intFromAny(a["id"])
		bi, _ := intFromAny(b["id"])
		return ai - bi
	})
	return out
}

func ensureUserBlobEntry(data map[string]any, userID string) map[string]any {
	users := ensureUsersMap(data)
	entry := mapOrNil(users[userID])
	if entry == nil {
		entry = map[string]any{}
		users[userID] = entry
	}

	lines := normalizeMemoryLines(entry["lines"])
	entry["lines"] = lines

	maxID := 0
	for _, line := range lines {
		if id, ok := intFromAny(line["id"]); ok && id > maxID {
			maxID = id
		}
	}
	nextID, ok := intFromAny(entry["next_id"])
	if !ok || nextID < 1 {
		nextID = 1
	}
	if nextID <= maxID {
		nextID = maxID + 1
	}
	entry["next_id"] = nextID
	return entry
}

func getUserBlobEntry(data map[string]any, userID string) map[string]any {
	users := getUsersMap(data)
	entry := mapOrNil(users[userID])
	if entry == nil {
		return nil
	}
	lines := normalizeMemoryLines(entry["lines"])
	entry["lines"] = lines
	return entry
}

func AddUserMemoryLine(args map[string]any) (map[string]any, error) {
	userID := getString(args, "user_id")
	if userID == "" {
		return nil, fmt.Errorf("user_id is required")
	}
	content := getString(args, "content")
	if content == "" {
		return nil, fmt.Errorf("content is required")
	}

	data := loadUserBlob()
	entry := ensureUserBlobEntry(data, userID)
	nextID, _ := intFromAny(entry["next_id"])

	line := map[string]any{
		"id":             nextID,
		"text":           content,
		"kind":           getString(args, "kind"),
		"source":         getString(args, "source"),
		"created_at_utc": utcNowISO(),
	}
	lines := normalizeMemoryLines(entry["lines"])
	lines = append(lines, line)
	entry["lines"] = lines
	entry["next_id"] = nextID + 1
	entry["updated_at_utc"] = line["created_at_utc"]

	if err := saveUserBlob(data); err != nil {
		return nil, err
	}

	return map[string]any{
		"user_id":     userID,
		"added_line":  line,
		"total_lines": len(lines),
		"path":        userBlobPath(),
	}, nil
}

func QueryUserMemoryBlob(args map[string]any) (map[string]any, error) {
	userID := getString(args, "user_id")
	if userID == "" {
		return nil, fmt.Errorf("user_id is required")
	}

	safeLimit := 50
	if limit, hasLimit, err := getOptionalInt(args, "limit"); hasLimit {
		if err != nil {
			return nil, fmt.Errorf("limit must be an integer when provided")
		}
		if limit < 1 {
			limit = 1
		}
		if limit > 200 {
			limit = 200
		}
		safeLimit = limit
	}

	safeOffset := 0
	if offset, hasOffset, err := getOptionalInt(args, "offset"); hasOffset {
		if err != nil {
			return nil, fmt.Errorf("offset must be an integer when provided")
		}
		if offset < 0 {
			offset = 0
		}
		safeOffset = offset
	}

	query := getString(args, "query")
	queryLower := strings.ToLower(query)

	data := loadUserBlob()
	entry := getUserBlobEntry(data, userID)
	if entry == nil {
		return map[string]any{
			"user_id":        userID,
			"query":          query,
			"offset":         safeOffset,
			"limit":          safeLimit,
			"total_lines":    0,
			"total_matches":  0,
			"returned_lines": 0,
			"lines":          []any{},
			"path":           userBlobPath(),
		}, nil
	}

	lines := normalizeMemoryLines(entry["lines"])
	slices.SortFunc(lines, func(a, b map[string]any) int {
		ai, _ := intFromAny(a["id"])
		bi, _ := intFromAny(b["id"])
		return bi - ai
	})

	filtered := make([]map[string]any, 0, len(lines))
	for _, line := range lines {
		if queryLower == "" {
			filtered = append(filtered, line)
			continue
		}
		haystack := strings.ToLower(
			strings.Join([]string{
				stringFromAny(line["text"]),
				stringFromAny(line["kind"]),
				stringFromAny(line["source"]),
			}, " "),
		)
		if strings.Contains(haystack, queryLower) {
			filtered = append(filtered, line)
		}
	}

	totalMatches := len(filtered)
	if safeOffset > totalMatches {
		safeOffset = totalMatches
	}
	pageEnd := safeOffset + safeLimit
	if pageEnd > totalMatches {
		pageEnd = totalMatches
	}
	page := filtered[safeOffset:pageEnd]

	pageAny := make([]any, 0, len(page))
	for _, line := range page {
		pageAny = append(pageAny, line)
	}

	return map[string]any{
		"user_id":        userID,
		"query":          query,
		"offset":         safeOffset,
		"limit":          safeLimit,
		"total_lines":    len(lines),
		"total_matches":  totalMatches,
		"returned_lines": len(page),
		"lines":          pageAny,
		"path":           userBlobPath(),
	}, nil
}

func DeleteUserMemoryLine(args map[string]any) (map[string]any, error) {
	userID := getString(args, "user_id")
	if userID == "" {
		return nil, fmt.Errorf("user_id is required")
	}

	lineID, hasLineID, err := getOptionalInt(args, "line_id")
	if !hasLineID {
		return nil, fmt.Errorf("line_id is required")
	}
	if err != nil {
		return nil, fmt.Errorf("line_id must be an integer")
	}
	if lineID < 1 {
		return nil, fmt.Errorf("line_id must be a positive integer")
	}

	data := loadUserBlob()
	entry := getUserBlobEntry(data, userID)
	if entry == nil {
		return map[string]any{
			"user_id":      userID,
			"line_id":      lineID,
			"deleted":      false,
			"deleted_line": nil,
			"total_lines":  0,
			"path":         userBlobPath(),
		}, nil
	}

	lines := normalizeMemoryLines(entry["lines"])
	remaining := make([]map[string]any, 0, len(lines))
	var deletedLine map[string]any
	for _, line := range lines {
		currentID, _ := intFromAny(line["id"])
		if deletedLine == nil && currentID == lineID {
			deletedLine = line
			continue
		}
		remaining = append(remaining, line)
	}

	if deletedLine == nil {
		return map[string]any{
			"user_id":      userID,
			"line_id":      lineID,
			"deleted":      false,
			"deleted_line": nil,
			"total_lines":  len(lines),
			"path":         userBlobPath(),
		}, nil
	}

	entry["lines"] = remaining
	entry["updated_at_utc"] = utcNowISO()
	if err := saveUserBlob(data); err != nil {
		return nil, err
	}

	return map[string]any{
		"user_id":      userID,
		"line_id":      lineID,
		"deleted":      true,
		"deleted_line": deletedLine,
		"total_lines":  len(remaining),
		"path":         userBlobPath(),
	}, nil
}
