package mcp

import (
	"testing"

	"github.com/neosh11/visa-jobs-mcp/internal/contract"
)

func TestAllContractToolsHaveHandlers(t *testing.T) {
	tools, err := contract.ToolContracts()
	if err != nil {
		t.Fatalf("ToolContracts failed: %v", err)
	}
	for _, tc := range tools {
		if _, ok := implementedToolHandlers[tc.Name]; !ok {
			t.Fatalf("missing handler for contract tool %q", tc.Name)
		}
	}
}
