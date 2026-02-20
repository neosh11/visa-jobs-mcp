package user

import (
	"fmt"
	"strings"
)

var visaTypeLabels = map[string]string{
	"h1b":            "H-1B",
	"h1b1_chile":     "H-1B1 Chile",
	"h1b1_singapore": "H-1B1 Singapore",
	"e3_australian":  "E-3 Australian",
	"green_card":     "Green Card",
}

var relatedTitleHints = map[string][]string{
	"software engineer": {
		"Software Developer",
		"Backend Engineer",
		"Full Stack Engineer",
		"Platform Engineer",
		"Site Reliability Engineer",
		"Application Engineer",
		"Machine Learning Engineer",
	},
	"data engineer": {
		"Data Platform Engineer",
		"Analytics Engineer",
		"ETL Engineer",
		"Big Data Engineer",
		"Data Infrastructure Engineer",
	},
	"product manager": {
		"Technical Product Manager",
		"Program Manager",
		"Product Owner",
		"Growth Product Manager",
		"Platform Product Manager",
	},
}

func findRelatedTitlesInternal(jobTitle string, limit int) []string {
	base := strings.TrimSpace(jobTitle)
	if base == "" {
		return []string{}
	}
	normalized := strings.ToLower(base)
	related := []string{}

	for key, values := range relatedTitleHints {
		if strings.Contains(normalized, key) || strings.Contains(key, normalized) {
			related = append(related, values...)
			break
		}
	}
	if len(related) == 0 {
		switch {
		case strings.Contains(normalized, "engineer"):
			related = append(related,
				strings.ReplaceAll(base, "Engineer", "Developer"),
				strings.ReplaceAll(base, "engineer", "developer"),
				strings.ReplaceAll(base, "Engineer", "Platform Engineer"),
			)
		case strings.Contains(normalized, "developer"):
			related = append(related,
				strings.ReplaceAll(base, "Developer", "Engineer"),
				strings.ReplaceAll(base, "developer", "engineer"),
				"Software Engineer",
			)
		case strings.Contains(normalized, "architect"):
			related = append(related,
				strings.ReplaceAll(base, "Architect", "Engineer"),
				strings.ReplaceAll(base, "architect", "engineer"),
				"Senior "+base,
				"Lead "+base,
			)
		default:
			related = append(related,
				"Senior "+base,
				"Lead "+base,
				"Principal "+base,
			)
		}
	}

	out := []string{}
	seen := map[string]struct{}{}
	for _, item := range related {
		clean := strings.TrimSpace(item)
		if clean == "" {
			continue
		}
		key := strings.ToLower(clean)
		if _, ok := seen[key]; ok {
			continue
		}
		seen[key] = struct{}{}
		out = append(out, clean)
		if len(out) >= limit {
			break
		}
	}
	return out
}

func FindRelatedTitles(args map[string]any) (map[string]any, error) {
	title := getString(args, "job_title")
	if title == "" {
		return nil, fmt.Errorf("job_title is required")
	}
	limit := 8
	if parsed, has, err := getOptionalInt(args, "limit"); has {
		if err != nil {
			return nil, fmt.Errorf("limit must be an integer when provided")
		}
		if parsed < 1 {
			parsed = 1
		}
		if parsed > 20 {
			parsed = 20
		}
		limit = parsed
	}
	related := findRelatedTitlesInternal(title, limit)
	return map[string]any{
		"job_title":      title,
		"related_titles": related,
		"count":          len(related),
	}, nil
}

func getFirstContact(resolved map[string]any) map[string]any {
	contacts := listOrEmpty(resolved["employer_contacts"])
	if len(contacts) == 0 {
		return map[string]any{}
	}
	first := mapOrNil(contacts[0])
	if first == nil {
		return map[string]any{}
	}
	return first
}

func GetBestContactStrategy(args map[string]any) (map[string]any, error) {
	userID := getString(args, "user_id")
	if userID == "" {
		return nil, fmt.Errorf("user_id is required")
	}
	resolved, err := resolveJobReference(args, userID)
	if err != nil {
		return nil, err
	}

	primary := getFirstContact(resolved)
	primaryName := getString(primary, "name")
	primaryTitle := getString(primary, "title")
	primaryEmail := getString(primary, "email")
	primaryPhone := getString(primary, "phone")

	channel := "application_plus_linkedin"
	strategy := []string{
		"Submit the application immediately using the job URL.",
		"Find the recruiter/hiring manager on LinkedIn and send a short intro note.",
		"Track this role in saved jobs and follow up in 3-5 days.",
	}
	if primaryEmail != "" {
		channel = "email"
		strategy = []string{
			"Send a short intro email referencing role fit and visa type.",
			"Attach or link a targeted resume with matching skills.",
			"Follow up once in 48 hours if no response.",
		}
	} else if primaryPhone != "" {
		channel = "phone"
		strategy = []string{
			"Call during business hours and ask for recruiter/hiring manager routing.",
			"Leave a concise voicemail with callback and role context.",
			"Follow with a short email or LinkedIn note if available.",
		}
	}

	return map[string]any{
		"user_id": userID,
		"job_reference": map[string]any{
			"result_id":         resolved["result_id"],
			"source_session_id": resolved["source_session_id"],
			"job_url":           resolved["job_url"],
			"title":             resolved["title"],
			"company":           resolved["company"],
		},
		"recommended_channel": channel,
		"primary_contact": map[string]any{
			"name":  primaryName,
			"title": primaryTitle,
			"email": primaryEmail,
			"phone": primaryPhone,
		},
		"strategy_steps":       strategy,
		"non_legal_disclaimer": "Guidance is informational only and not legal advice.",
	}, nil
}

func preferredVisaLabelForUser(userID string) string {
	prefs, err := loadPrefs()
	if err != nil {
		return "work visa sponsorship"
	}
	userPrefs := asMap(prefs[userID])
	stored := userPrefs["preferred_visa_types"]
	for _, raw := range listOrEmpty(stored) {
		value := strings.TrimSpace(fmt.Sprint(raw))
		if value == "" {
			continue
		}
		normalized, err := normalizeVisaType(value)
		if err != nil {
			value = strings.ToLower(value)
			if label, ok := visaTypeLabels[value]; ok {
				return label
			}
			return value
		}
		if label, ok := visaTypeLabels[normalized]; ok {
			return label
		}
		return normalized
	}
	return "work visa sponsorship"
}

func GenerateOutreachMessage(args map[string]any) (map[string]any, error) {
	userID := getString(args, "user_id")
	if userID == "" {
		return nil, fmt.Errorf("user_id is required")
	}
	resolved, err := resolveJobReference(args, userID)
	if err != nil {
		return nil, err
	}

	visaLabel := getString(args, "visa_type")
	if visaLabel == "" {
		visaLabel = preferredVisaLabelForUser(userID)
	}
	toName := getString(args, "recipient_name")
	if toName == "" {
		toName = "Hiring Team"
	}
	toTitle := getString(args, "recipient_title")
	role := getString(resolved, "title")
	if role == "" {
		role = "this role"
	}
	company := getString(resolved, "company")
	if company == "" {
		company = "your team"
	}
	url := getString(resolved, "job_url")

	greeting := "Hi " + toName + ","
	intro := "I’m reaching out about " + role + " at " + company + " (" + url + ")."
	fit := "I align strongly with the role requirements and can contribute quickly."
	visaLine := "I am specifically looking for opportunities that support " + visaLabel + "."
	ask := "If this role is still open, I’d appreciate the chance to share my background and discuss fit."
	tone := getString(args, "tone")
	if tone == "" {
		tone = "professional"
	}
	if strings.ToLower(tone) == "urgent" {
		ask = "Given timing constraints on my side, a quick conversation would be very helpful if sponsorship is possible."
	}
	body := strings.Join([]string{
		greeting,
		"",
		intro,
		fit,
		visaLine,
		ask,
		"",
		"Thanks for your time,",
		"[Your Name]",
	}, "\n")

	return map[string]any{
		"user_id": userID,
		"job_reference": map[string]any{
			"result_id":         resolved["result_id"],
			"source_session_id": resolved["source_session_id"],
			"job_url":           url,
			"title":             role,
			"company":           company,
		},
		"recipient": map[string]any{
			"name":  toName,
			"title": toTitle,
		},
		"tone":                 tone,
		"subject":              "Interest in " + role + " (" + visaLabel + ")",
		"message":              body,
		"non_legal_disclaimer": "Template guidance only; not legal advice.",
	}, nil
}

func RefreshCompanyDatasetCache(args map[string]any) (map[string]any, error) {
	datasetPath := datasetPathOrDefault(getString(args, "dataset_path"))
	clearDatasetCache(datasetPath)
	dataset, err := loadCompanyDataset(datasetPath)
	if err != nil {
		return nil, err
	}

	return map[string]any{
		"dataset_path":                  datasetPath,
		"rows":                          dataset.Rows,
		"distinct_normalized_companies": len(dataset.ByNormalizedCompany),
		"cache_refreshed":               true,
	}, nil
}
