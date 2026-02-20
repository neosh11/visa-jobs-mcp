package user

import (
	"bytes"
	"context"
	"errors"
	"fmt"
	"net/http"
	"net/url"
	"os"
	"os/exec"
	"path/filepath"
	"regexp"
	"slices"
	"strconv"
	"strings"
	"time"

	"github.com/PuerkitoBio/goquery"
)

const defaultDOLPerformanceURL = "https://www.dol.gov/agencies/eta/foreign-labor/performance"

var yearPattern = regexp.MustCompile(`(20[0-9]{2})`)

type disclosureURL struct {
	URL  string
	Year int
}

func disclosureLooksRelevant(link string) bool {
	clean := strings.ToLower(strings.TrimSpace(link))
	if clean == "" {
		return false
	}
	if !strings.Contains(clean, "disclosure") &&
		!strings.Contains(clean, "h-1b") &&
		!strings.Contains(clean, "h1b") &&
		!strings.Contains(clean, "perm") &&
		!strings.Contains(clean, "9089") {
		return false
	}
	for _, ext := range []string{".zip", ".csv", ".xlsx", ".xls", ".txt"} {
		if strings.Contains(clean, ext) {
			return true
		}
	}
	return strings.Contains(clean, "disclosure")
}

func isLCADisclosure(link string) bool {
	clean := strings.ToLower(link)
	return strings.Contains(clean, "lca") ||
		strings.Contains(clean, "h-1b") ||
		strings.Contains(clean, "h1b")
}

func isPERMDisclosure(link string) bool {
	clean := strings.ToLower(link)
	return strings.Contains(clean, "perm") ||
		strings.Contains(clean, "9089")
}

func parseDisclosureYear(link string) int {
	matches := yearPattern.FindAllString(link, -1)
	latest := 0
	for _, one := range matches {
		year, err := strconv.Atoi(one)
		if err == nil && year > latest {
			latest = year
		}
	}
	return latest
}

func sortDisclosureURLs(values []string) []string {
	rows := make([]disclosureURL, 0, len(values))
	for _, one := range values {
		rows = append(rows, disclosureURL{
			URL:  one,
			Year: parseDisclosureYear(one),
		})
	}
	slices.SortFunc(rows, func(a, b disclosureURL) int {
		if a.Year != b.Year {
			if a.Year > b.Year {
				return -1
			}
			return 1
		}
		return strings.Compare(a.URL, b.URL)
	})
	out := make([]string, 0, len(rows))
	for _, row := range rows {
		out = append(out, row.URL)
	}
	return out
}

func resolveAbsolute(baseURL, href string) string {
	href = strings.TrimSpace(href)
	if href == "" || strings.HasPrefix(href, "#") {
		return ""
	}
	lower := strings.ToLower(href)
	if strings.HasPrefix(lower, "javascript:") || strings.HasPrefix(lower, "mailto:") {
		return ""
	}

	baseParsed, err := url.Parse(baseURL)
	if err != nil {
		return ""
	}
	parsed, err := url.Parse(href)
	if err != nil {
		return ""
	}
	abs := baseParsed.ResolveReference(parsed)
	abs.Fragment = ""
	return abs.String()
}

func DiscoverLatestDolDisclosureURLs(args map[string]any) (map[string]any, error) {
	performanceURL := strings.TrimSpace(getString(args, "performance_url"))
	if performanceURL == "" {
		performanceURL = strings.TrimSpace(os.Getenv("VISA_DOL_PERFORMANCE_URL"))
	}
	if performanceURL == "" {
		performanceURL = defaultDOLPerformanceURL
	}

	timeout := envInt("VISA_DOL_DISCOVERY_TIMEOUT_SECONDS", 25)
	client := &http.Client{
		Timeout: time.Duration(timeout) * time.Second,
		Transport: &http.Transport{
			Proxy: nil,
		},
	}
	req, err := http.NewRequest(http.MethodGet, performanceURL, nil)
	if err != nil {
		return nil, fmt.Errorf("build request: %w", err)
	}
	req.Header.Set("User-Agent", "visa-jobs-mcp-go/0.3")
	resp, err := client.Do(req)
	if err != nil {
		return map[string]any{
			"status":            "failed",
			"error":             err.Error(),
			"source_page_url":   performanceURL,
			"discovered_at_utc": utcNowISO(),
			"guidance":          "Could not reach DOL page. Check network access and retry.",
		}, nil
	}
	defer resp.Body.Close()

	if resp.StatusCode < 200 || resp.StatusCode > 299 {
		return map[string]any{
			"status":            "failed",
			"error":             fmt.Sprintf("DOL page returned status %d", resp.StatusCode),
			"source_page_url":   performanceURL,
			"discovered_at_utc": utcNowISO(),
		}, nil
	}

	doc, err := goquery.NewDocumentFromReader(resp.Body)
	if err != nil {
		return nil, fmt.Errorf("parse DOL performance page: %w", err)
	}

	allSet := map[string]struct{}{}
	lcaSet := map[string]struct{}{}
	permSet := map[string]struct{}{}
	doc.Find("a[href]").Each(func(_ int, selection *goquery.Selection) {
		href, ok := selection.Attr("href")
		if !ok {
			return
		}
		abs := resolveAbsolute(performanceURL, href)
		if abs == "" || !disclosureLooksRelevant(abs) {
			return
		}
		allSet[abs] = struct{}{}
		if isLCADisclosure(abs) {
			lcaSet[abs] = struct{}{}
		}
		if isPERMDisclosure(abs) {
			permSet[abs] = struct{}{}
		}
	})

	toList := func(values map[string]struct{}) []string {
		out := make([]string, 0, len(values))
		for value := range values {
			out = append(out, value)
		}
		return sortDisclosureURLs(out)
	}

	all := toList(allSet)
	lca := toList(lcaSet)
	perm := toList(permSet)

	status := "ok"
	if len(all) == 0 {
		status = "empty"
	}
	return map[string]any{
		"status":                  status,
		"source_page_url":         performanceURL,
		"discovered_at_utc":       utcNowISO(),
		"lca_disclosure_urls":     lca,
		"perm_disclosure_urls":    perm,
		"all_disclosure_urls":     all,
		"latest_lca_disclosure":   firstOrNil(lca),
		"latest_perm_disclosure":  firstOrNil(perm),
		"total_disclosures_found": len(all),
	}, nil
}

func firstOrNil(values []string) any {
	if len(values) == 0 {
		return nil
	}
	return values[0]
}

func outputTail(text string, lines int) string {
	trimmed := strings.TrimSpace(text)
	if trimmed == "" {
		return ""
	}
	all := strings.Split(trimmed, "\n")
	if len(all) <= lines {
		return trimmed
	}
	return strings.Join(all[len(all)-lines:], "\n")
}

func inferExitCode(err error) any {
	if err == nil {
		return 0
	}
	var exitErr *exec.ExitError
	if errors.As(err, &exitErr) {
		return exitErr.ExitCode()
	}
	return nil
}

func defaultPipelineCommand() string {
	script := filepath.Join("scripts", "run_internal_pipeline.sh")
	if info, err := os.Stat(script); err == nil && !info.IsDir() {
		return script
	}
	return "python3 -m visa_jobs_mcp.pipeline_cli"
}

func RunInternalDolPipeline(args map[string]any) (map[string]any, error) {
	command := strings.TrimSpace(getString(args, "command"))
	if command == "" {
		command = strings.TrimSpace(os.Getenv("VISA_DOL_PIPELINE_COMMAND"))
	}
	if command == "" {
		command = defaultPipelineCommand()
	}

	timeoutSeconds := envInt("VISA_DOL_PIPELINE_TIMEOUT_SECONDS", 1800)
	if timeoutSeconds < 60 {
		timeoutSeconds = 60
	}
	datasetPath := datasetPathOrDefault(getString(args, "dataset_path"))
	manifestPath := envOrDefault("VISA_DOL_MANIFEST_PATH", defaultManifestPath)
	if rawManifest := getString(args, "manifest_path"); rawManifest != "" {
		manifestPath = rawManifest
	}

	started := utcNow()
	ctx, cancel := context.WithTimeout(context.Background(), time.Duration(timeoutSeconds)*time.Second)
	defer cancel()

	var stdout bytes.Buffer
	var stderr bytes.Buffer
	cmd := exec.CommandContext(ctx, "bash", "-lc", command)
	cmd.Stdout = &stdout
	cmd.Stderr = &stderr
	runErr := cmd.Run()
	completed := utcNow()
	durationSeconds := completed.Sub(started).Seconds()

	timedOut := errors.Is(ctx.Err(), context.DeadlineExceeded)
	result := map[string]any{
		"status":            "completed",
		"command":           command,
		"started_at_utc":    toISO(started),
		"completed_at_utc":  toISO(completed),
		"duration_seconds":  durationSeconds,
		"timed_out":         timedOut,
		"exit_code":         inferExitCode(runErr),
		"stdout_tail":       outputTail(stdout.String(), 20),
		"stderr_tail":       outputTail(stderr.String(), 20),
		"dataset_path":      datasetPath,
		"manifest_path":     manifestPath,
		"dataset_freshness": datasetFreshness(datasetPath, manifestPath),
	}
	if runErr != nil {
		result["status"] = "failed"
		if timedOut {
			result["error"] = fmt.Sprintf("Pipeline timed out after %d seconds", timeoutSeconds)
		} else {
			result["error"] = runErr.Error()
		}
		result["guidance"] = "Pipeline execution failed. Re-run command directly to inspect full logs."
	}
	return result, nil
}
