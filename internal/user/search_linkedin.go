package user

import (
	"errors"
	"fmt"
	"net/http"
	"net/url"
	"strconv"
	"strings"
	"time"

	"github.com/PuerkitoBio/goquery"
	"github.com/go-resty/resty/v2"
)

const linkedInSearchURL = "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"

type liveLinkedInClient struct {
	httpClient *resty.Client
}

func newLiveLinkedInClient() linkedInClient {
	transport := &http.Transport{
		Proxy: nil,
	}
	client := resty.New()
	client.SetTransport(transport)
	client.SetHeader("Accept", "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8")
	client.SetHeader("Accept-Language", "en-US,en;q=0.9")
	client.SetHeader("Cache-Control", "no-cache")
	client.SetHeader("Pragma", "no-cache")
	client.SetHeader("Upgrade-Insecure-Requests", "1")
	client.SetHeader("User-Agent", "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
	client.SetTimeout(time.Duration(linkedInRequestTimeoutSeconds()) * time.Second)
	client.SetRetryCount(0)
	return &liveLinkedInClient{httpClient: client}
}

func stripQuery(raw string) string {
	raw = strings.TrimSpace(raw)
	if raw == "" {
		return ""
	}
	parsed, err := url.Parse(raw)
	if err != nil {
		return raw
	}
	parsed.RawQuery = ""
	return parsed.String()
}

func firstNonEmptyText(selection *goquery.Selection, selectors ...string) string {
	for _, selector := range selectors {
		text := strings.TrimSpace(selection.Find(selector).First().Text())
		if text != "" {
			return text
		}
	}
	return ""
}

func parseLinkedInListHTML(html string) ([]linkedInJob, error) {
	doc, err := goquery.NewDocumentFromReader(strings.NewReader(html))
	if err != nil {
		return nil, err
	}
	out := []linkedInJob{}
	doc.Find("div.base-search-card").Each(func(_ int, card *goquery.Selection) {
		href, _ := card.Find("a.base-card__full-link").Attr("href")
		jobURL := stripQuery(href)
		if jobURL == "" {
			return
		}
		title := firstNonEmptyText(card, "h3.base-search-card__title", "span.sr-only")
		company := strings.TrimSpace(card.Find("h4.base-search-card__subtitle").Text())
		location := strings.TrimSpace(card.Find("span.job-search-card__location").First().Text())
		datePosted := ""
		if dateNode := card.Find("time").First(); dateNode != nil {
			if datetimeValue, ok := dateNode.Attr("datetime"); ok {
				datePosted = strings.TrimSpace(datetimeValue)
			}
		}
		out = append(out, linkedInJob{
			JobURL:     jobURL,
			Title:      title,
			Company:    company,
			Location:   location,
			Site:       "linkedin",
			DatePosted: datePosted,
		})
	})
	return out, nil
}

func parseLinkedInDescriptionHTML(html string) string {
	doc, err := goquery.NewDocumentFromReader(strings.NewReader(html))
	if err != nil {
		return ""
	}
	markup := doc.Find("div.show-more-less-html__markup").First()
	if markup == nil || markup.Length() == 0 {
		markup = doc.Find("div[class*='show-more-less-html__markup']").First()
	}
	text := strings.TrimSpace(markup.Text())
	text = strings.Join(strings.Fields(text), " ")
	return text
}

func isRateLimitStatus(code int) bool {
	return code == http.StatusTooManyRequests
}

func isRateLimitError(err error) bool {
	if err == nil {
		return false
	}
	text := strings.ToLower(err.Error())
	return strings.Contains(text, "429") || strings.Contains(text, "rate limit") || strings.Contains(text, "too many requests")
}

func requestWithRateLimitBackoff(
	doRequest func() (*resty.Response, error),
	isCancelled func() bool,
) (*resty.Response, float64, int, error) {
	window := float64(rateLimitRetryWindowSeconds())
	backoff := float64(rateLimitInitialBackoffSeconds())
	maxBackoff := float64(rateLimitMaxBackoffSeconds())
	elapsed := 0.0
	retries := 0

	for {
		if isCancelled != nil && isCancelled() {
			return nil, elapsed, retries, errSearchRunCancelled
		}
		resp, err := doRequest()
		if err == nil && resp != nil && !isRateLimitStatus(resp.StatusCode()) {
			return resp, elapsed, retries, nil
		}

		shouldRetry := false
		if err != nil && isRateLimitError(err) {
			shouldRetry = true
		}
		if err == nil && resp != nil && isRateLimitStatus(resp.StatusCode()) {
			shouldRetry = true
		}
		if !shouldRetry {
			if err != nil {
				return nil, elapsed, retries, err
			}
			if resp != nil {
				return resp, elapsed, retries, fmt.Errorf("linkedin request failed with status %d", resp.StatusCode())
			}
			return nil, elapsed, retries, errors.New("linkedin request failed without response")
		}

		if elapsed >= window {
			return nil, elapsed, retries, fmt.Errorf("rate limited by upstream job source (429/Too Many Requests). Retried for 3 minutes without recovery. Please try again shortly")
		}
		sleepFor := backoff
		if sleepFor > maxBackoff {
			sleepFor = maxBackoff
		}
		remaining := window - elapsed
		if sleepFor > remaining {
			sleepFor = remaining
		}
		if sleepFor <= 0 {
			return nil, elapsed, retries, fmt.Errorf("rate limited by upstream job source (429/Too Many Requests). Retried for 3 minutes without recovery. Please try again shortly")
		}
		sleepDur := time.Duration(sleepFor * float64(time.Second))
		if !sleepWithCancel(sleepDur, isCancelled) {
			return nil, elapsed, retries, errSearchRunCancelled
		}
		elapsed += sleepFor
		retries++
		backoff *= 2
	}
}

func sleepWithCancel(duration time.Duration, isCancelled func() bool) bool {
	if duration <= 0 {
		return true
	}
	if isCancelled == nil {
		time.Sleep(duration)
		return true
	}
	const slice = 250 * time.Millisecond
	deadline := time.Now().Add(duration)
	for {
		if isCancelled() {
			return false
		}
		remaining := time.Until(deadline)
		if remaining <= 0 {
			return true
		}
		step := slice
		if remaining < step {
			step = remaining
		}
		time.Sleep(step)
	}
}

func (c *liveLinkedInClient) FetchSearchPage(query linkedInSearchQuery, isCancelled func() bool) ([]linkedInJob, error) {
	params := map[string]string{
		"keywords": query.JobTitle,
		"location": query.Location,
		"start":    strconv.Itoa(query.Start),
	}
	if query.HoursOld > 0 {
		params["f_TPR"] = fmt.Sprintf("r%d", query.HoursOld*3600)
	}
	resp, _, _, err := requestWithRateLimitBackoff(func() (*resty.Response, error) {
		return c.httpClient.R().
			SetQueryParams(params).
			Get(linkedInSearchURL)
	}, isCancelled)
	if err != nil {
		return nil, err
	}
	body := string(resp.Body())
	return parseLinkedInListHTML(body)
}

func (c *liveLinkedInClient) FetchJobDescription(jobURL string, isCancelled func() bool) (string, error) {
	resp, _, _, err := requestWithRateLimitBackoff(func() (*resty.Response, error) {
		return c.httpClient.R().Get(jobURL)
	}, isCancelled)
	if err != nil {
		return "", err
	}
	return parseLinkedInDescriptionHTML(string(resp.Body())), nil
}
