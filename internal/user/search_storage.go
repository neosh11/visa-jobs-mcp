package user

import (
	"encoding/json"
	"fmt"
	"slices"
	"strings"
	"sync"
	"time"
)

var searchRunMu sync.Mutex
var searchSessionMu sync.Mutex

func parseISOTime(value any) time.Time {
	text := strings.TrimSpace(fmt.Sprint(value))
	if text == "" {
		return time.Time{}
	}
	t, err := time.Parse(time.RFC3339, text)
	if err != nil {
		return time.Time{}
	}
	return t.UTC()
}

func toISO(t time.Time) string {
	return t.UTC().Truncate(time.Second).Format(time.RFC3339)
}

func futureISO(seconds int) string {
	return toISO(utcNow().Add(time.Duration(seconds) * time.Second))
}

func cloneMap(value map[string]any) map[string]any {
	raw, err := json.Marshal(value)
	if err != nil {
		return map[string]any{}
	}
	var out map[string]any
	if err := json.Unmarshal(raw, &out); err != nil {
		return map[string]any{}
	}
	return out
}

func appendRunEvent(
	run map[string]any,
	phase string,
	detail string,
	progressPercent float64,
	payload map[string]any,
) {
	events := listOrEmpty(run["events"])
	nextEventID := intOrZero(run["next_event_id"])
	event := map[string]any{
		"event_id": nextEventID,
		"at_utc":   utcNowISO(),
		"phase":    phase,
		"detail":   detail,
	}
	if progressPercent >= 0 {
		if progressPercent > 100 {
			progressPercent = 100
		}
		event["progress_percent"] = progressPercent
	}
	if len(payload) > 0 {
		event["payload"] = payload
	}
	events = append(events, event)
	run["events"] = events
	run["next_event_id"] = nextEventID + 1
}

func pruneSearchRunsLocked(store map[string]any) map[string]any {
	runs := mapOrNil(store["runs"])
	if runs == nil {
		store["runs"] = map[string]any{}
		return store
	}

	now := utcNow()
	valid := map[string]any{}
	for runID, raw := range runs {
		run := mapOrNil(raw)
		if run == nil {
			continue
		}
		expiresAt := parseISOTime(run["expires_at_utc"])
		if !expiresAt.IsZero() && !expiresAt.After(now) {
			continue
		}
		valid[runID] = run
	}

	if len(valid) > searchMaxRuns() && searchMaxRuns() > 0 {
		type runPair struct {
			ID   string
			Time time.Time
		}
		pairs := make([]runPair, 0, len(valid))
		for runID, raw := range valid {
			run := mapOrNil(raw)
			updated := parseISOTime(run["updated_at_utc"])
			if updated.IsZero() {
				updated = parseISOTime(run["created_at_utc"])
			}
			pairs = append(pairs, runPair{ID: runID, Time: updated})
		}
		slices.SortFunc(pairs, func(a, b runPair) int {
			if a.Time.Equal(b.Time) {
				return strings.Compare(a.ID, b.ID)
			}
			if a.Time.After(b.Time) {
				return -1
			}
			return 1
		})
		trimmed := map[string]any{}
		for idx, pair := range pairs {
			if idx >= searchMaxRuns() {
				break
			}
			trimmed[pair.ID] = valid[pair.ID]
		}
		valid = trimmed
	}

	store["runs"] = valid
	return store
}

func loadSearchRunsPrunedLocked() map[string]any {
	store := loadSearchRuns()
	return pruneSearchRunsLocked(store)
}

func saveSearchRunsPrunedLocked(store map[string]any) error {
	return saveSearchRuns(pruneSearchRunsLocked(store))
}

func withSearchRunStore(write bool, fn func(store map[string]any) error) error {
	searchRunMu.Lock()
	defer searchRunMu.Unlock()

	store := loadSearchRunsPrunedLocked()
	if err := fn(store); err != nil {
		return err
	}
	if write {
		return saveSearchRunsPrunedLocked(store)
	}
	return nil
}

func loadRunForUser(runID, userID string) (map[string]any, error) {
	var run map[string]any
	err := withSearchRunStore(false, func(store map[string]any) error {
		runs := mapOrNil(store["runs"])
		if runs == nil {
			return fmt.Errorf("unknown run_id '%s'", runID)
		}
		current := mapOrNil(runs[runID])
		if current == nil {
			return fmt.Errorf("unknown run_id '%s'", runID)
		}
		query := mapOrNil(current["query"])
		if query == nil || getString(query, "user_id") != userID {
			return fmt.Errorf("run_id does not belong to this user_id")
		}
		run = cloneMap(current)
		return nil
	})
	if err != nil {
		return nil, err
	}
	return run, nil
}

func loadRunByID(runID string) (map[string]any, error) {
	var run map[string]any
	err := withSearchRunStore(false, func(store map[string]any) error {
		runs := mapOrNil(store["runs"])
		if runs == nil {
			return fmt.Errorf("unknown run_id '%s'", runID)
		}
		current := mapOrNil(runs[runID])
		if current == nil {
			return fmt.Errorf("unknown run_id '%s'", runID)
		}
		run = cloneMap(current)
		return nil
	})
	if err != nil {
		return nil, err
	}
	return run, nil
}

func updateRun(runID string, updater func(run map[string]any) error) error {
	return withSearchRunStore(true, func(store map[string]any) error {
		runs := mapOrNil(store["runs"])
		if runs == nil {
			return fmt.Errorf("search run store is unavailable")
		}
		run := mapOrNil(runs[runID])
		if run == nil {
			return fmt.Errorf("unknown run_id '%s'", runID)
		}
		if err := updater(run); err != nil {
			return err
		}
		run["updated_at_utc"] = utcNowISO()
		runs[runID] = run
		store["runs"] = runs
		return nil
	})
}

func pruneSearchSessionsLocked(store map[string]any) map[string]any {
	sessions := mapOrNil(store["sessions"])
	if sessions == nil {
		store["sessions"] = map[string]any{}
		return store
	}
	now := utcNow()
	valid := map[string]any{}
	for sessionID, raw := range sessions {
		session := mapOrNil(raw)
		if session == nil {
			continue
		}
		expiresAt := parseISOTime(session["expires_at_utc"])
		if !expiresAt.IsZero() && !expiresAt.After(now) {
			continue
		}
		valid[sessionID] = session
	}

	if maxSessions := searchMaxSessions(); maxSessions > 0 && len(valid) > maxSessions {
		type sessionPair struct {
			ID   string
			Time time.Time
		}
		pairs := make([]sessionPair, 0, len(valid))
		for sessionID, raw := range valid {
			session := mapOrNil(raw)
			updated := parseISOTime(session["updated_at_utc"])
			if updated.IsZero() {
				updated = parseISOTime(session["created_at_utc"])
			}
			pairs = append(pairs, sessionPair{ID: sessionID, Time: updated})
		}
		slices.SortFunc(pairs, func(a, b sessionPair) int {
			if a.Time.Equal(b.Time) {
				return strings.Compare(a.ID, b.ID)
			}
			if a.Time.After(b.Time) {
				return -1
			}
			return 1
		})
		trimmed := map[string]any{}
		for idx, pair := range pairs {
			if idx >= maxSessions {
				break
			}
			trimmed[pair.ID] = valid[pair.ID]
		}
		valid = trimmed
	}
	store["sessions"] = valid
	return store
}

func enforceUserSessionLimitLocked(store map[string]any, userID string) {
	maxUserSessions := searchMaxSessionsPerUser()
	if maxUserSessions <= 0 {
		return
	}
	sessions := mapOrNil(store["sessions"])
	if sessions == nil {
		return
	}
	type sessionPair struct {
		ID   string
		Time time.Time
	}
	userSessions := []sessionPair{}
	for sessionID, raw := range sessions {
		session := mapOrNil(raw)
		if session == nil {
			continue
		}
		query := mapOrNil(session["query"])
		if query == nil || getString(query, "user_id") != userID {
			continue
		}
		updated := parseISOTime(session["updated_at_utc"])
		if updated.IsZero() {
			updated = parseISOTime(session["created_at_utc"])
		}
		userSessions = append(userSessions, sessionPair{ID: sessionID, Time: updated})
	}
	if len(userSessions) <= maxUserSessions {
		return
	}
	slices.SortFunc(userSessions, func(a, b sessionPair) int {
		if a.Time.Equal(b.Time) {
			return strings.Compare(a.ID, b.ID)
		}
		if a.Time.After(b.Time) {
			return -1
		}
		return 1
	})
	keep := map[string]struct{}{}
	for idx, item := range userSessions {
		if idx >= maxUserSessions {
			break
		}
		keep[item.ID] = struct{}{}
	}
	for _, item := range userSessions {
		if _, ok := keep[item.ID]; ok {
			continue
		}
		delete(sessions, item.ID)
	}
	store["sessions"] = sessions
}

func loadSearchSessionsPruned() map[string]any {
	store := loadSearchSessions()
	return pruneSearchSessionsLocked(store)
}

func saveSearchSessionsPruned(store map[string]any) error {
	return saveSearchSessions(pruneSearchSessionsLocked(store))
}

func withSearchSessionStore(write bool, fn func(store map[string]any) error) error {
	searchSessionMu.Lock()
	defer searchSessionMu.Unlock()

	store := loadSearchSessionsPruned()
	if err := fn(store); err != nil {
		return err
	}
	if write {
		return saveSearchSessionsPruned(store)
	}
	return nil
}
