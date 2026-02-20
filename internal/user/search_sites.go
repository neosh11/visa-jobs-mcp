package user

import (
	"fmt"
	"strings"
)

func normalizeSearchSite(site string) (string, error) {
	clean := strings.ToLower(strings.TrimSpace(site))
	if clean == "" {
		clean = "linkedin"
	}
	if clean != "linkedin" {
		return "", fmt.Errorf("only linkedin is supported right now: %q", clean)
	}
	return clean, nil
}

func newSiteClient(site string) (linkedInClient, error) {
	clean, err := normalizeSearchSite(site)
	if err != nil {
		return nil, err
	}
	switch clean {
	case "linkedin":
		return linkedInClientFactory(), nil
	default:
		return nil, fmt.Errorf("unsupported site: %q", clean)
	}
}
