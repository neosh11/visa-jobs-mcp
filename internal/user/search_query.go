package user

import (
	"errors"
	"fmt"
	"slices"
	"strings"
	"time"
)

func executeSearchQuery(
	query searchQuery,
	onProgress func(phase, detail string, progress float64, payload map[string]any),
	isCancelled func() bool,
) (map[string]any, map[string]any, string, error) {
	desiredVisaTypes, err := getRequiredUserVisaTypes(query.UserID)
	if err != nil {
		return nil, nil, "", err
	}
	if len(desiredVisaTypes) == 0 {
		return nil, nil, "", fmt.Errorf("no preferred visa types set for user_id='%s'", query.UserID)
	}

	onProgress("dataset", "Loading sponsor dataset.", 5, nil)
	dataset, err := loadCompanyDataset(query.DatasetPath)
	if err != nil {
		return nil, nil, "", err
	}
	freshness := datasetFreshness(datasetPathOrDefault(query.DatasetPath), envOrDefault("VISA_DOL_MANIFEST_PATH", defaultManifestPath))
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

	onProgress("filter", "Evaluating visa relevance.", 76, map[string]any{"raw_jobs_scanned": len(rawJobs)})
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
		needsDescription := query.RequireDescriptionSignal || desiredCount == 0
		if needsDescription {
			canFetchDescription := descriptionFetches < descriptionFetchLimit && time.Now().Before(descriptionDeadline)
			if canFetchDescription {
				if descriptionFetches%5 == 0 {
					onProgress("filter", "Checking job descriptions for visa signals.", 80, map[string]any{
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
		if descriptionPositive && descriptionDesired {
			stats.DescriptionSignalMatches++
		}

		if !shouldAcceptJob(
			query.StrictnessMode,
			desiredCount,
			descriptionPositive,
			descriptionNegative,
			descriptionDesired,
			query.RequireDescriptionSignal,
		) {
			continue
		}

		visasSponsored := []string{}
		for _, visa := range desiredVisaTypes {
			if visaCounts[visa] > 0 || (descriptionDesired && slices.Contains(mentioned, visa)) {
				if label, ok := visaTypeLabels[visa]; ok {
					visasSponsored = append(visasSponsored, label)
				} else {
					visasSponsored = append(visasSponsored, visa)
				}
			}
		}
		conf := confidenceScore(desiredCount, totalCount, descriptionPositive, descriptionNegative, descriptionDesired)
		reasons := buildEligibilityReasons(desiredCount, descriptionPositive, descriptionNegative, descriptionDesired, desiredVisaTypes)
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
			"visa_match_strength":      visaMatchStrength(desiredCount, descriptionDesired, descriptionPositive),
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
			onProgress("filter", "Scoring visa eligibility.", progress, map[string]any{
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

	labels := labelsForDesiredVisas(desiredVisaTypes)
	statusMessage := fmt.Sprintf(
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
			"long_search_guidance": "Use start_visa_job_search then poll get_visa_job_search_status; fetch pages with get_visa_job_search_results.",
			"background_search_tools": map[string]any{
				"start":   "start_visa_job_search",
				"status":  "get_visa_job_search_status",
				"results": "get_visa_job_search_results",
				"cancel":  "cancel_visa_job_search",
			},
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
