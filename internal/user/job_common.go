package user

import (
	"fmt"
	"regexp"
	"strings"
)

var validJobStages = map[string]struct{}{
	"new":       {},
	"saved":     {},
	"applied":   {},
	"interview": {},
	"offer":     {},
	"rejected":  {},
	"ignored":   {},
}

var companyLegalSuffixes = map[string]struct{}{
	"inc":          {},
	"corp":         {},
	"corporation":  {},
	"co":           {},
	"llc":          {},
	"ltd":          {},
	"lp":           {},
	"plc":          {},
	"pc":           {},
	"holdings":     {},
	"holding":      {},
	"group":        {},
	"technologies": {},
	"technology":   {},
}

var nonAlnumCompanyRegex = regexp.MustCompile(`[^A-Za-z0-9\s]`)

func validateJobStage(stage string) (string, error) {
	clean := strings.ToLower(strings.TrimSpace(stage))
	if _, ok := validJobStages[clean]; !ok {
		return "", fmt.Errorf("stage must be one of [applied ignored interview new offer rejected saved]")
	}
	return clean, nil
}

func normalizeCompanyName(name string) string {
	text := strings.TrimSpace(name)
	if text == "" {
		return ""
	}
	lower := strings.ToLower(text)
	switch lower {
	case "nan", "none", "null", "na", "n/a":
		return ""
	}
	cleaned := nonAlnumCompanyRegex.ReplaceAllString(lower, " ")
	tokens := strings.Fields(cleaned)
	for len(tokens) > 0 {
		last := tokens[len(tokens)-1]
		if _, ok := companyLegalSuffixes[last]; !ok {
			break
		}
		tokens = tokens[:len(tokens)-1]
	}
	return strings.Join(tokens, " ")
}
