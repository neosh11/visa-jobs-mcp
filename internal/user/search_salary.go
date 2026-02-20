package user

import (
	"math"
	"regexp"
	"sort"
	"strconv"
	"strings"
)

type jobCompensation struct {
	Text      string
	Currency  string
	Interval  string
	MinAmount *int
	MaxAmount *int
}

var salaryNumberPattern = regexp.MustCompile(`(?i)(\d{1,3}(?:,\d{3})+|\d+(?:\.\d+)?)(\s*[kmb])?`)

func parseCompensation(raw string) (jobCompensation, bool) {
	text := normalizeWhitespace(raw)
	if text == "" {
		return jobCompensation{}, false
	}

	out := jobCompensation{
		Text:     text,
		Currency: detectCurrency(text),
		Interval: detectSalaryInterval(text),
	}

	amounts := parseSalaryAmounts(text)
	if len(amounts) == 0 {
		return jobCompensation{}, false
	}

	lower := strings.ToLower(text)
	switch {
	case strings.Contains(lower, "up to") || strings.Contains(lower, "maximum") || strings.Contains(lower, "max"):
		out.MaxAmount = intPtr(amounts[0])
	case strings.Contains(lower, "from ") || strings.Contains(lower, "minimum") || strings.Contains(lower, "min"):
		out.MinAmount = intPtr(amounts[0])
	default:
		out.MinAmount = intPtr(amounts[0])
	}

	if len(amounts) > 1 {
		minAmount := amounts[0]
		maxAmount := amounts[1]
		if minAmount > maxAmount {
			minAmount, maxAmount = maxAmount, minAmount
		}
		out.MinAmount = intPtr(minAmount)
		out.MaxAmount = intPtr(maxAmount)
	}

	return out, true
}

func parseSalaryAmounts(text string) []int {
	matches := salaryNumberPattern.FindAllStringSubmatch(text, -1)
	if len(matches) == 0 {
		return nil
	}
	values := make([]int, 0, 2)
	for _, match := range matches {
		if len(match) < 2 {
			continue
		}
		numberText := strings.ReplaceAll(strings.TrimSpace(match[1]), ",", "")
		numberValue, err := strconv.ParseFloat(numberText, 64)
		if err != nil {
			continue
		}
		suffix := strings.ToLower(strings.TrimSpace(match[2]))
		switch suffix {
		case "k":
			numberValue *= 1000
		case "m":
			numberValue *= 1000000
		case "b":
			numberValue *= 1000000000
		}
		value := int(math.Round(numberValue))
		// Ignore tiny values that are unlikely to be compensation.
		if value < 10 {
			continue
		}
		values = append(values, value)
		if len(values) == 2 {
			break
		}
	}
	if len(values) == 0 {
		return nil
	}
	sort.Ints(values)
	return values
}

func detectCurrency(text string) string {
	lower := strings.ToLower(text)
	switch {
	case strings.Contains(text, "$"), strings.Contains(lower, "usd"):
		return "USD"
	case strings.Contains(text, "€"), strings.Contains(lower, "eur"):
		return "EUR"
	case strings.Contains(text, "£"), strings.Contains(lower, "gbp"):
		return "GBP"
	case strings.Contains(text, "₹"), strings.Contains(lower, "inr"):
		return "INR"
	case strings.Contains(lower, "aud"):
		return "AUD"
	case strings.Contains(lower, "cad"):
		return "CAD"
	default:
		return ""
	}
}

func detectSalaryInterval(text string) string {
	lower := strings.ToLower(text)
	switch {
	case strings.Contains(lower, "/hr"),
		strings.Contains(lower, "/hour"),
		strings.Contains(lower, "per hour"),
		strings.Contains(lower, "hourly"):
		return "hourly"
	case strings.Contains(lower, "/day"),
		strings.Contains(lower, "per day"),
		strings.Contains(lower, "daily"):
		return "daily"
	case strings.Contains(lower, "/wk"),
		strings.Contains(lower, "/week"),
		strings.Contains(lower, "per week"),
		strings.Contains(lower, "weekly"):
		return "weekly"
	case strings.Contains(lower, "/mo"),
		strings.Contains(lower, "/month"),
		strings.Contains(lower, "per month"),
		strings.Contains(lower, "monthly"):
		return "monthly"
	case strings.Contains(lower, "/yr"),
		strings.Contains(lower, "/year"),
		strings.Contains(lower, "per year"),
		strings.Contains(lower, "yearly"),
		strings.Contains(lower, "annual"):
		return "yearly"
	default:
		return ""
	}
}

func intPtr(value int) *int {
	clone := value
	return &clone
}

func normalizeWhitespace(text string) string {
	return strings.Join(strings.Fields(strings.TrimSpace(text)), " ")
}
