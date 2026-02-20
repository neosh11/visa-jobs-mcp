package contract

import (
	"embed"
	"encoding/json"
	"fmt"
	"sync"
)

//go:embed contract.json
var fs embed.FS

type ToolContract struct {
	Name           string   `json:"name"`
	Description    string   `json:"description"`
	RequiredInputs []string `json:"required_inputs"`
	OptionalInputs []string `json:"optional_inputs,omitempty"`
}

var (
	loadOnce      sync.Once
	loadErr       error
	capabilities  map[string]any
	toolContracts []ToolContract
)

func load() {
	raw, err := fs.ReadFile("contract.json")
	if err != nil {
		loadErr = fmt.Errorf("read embedded contract: %w", err)
		return
	}

	var parsed map[string]any
	if err := json.Unmarshal(raw, &parsed); err != nil {
		loadErr = fmt.Errorf("decode embedded contract: %w", err)
		return
	}
	capabilities = parsed

	toolsAny, ok := parsed["tools"].([]any)
	if !ok {
		toolContracts = []ToolContract{}
		return
	}

	contracts := make([]ToolContract, 0, len(toolsAny))
	for _, entry := range toolsAny {
		obj, ok := entry.(map[string]any)
		if !ok {
			continue
		}
		tc := ToolContract{
			Name:        asString(obj["name"]),
			Description: asString(obj["description"]),
		}
		tc.RequiredInputs = asStringSlice(obj["required_inputs"])
		tc.OptionalInputs = asStringSlice(obj["optional_inputs"])
		if tc.Name == "" {
			continue
		}
		contracts = append(contracts, tc)
	}
	toolContracts = contracts
}

func asString(value any) string {
	s, _ := value.(string)
	return s
}

func asStringSlice(value any) []string {
	values, ok := value.([]any)
	if !ok {
		return nil
	}
	out := make([]string, 0, len(values))
	for _, item := range values {
		if s, ok := item.(string); ok && s != "" {
			out = append(out, s)
		}
	}
	return out
}

func cloneMap(value map[string]any) (map[string]any, error) {
	raw, err := json.Marshal(value)
	if err != nil {
		return nil, err
	}
	var out map[string]any
	if err := json.Unmarshal(raw, &out); err != nil {
		return nil, err
	}
	return out, nil
}

func Capabilities() (map[string]any, error) {
	loadOnce.Do(load)
	if loadErr != nil {
		return nil, loadErr
	}
	return cloneMap(capabilities)
}

func ToolContracts() ([]ToolContract, error) {
	loadOnce.Do(load)
	if loadErr != nil {
		return nil, loadErr
	}
	out := make([]ToolContract, 0, len(toolContracts))
	out = append(out, toolContracts...)
	return out, nil
}
