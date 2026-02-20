package user

import (
	"fmt"
	"math"
	"regexp"
	"slices"
	"strings"
)

var visaPositiveRegexes = []*regexp.Regexp{
	regexp.MustCompile(`(?i)\bvisa sponsorship\b`),
	regexp.MustCompile(`(?i)\bsponsor(?:ship|ed|s)?\b`),
	regexp.MustCompile(`(?i)\bh-?1b\b`),
	regexp.MustCompile(`(?i)\be-?3\b`),
	regexp.MustCompile(`(?i)\bopt\b`),
	regexp.MustCompile(`(?i)\bcpt\b`),
	regexp.MustCompile(`(?i)\bgreen card\b`),
}

var visaNegativeRegexes = []*regexp.Regexp{
	regexp.MustCompile(`(?i)\bno visa sponsorship\b`),
	regexp.MustCompile(`(?i)\bwithout visa sponsorship\b`),
	regexp.MustCompile(`(?i)\bdo not sponsor\b`),
	regexp.MustCompile(`(?i)\bunable to sponsor\b`),
	regexp.MustCompile(`(?i)\bmust be authorized to work\b`),
}

func detectDescriptionSignals(description string) (positive bool, negative bool, mentioned []string) {
	text := strings.ToLower(description)
	for _, rx := range visaPositiveRegexes {
		if rx.MatchString(text) {
			positive = true
			break
		}
	}
	for _, rx := range visaNegativeRegexes {
		if rx.MatchString(text) {
			negative = true
			break
		}
	}

	out := []string{}
	add := func(visa string) {
		if !slices.Contains(out, visa) {
			out = append(out, visa)
		}
	}
	if regexp.MustCompile(`(?i)\bh-?1b\b`).MatchString(text) {
		add("h1b")
	}
	if regexp.MustCompile(`(?i)\bh-?1b1\b`).MatchString(text) && regexp.MustCompile(`(?i)\bchile\b`).MatchString(text) {
		add("h1b1_chile")
	}
	if regexp.MustCompile(`(?i)\bh-?1b1\b`).MatchString(text) && regexp.MustCompile(`(?i)\bsingapore\b`).MatchString(text) {
		add("h1b1_singapore")
	}
	if regexp.MustCompile(`(?i)\be-?3\b`).MatchString(text) {
		add("e3_australian")
	}
	if regexp.MustCompile(`(?i)\bgreen card\b`).MatchString(text) || regexp.MustCompile(`(?i)\bperm\b`).MatchString(text) {
		add("green_card")
	}
	return positive, negative, out
}

func hasDesiredMention(mentioned []string, desired []string) bool {
	for _, one := range mentioned {
		for _, target := range desired {
			if one == target {
				return true
			}
		}
	}
	return false
}

func labelsForDesiredVisas(desired []string) []string {
	labels := []string{}
	for _, visa := range desired {
		if label, ok := visaTypeLabels[visa]; ok {
			labels = append(labels, label)
			continue
		}
		labels = append(labels, visa)
	}
	return labels
}

func confidenceScore(
	desiredCount int,
	totalCount int,
	descriptionPositive bool,
	descriptionNegative bool,
	descriptionDesiredMention bool,
) float64 {
	score := 0.0
	if desiredCount > 0 {
		score += 0.65
		score += math.Min(0.2, float64(desiredCount)/50.0)
	}
	if descriptionPositive {
		score += 0.1
	}
	if descriptionDesiredMention {
		score += 0.2
	}
	if descriptionNegative {
		score -= 0.6
	}
	if desiredCount == 0 && totalCount > 0 {
		score += 0.05
	}
	if score < 0 {
		score = 0
	}
	if score > 1 {
		score = 1
	}
	return math.Round(score*100) / 100
}

func visaMatchStrength(desiredCount int, descriptionDesiredMention bool, descriptionPositive bool) string {
	if desiredCount > 0 && descriptionDesiredMention {
		return "strong"
	}
	if desiredCount > 0 {
		return "company_dataset"
	}
	if descriptionDesiredMention && descriptionPositive {
		return "description_signal"
	}
	return "weak"
}

func buildEligibilityReasons(
	desiredCount int,
	descriptionPositive bool,
	descriptionNegative bool,
	descriptionDesiredMention bool,
	desired []string,
) []string {
	reasons := []string{}
	if desiredCount > 0 {
		reasons = append(reasons, fmt.Sprintf("company_has_historical_%s_sponsorship", strings.Join(desired, "_or_")))
	}
	if descriptionDesiredMention {
		reasons = append(reasons, "job_description_mentions_requested_visa")
	}
	if descriptionPositive {
		reasons = append(reasons, "job_description_mentions_sponsorship")
	}
	if descriptionNegative {
		reasons = append(reasons, "job_description_contains_negative_sponsorship_language")
	}
	return reasons
}

func shouldAcceptJob(
	strictness string,
	desiredCount int,
	descriptionPositive bool,
	descriptionNegative bool,
	descriptionDesiredMention bool,
	requireDescriptionSignal bool,
) bool {
	if descriptionNegative {
		return false
	}

	companyEligible := desiredCount > 0
	descriptionEligible := descriptionPositive && descriptionDesiredMention
	if requireDescriptionSignal && !descriptionEligible {
		return false
	}
	if companyEligible || descriptionEligible {
		return true
	}
	if strictness == "balanced" {
		return false
	}
	return false
}
