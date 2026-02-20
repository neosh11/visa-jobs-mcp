package user

import (
	"fmt"
	"strings"
)

func resolveJobReference(args map[string]any, userID string) (map[string]any, error) {
	jobURL := getString(args, "job_url")
	resultID := getString(args, "result_id")
	sessionID := getString(args, "session_id")

	if jobURL != "" {
		return map[string]any{
			"job_url":                  jobURL,
			"title":                    "",
			"company":                  "",
			"location":                 "",
			"site":                     "",
			"result_id":                resultID,
			"source_session_id":        sessionID,
			"employer_contacts":        []any{},
			"visa_counts":              map[string]any{},
			"visas_sponsored":          []any{},
			"eligibility_reasons":      []any{},
			"confidence_score":         nil,
			"confidence_model_version": nil,
		}, nil
	}

	if resultID == "" {
		return nil, fmt.Errorf("job_url or result_id is required")
	}
	if strings.Contains(resultID, ":") && sessionID == "" {
		sessionID = strings.TrimSpace(strings.SplitN(resultID, ":", 2)[0])
	}
	if sessionID == "" {
		return nil, fmt.Errorf("session_id is required when using result_id without a session prefix")
	}

	store := loadSearchSessions()
	sessions := mapOrNil(store["sessions"])
	record := mapOrNil(sessions[sessionID])
	if record == nil {
		return nil, fmt.Errorf("unknown session_id '%s'", sessionID)
	}
	query := mapOrNil(record["query"])
	if query == nil || getString(query, "user_id") != strings.TrimSpace(userID) {
		return nil, fmt.Errorf("session_id does not belong to this user_id")
	}

	resultIndex := mapOrNil(record["result_id_index"])
	if resultIndex == nil {
		acceptedJobs := []map[string]any{}
		for idx, raw := range listOrEmpty(record["accepted_jobs"]) {
			item := mapOrNil(raw)
			if item == nil {
				continue
			}
			normalized := map[string]any{
				"result_id":                getString(item, "result_id"),
				"job_url":                  getString(item, "job_url"),
				"title":                    getString(item, "title"),
				"company":                  getString(item, "company"),
				"location":                 getString(item, "location"),
				"site":                     getString(item, "site"),
				"employer_contacts":        listOrEmpty(item["employer_contacts"]),
				"visa_counts":              asMap(item["visa_counts"]),
				"visas_sponsored":          listOrEmpty(item["visas_sponsored"]),
				"visa_match_strength":      getString(item, "visa_match_strength"),
				"eligibility_reasons":      listOrEmpty(item["eligibility_reasons"]),
				"confidence_score":         item["confidence_score"],
				"confidence_model_version": item["confidence_model_version"],
			}
			if normalized["result_id"] == "" {
				normalized["result_id"] = fmt.Sprintf("%s:%d", sessionID, idx+1)
			}
			acceptedJobs = append(acceptedJobs, normalized)
		}
		resultIndex = map[string]any{}
		acceptedOut := make([]any, 0, len(acceptedJobs))
		for _, row := range acceptedJobs {
			rid := getString(row, "result_id")
			if rid != "" {
				resultIndex[rid] = row
			}
			acceptedOut = append(acceptedOut, row)
		}
		record["accepted_jobs"] = acceptedOut
		record["result_id_index"] = resultIndex
		sessions[sessionID] = record
		store["sessions"] = sessions
		_ = saveSearchSessions(store)
	}

	resolved := mapOrNil(resultIndex[resultID])
	if resolved == nil && !strings.Contains(resultID, ":") {
		resolved = mapOrNil(resultIndex[sessionID+":"+resultID])
	}
	if resolved == nil {
		return nil, fmt.Errorf("unknown result_id for this session. Pass a result_id returned by get_visa_job_search_results")
	}
	if getString(resolved, "job_url") == "" {
		return nil, fmt.Errorf("resolved result_id does not have a job_url. Save/ignore requires a job URL")
	}

	out := cloneOrEmptyMap(resolved)
	out["source_session_id"] = sessionID
	return out, nil
}
