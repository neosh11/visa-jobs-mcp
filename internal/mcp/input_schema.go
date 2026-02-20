package mcp

import (
	"slices"

	"github.com/neosh11/visa-jobs-mcp/internal/contract"
)

func buildInputSchema(tool contract.ToolContract) map[string]any {
	properties := map[string]any{}
	seen := map[string]struct{}{}

	for _, name := range tool.RequiredInputs {
		if _, ok := seen[name]; ok {
			continue
		}
		properties[name] = inputPropertySchema(name)
		seen[name] = struct{}{}
	}
	for _, name := range tool.OptionalInputs {
		if _, ok := seen[name]; ok {
			continue
		}
		properties[name] = inputPropertySchema(name)
		seen[name] = struct{}{}
	}

	required := append([]string{}, tool.RequiredInputs...)
	slices.Sort(required)

	return map[string]any{
		"type":                 "object",
		"properties":           properties,
		"required":             required,
		"additionalProperties": true,
	}
}

func inputPropertySchema(name string) map[string]any {
	if schema, ok := arrayStringFields[name]; ok {
		return schema
	}
	if schema, ok := booleanFields[name]; ok {
		return schema
	}
	if schema, ok := integerFields[name]; ok {
		return schema
	}
	if schema, ok := stringFields[name]; ok {
		return schema
	}
	return map[string]any{}
}

var stringFields = map[string]map[string]any{
	"applied_at_utc":  {"type": "string"},
	"command":         {"type": "string"},
	"company_name":    {"type": "string"},
	"context":         {"type": "string"},
	"dataset_path":    {"type": "string"},
	"job_title":       {"type": "string"},
	"job_url":         {"type": "string"},
	"location":        {"type": "string"},
	"manifest_path":   {"type": "string"},
	"note":            {"type": "string"},
	"performance_url": {"type": "string"},
	"reason":          {"type": "string"},
	"recipient_email": {"type": "string"},
	"recipient_name":  {"type": "string"},
	"recipient_title": {"type": "string"},
	"result_id":       {"type": "string"},
	"run_id":          {"type": "string"},
	"session_id":      {"type": "string"},
	"site":            {"type": "string"},
	"source":          {"type": "string"},
	"stage":           {"type": "string"},
	"strictness_mode": {"type": "string"},
	"tone":            {"type": "string"},
	"user_id":         {"type": "string"},
}

var integerFields = map[string]map[string]any{
	"cursor":             {"type": "integer"},
	"days_remaining":     {"type": "integer"},
	"hours_old":          {"type": "integer"},
	"ignored_company_id": {"type": "integer"},
	"ignored_job_id":     {"type": "integer"},
	"job_id":             {"type": "integer"},
	"limit":              {"type": "integer"},
	"line_id":            {"type": "integer"},
	"max_returned":       {"type": "integer"},
	"max_scan_results":   {"type": "integer"},
	"offset":             {"type": "integer"},
	"results_wanted":     {"type": "integer"},
	"saved_job_id":       {"type": "integer"},
	"scan_multiplier":    {"type": "integer"},
}

var booleanFields = map[string]map[string]any{
	"clear_all_for_user":         {"type": "boolean"},
	"confirm":                    {"type": "boolean"},
	"refresh_session":            {"type": "boolean"},
	"require_description_signal": {"type": "boolean"},
	"willing_to_relocate":        {"type": "boolean"},
}

var arrayStringFields = map[string]map[string]any{
	"preferred_visa_types": {
		"type":  "array",
		"items": map[string]any{"type": "string"},
	},
	"work_modes": {
		"type":  "array",
		"items": map[string]any{"type": "string"},
	},
}
