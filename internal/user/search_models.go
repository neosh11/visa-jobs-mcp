package user

import (
	"os"
	"strconv"
	"strings"
	"time"
)

const (
	defaultSearchResultsWanted       = 300
	defaultSearchHoursOld            = 336
	defaultSearchMaxReturned         = 10
	defaultSearchScanMultiplier      = 8
	defaultSearchMaxScanResults      = 1200
	defaultSearchRunTTLSeconds       = 21600
	defaultSearchSessionTTLSeconds   = 21600
	defaultSearchMaxRuns             = 500
	defaultSearchMaxSessions         = 200
	defaultSearchMaxSessionsPerUser  = 20
	defaultRateLimitRetryWindowSec   = 180
	defaultRateLimitInitialBackoff   = 2
	defaultRateLimitMaxBackoff       = 30
	defaultLinkedInRequestTimeoutSec = 12
)

type companyDatasetRecord struct {
	CompanyName string
	CompanyTier string

	H1B              int
	H1B1Chile        int
	H1B1Singapore    int
	E3Australian     int
	GreenCard        int
	TotalVisas       int
	EmployerContacts []map[string]any
}

type companyDataset struct {
	Rows                int
	ByNormalizedCompany map[string]companyDatasetRecord
}

type linkedInJob struct {
	JobURL     string
	Title      string
	Company    string
	Location   string
	Site       string
	DatePosted string
}

type linkedInSearchQuery struct {
	JobTitle string
	Location string
	HoursOld int
	Start    int
}

type linkedInClient interface {
	FetchSearchPage(query linkedInSearchQuery) ([]linkedInJob, error)
	FetchJobDescription(jobURL string) (string, error)
}

type searchQuery struct {
	RunID                    string
	UserID                   string
	Location                 string
	JobTitle                 string
	HoursOld                 int
	DatasetPath              string
	Site                     string
	ResultsWanted            int
	MaxReturned              int
	Offset                   int
	RequireDescriptionSignal bool
	StrictnessMode           string
	RefreshSession           bool
	ScanMultiplier           int
	MaxScanResults           int
}

type searchExecutionStats struct {
	RawJobsScanned           int
	AcceptedJobs             int
	ReturnedJobs             int
	CompanyMatches           int
	DescriptionSignalMatches int
	IgnoredJobsSkipped       int
	IgnoredCompaniesSkipped  int
	DatasetRows              int
	RetrySleepSeconds        float64
	RetryAttempts            int
}

func envInt(name string, fallback int) int {
	raw := strings.TrimSpace(os.Getenv(name))
	if raw == "" {
		return fallback
	}
	value, err := strconv.Atoi(raw)
	if err != nil {
		return fallback
	}
	return value
}

func searchRunTTLSeconds() int {
	return envInt("VISA_SEARCH_RUN_TTL_SECONDS", defaultSearchRunTTLSeconds)
}

func searchSessionTTLSeconds() int {
	return envInt("VISA_SEARCH_SESSION_TTL_SECONDS", defaultSearchSessionTTLSeconds)
}

func searchMaxRuns() int {
	return envInt("VISA_MAX_SEARCH_RUNS", defaultSearchMaxRuns)
}

func searchMaxSessions() int {
	return envInt("VISA_MAX_SEARCH_SESSIONS", defaultSearchMaxSessions)
}

func searchMaxSessionsPerUser() int {
	return envInt("VISA_MAX_SEARCH_SESSIONS_PER_USER", defaultSearchMaxSessionsPerUser)
}

func rateLimitRetryWindowSeconds() int {
	return envInt("VISA_RATE_LIMIT_RETRY_WINDOW_SECONDS", defaultRateLimitRetryWindowSec)
}

func rateLimitInitialBackoffSeconds() int {
	return envInt("VISA_RATE_LIMIT_INITIAL_BACKOFF_SECONDS", defaultRateLimitInitialBackoff)
}

func rateLimitMaxBackoffSeconds() int {
	return envInt("VISA_RATE_LIMIT_MAX_BACKOFF_SECONDS", defaultRateLimitMaxBackoff)
}

func linkedInRequestTimeoutSeconds() int {
	return envInt("VISA_LINKEDIN_TIMEOUT_SECONDS", defaultLinkedInRequestTimeoutSec)
}

func strictnessOrDefault(value string) string {
	mode := strings.ToLower(strings.TrimSpace(value))
	if mode == "" {
		return "strict"
	}
	if mode == "strict" || mode == "balanced" {
		return mode
	}
	return mode
}

func utcNow() time.Time {
	return time.Now().UTC()
}
