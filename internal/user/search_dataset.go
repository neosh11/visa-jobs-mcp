package user

import (
	"encoding/csv"
	"fmt"
	"os"
	"path/filepath"
	"strconv"
	"strings"
	"sync"
	"time"
)

var datasetCacheMu sync.Mutex

type datasetCacheEntry struct {
	Path    string
	ModTime time.Time
	Data    companyDataset
}

var datasetCache = map[string]datasetCacheEntry{}

var datasetColumnAliases = map[string][]string{
	"company_tier":    {"company_tier", "size"},
	"company_name":    {"company_name", "employer"},
	"h1b":             {"h1b", "h-1b"},
	"h1b1_chile":      {"h1b1_chile", "h-1b1 chile"},
	"h1b1_singapore":  {"h1b1_singapore", "h-1b1 singapore"},
	"e3_australian":   {"e3_australian", "e-3 australian"},
	"green_card":      {"green_card", "green card"},
	"email_1":         {"email_1"},
	"contact_1":       {"contact_1"},
	"contact_1_title": {"contact_1_title"},
	"contact_1_phone": {"contact_1_phone"},
	"email_2":         {"email_2"},
	"contact_2":       {"contact_2"},
	"contact_2_title": {"contact_2_title"},
	"contact_2_phone": {"contact_2_phone"},
	"email_3":         {"email_3"},
	"contact_3":       {"contact_3"},
	"contact_3_title": {"contact_3_title"},
	"contact_3_phone": {"contact_3_phone"},
}

func datasetPathOrDefault(raw string) string {
	path := strings.TrimSpace(raw)
	if path == "" {
		path = strings.TrimSpace(os.Getenv("VISA_COMPANY_DATASET_PATH"))
	}
	if path != "" {
		return path
	}

	// Prefer explicit project-local path when available.
	if _, err := os.Stat(defaultDatasetPath); err == nil {
		return defaultDatasetPath
	}

	// Fallbacks for packaged installs (Homebrew/tarball layouts).
	exePath, err := os.Executable()
	if err != nil {
		return defaultDatasetPath
	}
	candidates := datasetFallbackCandidates(exePath)
	for _, candidate := range candidates {
		if _, err := os.Stat(candidate); err == nil {
			return candidate
		}
	}
	return defaultDatasetPath
}

func datasetFallbackCandidates(exePath string) []string {
	exeDir := filepath.Dir(exePath)
	return []string{
		filepath.Join(exeDir, "data", "companies.csv"),
		filepath.Join(exeDir, "..", "data", "companies.csv"),
		filepath.Join(exeDir, "..", "share", "visa-jobs-mcp", "data", "companies.csv"),
		filepath.Join(exeDir, "..", "share", "visa-jobs-mcp", "companies.csv"),
	}
}

func parseIntCSV(text string) int {
	value, err := strconv.Atoi(strings.TrimSpace(text))
	if err != nil {
		return 0
	}
	return value
}

func normalizedHeaderMap(headers []string) map[string]int {
	out := map[string]int{}
	for idx, raw := range headers {
		key := strings.ToLower(strings.TrimSpace(raw))
		out[key] = idx
	}
	return out
}

func findColumnIndex(indexByHeader map[string]int, aliases []string) int {
	for _, alias := range aliases {
		if idx, ok := indexByHeader[strings.ToLower(strings.TrimSpace(alias))]; ok {
			return idx
		}
	}
	return -1
}

func readCSVColumn(row []string, idx int) string {
	if idx < 0 || idx >= len(row) {
		return ""
	}
	return strings.TrimSpace(row[idx])
}

func buildContactsFromRow(row []string, idx map[string]int) []map[string]any {
	contacts := []map[string]any{}
	for _, n := range []string{"1", "2", "3"} {
		name := readCSVColumn(row, idx["contact_"+n])
		title := readCSVColumn(row, idx["contact_"+n+"_title"])
		email := readCSVColumn(row, idx["email_"+n])
		phone := readCSVColumn(row, idx["contact_"+n+"_phone"])
		if name == "" && title == "" && email == "" && phone == "" {
			continue
		}
		contacts = append(contacts, map[string]any{
			"name":  name,
			"title": title,
			"email": email,
			"phone": phone,
		})
	}
	return contacts
}

func loadCompanyDataset(datasetPath string) (companyDataset, error) {
	path := datasetPathOrDefault(datasetPath)
	info, err := os.Stat(path)
	if err != nil {
		return companyDataset{}, fmt.Errorf("dataset not found at '%s': %w", path, err)
	}

	datasetCacheMu.Lock()
	if cached, ok := datasetCache[path]; ok && cached.ModTime.Equal(info.ModTime().UTC()) {
		data := cached.Data
		datasetCacheMu.Unlock()
		return data, nil
	}
	datasetCacheMu.Unlock()

	file, err := os.Open(path)
	if err != nil {
		return companyDataset{}, fmt.Errorf("open dataset '%s': %w", path, err)
	}
	defer file.Close()

	reader := csv.NewReader(file)
	reader.FieldsPerRecord = -1
	header, err := reader.Read()
	if err != nil {
		return companyDataset{}, fmt.Errorf("read dataset header: %w", err)
	}
	headerIndex := normalizedHeaderMap(header)

	canonicalIndex := map[string]int{}
	for canonical, aliases := range datasetColumnAliases {
		canonicalIndex[canonical] = findColumnIndex(headerIndex, aliases)
	}
	required := []string{"company_name", "h1b", "h1b1_chile", "h1b1_singapore", "e3_australian", "green_card"}
	missing := []string{}
	for _, key := range required {
		if canonicalIndex[key] < 0 {
			missing = append(missing, key)
		}
	}
	if len(missing) > 0 {
		return companyDataset{}, fmt.Errorf("dataset missing required columns: %s", strings.Join(missing, ", "))
	}

	out := companyDataset{
		ByNormalizedCompany: map[string]companyDatasetRecord{},
	}
	for {
		row, err := reader.Read()
		if err != nil {
			break
		}
		companyName := readCSVColumn(row, canonicalIndex["company_name"])
		normalized := normalizeCompanyName(companyName)
		if normalized == "" {
			continue
		}

		record := companyDatasetRecord{
			CompanyName:      companyName,
			CompanyTier:      readCSVColumn(row, canonicalIndex["company_tier"]),
			H1B:              parseIntCSV(readCSVColumn(row, canonicalIndex["h1b"])),
			H1B1Chile:        parseIntCSV(readCSVColumn(row, canonicalIndex["h1b1_chile"])),
			H1B1Singapore:    parseIntCSV(readCSVColumn(row, canonicalIndex["h1b1_singapore"])),
			E3Australian:     parseIntCSV(readCSVColumn(row, canonicalIndex["e3_australian"])),
			GreenCard:        parseIntCSV(readCSVColumn(row, canonicalIndex["green_card"])),
			EmployerContacts: buildContactsFromRow(row, canonicalIndex),
		}
		record.TotalVisas = record.H1B + record.H1B1Chile + record.H1B1Singapore + record.E3Australian + record.GreenCard

		existing, exists := out.ByNormalizedCompany[normalized]
		if !exists || record.TotalVisas > existing.TotalVisas {
			out.ByNormalizedCompany[normalized] = record
		}
		out.Rows++
	}

	datasetCacheMu.Lock()
	datasetCache[path] = datasetCacheEntry{
		Path:    path,
		ModTime: info.ModTime().UTC(),
		Data:    out,
	}
	datasetCacheMu.Unlock()
	return out, nil
}

func clearDatasetCache(datasetPath string) {
	path := datasetPathOrDefault(datasetPath)
	datasetCacheMu.Lock()
	delete(datasetCache, path)
	datasetCacheMu.Unlock()
}

func visaCountsFromRecord(record companyDatasetRecord) map[string]int {
	return map[string]int{
		"h1b":            record.H1B,
		"h1b1_chile":     record.H1B1Chile,
		"h1b1_singapore": record.H1B1Singapore,
		"e3_australian":  record.E3Australian,
		"green_card":     record.GreenCard,
		"total_visas":    record.TotalVisas,
	}
}

func desiredVisaCount(record companyDatasetRecord, desired []string) int {
	total := 0
	for _, visa := range desired {
		switch visa {
		case "h1b":
			total += record.H1B
		case "h1b1_chile":
			total += record.H1B1Chile
		case "h1b1_singapore":
			total += record.H1B1Singapore
		case "e3_australian":
			total += record.E3Australian
		case "green_card":
			total += record.GreenCard
		}
	}
	return total
}
