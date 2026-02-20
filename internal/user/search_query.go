package user

import (
	"errors"
	"fmt"
	"slices"
	"strings"
	"time"
	"unicode"
)

func executeSearchQuery(
	query searchQuery,
	onProgress func(phase, detail string, progress float64, payload map[string]any),
	isCancelled func() bool,
) (map[string]any, map[string]any, string, error) {
	queryMode := searchModeOrDefault(query.SearchMode)
	desiredVisaTypes, err := getOptionalUserVisaTypes(query.UserID)
	if err != nil {
		return nil, nil, "", err
	}
	applyVisaFiltering := queryMode == searchModeVisa && len(desiredVisaTypes) > 0
	if !applyVisaFiltering {
		desiredVisaTypes = []string{}
	}

	onProgress("dataset", "Loading sponsor dataset.", 5, nil)
	dataset := companyDataset{Rows: 0, ByNormalizedCompany: map[string]companyDatasetRecord{}}
	datasetPath := datasetPathOrDefault(query.DatasetPath)
	dataset, err = loadCompanyDataset(datasetPath)
	datasetLoadWarning := ""
	if err != nil {
		dataset = companyDataset{Rows: 0, ByNormalizedCompany: map[string]companyDatasetRecord{}}
		datasetLoadWarning = err.Error()
		onProgress("dataset", "Dataset unavailable; continuing with live listing signals only.", 8, map[string]any{
			"warning": datasetLoadWarning,
		})
	}
	freshness := datasetFreshness(datasetPath, envOrDefault("VISA_DOL_MANIFEST_PATH", defaultManifestPath))
	ignoredJobs := ignoredJobURLSet(query.UserID)
	ignoredCompanies := ignoredCompanySet(query.UserID)

	requiredAccepted := query.ResultsWanted
	if query.Offset+query.MaxReturned > requiredAccepted {
		requiredAccepted = query.Offset + query.MaxReturned
	}
	if requiredAccepted < 1 {
		requiredAccepted = 1
	}
	rawScanTarget := requiredAccepted * query.ScanMultiplier
	if rawScanTarget < requiredAccepted {
		rawScanTarget = requiredAccepted
	}
	if rawScanTarget > query.MaxScanResults {
		rawScanTarget = query.MaxScanResults
	}

	client, err := newSiteClient(query.Site)
	if err != nil {
		return nil, nil, "", err
	}
	rawJobs := []linkedInJob{}
	seenURLs := map[string]struct{}{}
	start := 0
	const maxLinkedInStart = 1000
	scanExhausted := false
	stats := searchExecutionStats{}
	onProgress("scrape", "Scanning LinkedIn listings.", 15, map[string]any{"scan_target": rawScanTarget})
	for len(rawJobs) < rawScanTarget && start <= maxLinkedInStart {
		if isCancelled() {
			return nil, nil, "", errSearchRunCancelled
		}
		pageJobs, err := client.FetchSearchPage(linkedInSearchQuery{
			JobTitle: query.JobTitle,
			Location: query.Location,
			HoursOld: query.HoursOld,
			Start:    start,
		}, isCancelled)
		if err != nil {
			return nil, nil, "", err
		}
		if len(pageJobs) == 0 {
			scanExhausted = true
			break
		}
		added := 0
		for _, job := range pageJobs {
			key := strings.ToLower(strings.TrimSpace(job.JobURL))
			if key == "" {
				continue
			}
			if _, exists := seenURLs[key]; exists {
				continue
			}
			seenURLs[key] = struct{}{}
			rawJobs = append(rawJobs, job)
			added++
			if len(rawJobs) >= rawScanTarget {
				break
			}
		}
		if added == 0 {
			scanExhausted = true
			break
		}
		start += len(pageJobs)
		progress := 15.0 + (60.0 * float64(len(rawJobs)) / float64(max(1, rawScanTarget)))
		onProgress("scrape", "Collected LinkedIn pages.", progress, map[string]any{
			"raw_jobs_scanned": len(rawJobs),
		})
	}
	if len(rawJobs) < rawScanTarget {
		scanExhausted = true
	}

	filterDetail := "Evaluating visa relevance."
	if !applyVisaFiltering {
		filterDetail = "Evaluating role relevance."
	}
	onProgress("filter", filterDetail, 76, map[string]any{"raw_jobs_scanned": len(rawJobs)})
	accepted := []map[string]any{}
	descriptionFetches := 0
	descriptionFetchLimit := maxDescriptionFetches()
	descriptionDeadline := time.Now().Add(time.Duration(descriptionBudgetSeconds()) * time.Second)
	descriptionBudgetHit := false
	for idx, raw := range rawJobs {
		if isCancelled() {
			return nil, nil, "", errSearchRunCancelled
		}
		stats.RawJobsScanned++
		jobURLKey := strings.ToLower(strings.TrimSpace(raw.JobURL))
		if _, ignored := ignoredJobs[jobURLKey]; ignored {
			stats.IgnoredJobsSkipped++
			continue
		}

		normalizedCompany := normalizeCompanyName(raw.Company)
		if normalizedCompany != "" {
			if _, ignored := ignoredCompanies[normalizedCompany]; ignored {
				stats.IgnoredCompaniesSkipped++
				continue
			}
		}

		record, hasCompany := dataset.ByNormalizedCompany[normalizedCompany]
		desiredCount := 0
		totalCount := 0
		visaCounts := map[string]int{
			"h1b":            0,
			"h1b1_chile":     0,
			"h1b1_singapore": 0,
			"e3_australian":  0,
			"green_card":     0,
			"total_visas":    0,
		}
		contacts := []map[string]any{}
		if hasCompany {
			stats.CompanyMatches++
			desiredCount = desiredVisaCount(record, desiredVisaTypes)
			totalCount = record.TotalVisas
			visaCounts = visaCountsFromRecord(record)
			contacts = record.EmployerContacts
		}

		descriptionText := ""
		fetchedDescription := false
		jobType := raw.JobType
		jobLevel := raw.JobLevel
		companyIndustry := raw.CompanyIndustry
		jobFunction := raw.JobFunction
		jobURLDirect := raw.JobURLDirect
		isRemote := raw.IsRemote
		needsDescription := query.RequireDescriptionSignal || (applyVisaFiltering && desiredCount == 0)
		if needsDescription {
			canFetchDescription := descriptionFetches < descriptionFetchLimit && time.Now().Before(descriptionDeadline)
			if canFetchDescription {
				if descriptionFetches%5 == 0 {
					detail := "Checking job descriptions for relevance signals."
					if applyVisaFiltering {
						detail = "Checking job descriptions for visa signals."
					}
					onProgress("filter", detail, 80, map[string]any{
						"description_fetches":     descriptionFetches,
						"description_fetch_limit": descriptionFetchLimit,
						"accepted_jobs":           len(accepted),
					})
				}
				details, fetchErr := client.FetchJobDetails(raw.JobURL, raw.Title, raw.Location, isCancelled)
				if errors.Is(fetchErr, errSearchRunCancelled) {
					return nil, nil, "", errSearchRunCancelled
				}
				if fetchErr == nil {
					descriptionText = details.Description
					fetchedDescription = descriptionText != ""
					if normalizeWhitespace(details.JobType) != "" {
						jobType = details.JobType
					}
					if normalizeWhitespace(details.JobLevel) != "" {
						jobLevel = details.JobLevel
					}
					if normalizeWhitespace(details.CompanyIndustry) != "" {
						companyIndustry = details.CompanyIndustry
					}
					if normalizeWhitespace(details.JobFunction) != "" {
						jobFunction = details.JobFunction
					}
					if normalizeWhitespace(details.JobURLDirect) != "" {
						jobURLDirect = details.JobURLDirect
					}
					if details.IsRemote != nil {
						isRemote = details.IsRemote
					}
				}
				descriptionFetches++
				stats.DescriptionFetches = descriptionFetches
			} else {
				descriptionBudgetHit = true
				stats.DescriptionFetchSkipped++
			}
		}
		descriptionPositive, descriptionNegative, mentioned := detectDescriptionSignals(descriptionText)
		descriptionDesired := hasDesiredMention(mentioned, desiredVisaTypes)
		if applyVisaFiltering && descriptionPositive && descriptionDesired {
			stats.DescriptionSignalMatches++
		}
		if !applyVisaFiltering && !jobMatchesRequestedTitle(query.JobTitle, raw.Title) {
			continue
		}

		acceptJob := false
		if applyVisaFiltering {
			acceptJob = shouldAcceptJob(
				query.StrictnessMode,
				desiredCount,
				descriptionPositive,
				descriptionNegative,
				descriptionDesired,
				query.RequireDescriptionSignal,
			)
		} else {
			acceptJob = true
			if query.RequireDescriptionSignal && strings.TrimSpace(descriptionText) == "" {
				acceptJob = false
			}
		}
		if !acceptJob {
			continue
		}

		visasSponsored := []string{}
		if applyVisaFiltering {
			for _, visa := range desiredVisaTypes {
				if visaCounts[visa] > 0 || (descriptionDesired && slices.Contains(mentioned, visa)) {
					if label, ok := visaTypeLabels[visa]; ok {
						visasSponsored = append(visasSponsored, label)
					} else {
						visasSponsored = append(visasSponsored, visa)
					}
				}
			}
		} else {
			visasSponsored = allVisaLabelsFromCounts(visaCounts)
		}
		conf := confidenceScore(desiredCount, totalCount, descriptionPositive, descriptionNegative, descriptionDesired)
		reasons := buildEligibilityReasons(desiredCount, descriptionPositive, descriptionNegative, descriptionDesired, desiredVisaTypes)
		visaMatchStrength := visaMatchStrength(desiredCount, descriptionDesired, descriptionPositive)
		if !applyVisaFiltering {
			conf = generalConfidenceScore(hasCompany, fetchedDescription)
			reasons = buildGeneralEligibilityReasons(query.JobTitle, hasCompany, fetchedDescription)
			visaMatchStrength = "not_requested"
		}
		guidance := "Apply and tailor outreach to the hiring team."
		if len(contacts) > 0 {
			primary := contacts[0]
			name := getString(primary, "name")
			email := getString(primary, "email")
			if name != "" || email != "" {
				guidance = fmt.Sprintf("Prioritize outreach to %s %s after applying.", name, email)
			}
		}
		if isRemote == nil {
			isRemote = boolPtr(detectLinkedInRemote(raw.Title, raw.Location, descriptionText))
		}

		accepted = append(accepted, map[string]any{
			"job_url":             raw.JobURL,
			"title":               raw.Title,
			"company":             raw.Company,
			"location":            raw.Location,
			"site":                "linkedin",
			"date_posted":         raw.DatePosted,
			"description_fetched": fetchedDescription,
			"description":         optionalString(descriptionText),
			"description_excerpt": func() string {
				if len(descriptionText) > 280 {
					return descriptionText[:280]
				}
				return descriptionText
			}(),
			"salary_text":              optionalString(raw.SalaryText),
			"salary_currency":          optionalString(raw.SalaryCurrency),
			"salary_interval":          optionalString(raw.SalaryInterval),
			"salary_min_amount":        optionalInt(raw.SalaryMin),
			"salary_max_amount":        optionalInt(raw.SalaryMax),
			"salary_source":            optionalString(raw.SalarySource),
			"job_type":                 optionalString(jobType),
			"job_level":                optionalString(jobLevel),
			"company_industry":         optionalString(companyIndustry),
			"job_function":             optionalString(jobFunction),
			"job_url_direct":           optionalString(jobURLDirect),
			"is_remote":                optionalBool(isRemote),
			"employer_contacts":        contacts,
			"visa_counts":              visaCounts,
			"visas_sponsored":          visasSponsored,
			"visa_match_strength":      visaMatchStrength,
			"eligibility_reasons":      reasons,
			"confidence_score":         conf,
			"confidence_model_version": "v1.1.0-rules-go",
			"agent_guidance":           guidance,
		})
		if len(accepted) >= requiredAccepted {
			break
		}

		if idx%25 == 0 {
			progress := 76.0 + (18.0 * float64(idx+1) / float64(max(1, len(rawJobs))))
			detail := "Scoring job relevance."
			if applyVisaFiltering {
				detail = "Scoring visa eligibility."
			}
			onProgress("filter", detail, progress, map[string]any{
				"accepted_jobs": len(accepted),
			})
		}
	}

	sessionRecord, err := saveSearchSessionRecord(query, desiredVisaTypes, accepted, scanExhausted, rawScanTarget)
	if err != nil {
		return nil, nil, "", err
	}
	sessionID := getString(sessionRecord, "session_id")
	acceptedWithIDs := []map[string]any{}
	for _, raw := range listOrEmpty(sessionRecord["accepted_jobs"]) {
		row := mapOrNil(raw)
		if row != nil {
			acceptedWithIDs = append(acceptedWithIDs, row)
		}
	}

	page, pagination := sliceAcceptedJobs(acceptedWithIDs, query.Offset, query.MaxReturned, rawScanTarget, query.MaxScanResults, scanExhausted)
	stats.AcceptedJobs = len(acceptedWithIDs)
	stats.ReturnedJobs = len(page)
	stats.DatasetRows = dataset.Rows

	recoverySuggestions := []any{}
	if len(page) == 0 {
		recoverySuggestions = append(recoverySuggestions, map[string]any{
			"type":             "related_titles",
			"job_title":        query.JobTitle,
			"suggested_titles": findRelatedTitlesInternal(query.JobTitle, 8),
		})
	}
	if descriptionBudgetHit {
		recoverySuggestions = append(recoverySuggestions, map[string]any{
			"type":                    "description_probe_budget_reached",
			"message":                 "Stopped description probing due runtime budget; narrow the search or rerun.",
			"description_fetch_limit": descriptionFetchLimit,
		})
	}
	if datasetLoadWarning != "" {
		recoverySuggestions = append(recoverySuggestions, map[string]any{
			"type":    "dataset_unavailable",
			"message": "Company dataset was unavailable; results were ranked using live listing signals only.",
		})
	}

	statusMessage := fmt.Sprintf(
		"Evaluated %d raw LinkedIn jobs and accepted %d matching %q in %q.",
		stats.RawJobsScanned,
		stats.AcceptedJobs,
		query.JobTitle,
		query.Location,
	)
	if applyVisaFiltering {
		labels := labelsForDesiredVisas(desiredVisaTypes)
		statusMessage = fmt.Sprintf(
			"Evaluated %d raw LinkedIn jobs and accepted %d for %s sponsorship.",
			stats.RawJobsScanned,
			stats.AcceptedJobs,
			strings.Join(labels, ", "),
		)
		if len(page) == 0 {
			statusMessage = fmt.Sprintf(
				"No jobs matched requested visa criteria yet for %s. Try related titles or wider location.",
				strings.Join(labels, ", "),
			)
		}
	} else if len(page) == 0 {
		statusMessage = fmt.Sprintf(
			"No jobs matched %q in %q yet. Try related titles or a wider location.",
			query.JobTitle,
			query.Location,
		)
	}

	statsMap := map[string]any{
		"raw_jobs_scanned":           stats.RawJobsScanned,
		"accepted_jobs":              stats.AcceptedJobs,
		"returned_jobs":              stats.ReturnedJobs,
		"company_matches":            stats.CompanyMatches,
		"description_signal_matches": stats.DescriptionSignalMatches,
		"description_fetches":        stats.DescriptionFetches,
		"description_fetch_skipped":  stats.DescriptionFetchSkipped,
		"description_fetch_limit":    descriptionFetchLimit,
		"description_budget_hit":     descriptionBudgetHit,
		"ignored_jobs_skipped":       stats.IgnoredJobsSkipped,
		"ignored_companies_skipped":  stats.IgnoredCompaniesSkipped,
		"dataset_rows":               stats.DatasetRows,
		"visa_filtering_enabled":     applyVisaFiltering,
	}

	searchTools := map[string]any{
		"start":   "start_job_search",
		"status":  "get_job_search_status",
		"results": "get_job_search_results",
		"cancel":  "cancel_job_search",
	}
	longGuidance := "Use start_job_search then poll get_job_search_status; fetch pages with get_job_search_results."
	if queryMode == searchModeVisa {
		searchTools = map[string]any{
			"start":   "start_visa_job_search",
			"status":  "get_visa_job_search_status",
			"results": "get_visa_job_search_results",
			"cancel":  "cancel_visa_job_search",
		}
		longGuidance = "Use start_visa_job_search then poll get_visa_job_search_status; fetch pages with get_visa_job_search_results."
	}

	response := map[string]any{
		"status": map[string]any{
			"outcome": func() string {
				if len(page) > 0 {
					return "completed"
				}
				return "completed_no_results"
			}(),
			"message":            statusMessage,
			"site":               query.Site,
			"strictness_mode":    query.StrictnessMode,
			"search_mode":        queryMode,
			"visa_filtering":     applyVisaFiltering,
			"desired_visa_types": desiredVisaTypes,
			"search_session": map[string]any{
				"session_id":          sessionID,
				"expires_at_utc":      sessionRecord["expires_at_utc"],
				"accepted_jobs_total": len(acceptedWithIDs),
			},
			"scan_outcome": map[string]any{
				"scan_exhausted":        scanExhausted,
				"requested_scan_target": rawScanTarget,
				"max_scan_results":      query.MaxScanResults,
			},
		},
		"stats": statsMap,
		"guidance": map[string]any{
			"long_search_guidance":    longGuidance,
			"background_search_tools": searchTools,
		},
		"dataset_freshness":    freshness,
		"pagination":           pagination,
		"recovery_suggestions": recoverySuggestions,
		"jobs": func() []any {
			out := []any{}
			for _, item := range page {
				out = append(out, item)
			}
			return out
		}(),
	}
	onProgress("completed", "Search run completed.", 100, map[string]any{
		"accepted_jobs": len(acceptedWithIDs),
		"returned_jobs": len(page),
	})
	return response, statsMap, sessionID, nil
}

func optionalString(value string) any {
	clean := normalizeWhitespace(value)
	if clean == "" {
		return nil
	}
	return clean
}

func optionalInt(value *int) any {
	if value == nil {
		return nil
	}
	return *value
}

func optionalBool(value *bool) any {
	if value == nil {
		return nil
	}
	return *value
}

func allVisaLabelsFromCounts(visaCounts map[string]int) []string {
	order := []string{"h1b", "h1b1_chile", "h1b1_singapore", "e3_australian", "green_card"}
	out := []string{}
	for _, key := range order {
		if visaCounts[key] <= 0 {
			continue
		}
		if label, ok := visaTypeLabels[key]; ok {
			out = append(out, label)
		}
	}
	return out
}

func generalConfidenceScore(hasCompany bool, fetchedDescription bool) float64 {
	score := 0.55
	if hasCompany {
		score += 0.2
	}
	if fetchedDescription {
		score += 0.15
	}
	if score > 1 {
		score = 1
	}
	return score
}

func buildGeneralEligibilityReasons(jobTitle string, hasCompany bool, fetchedDescription bool) []string {
	reasons := []string{
		fmt.Sprintf("matches_requested_title_%s", normalizeCompanyName(jobTitle)),
	}
	if hasCompany {
		reasons = append(reasons, "company_found_in_dataset")
	}
	if fetchedDescription {
		reasons = append(reasons, "job_description_fetched")
	}
	return reasons
}

func tokenizeSearchText(value string) []string {
	out := []string{}
	for _, token := range strings.FieldsFunc(strings.ToLower(value), func(r rune) bool {
		return !unicode.IsLetter(r) && !unicode.IsDigit(r) && r != '+' && r != '#'
	}) {
		token = strings.TrimSpace(token)
		if token == "" {
			continue
		}
		out = append(out, token)
	}
	return out
}

func jobMatchesRequestedTitle(requestedTitle string, jobTitle string) bool {
	requested := tokenizeSearchText(requestedTitle)
	if len(requested) == 0 {
		return true
	}
	titleTokens := tokenizeSearchText(jobTitle)
	if len(titleTokens) == 0 {
		return false
	}
	titleSet := map[string]struct{}{}
	for _, token := range titleTokens {
		titleSet[token] = struct{}{}
	}

	matches := 0
	for _, token := range requested {
		if _, ok := titleSet[token]; ok {
			matches++
		}
	}

	if len(requested) == 1 {
		query := requested[0]
		if len(query) <= 2 {
			return matches > 0
		}
		return matches > 0 || strings.Contains(strings.ToLower(jobTitle), query)
	}
	required := 1
	if len(requested) >= 3 {
		required = 2
	}
	return matches >= required
}
