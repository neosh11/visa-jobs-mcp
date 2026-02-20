package contract

import "testing"

func TestCapabilitiesReturnsDefensiveCopy(t *testing.T) {
	first, err := Capabilities()
	if err != nil {
		t.Fatalf("Capabilities returned error: %v", err)
	}
	originalServer, _ := first["server"].(string)

	first["server"] = "mutated-local-copy"

	second, err := Capabilities()
	if err != nil {
		t.Fatalf("Capabilities returned error: %v", err)
	}
	gotServer, _ := second["server"].(string)
	if gotServer != originalServer {
		t.Fatalf("expected server=%q, got %q", originalServer, gotServer)
	}
}

func TestToolContractsIncludeCoreTools(t *testing.T) {
	tools, err := ToolContracts()
	if err != nil {
		t.Fatalf("ToolContracts returned error: %v", err)
	}
	if len(tools) == 0 {
		t.Fatal("expected embedded tool contracts, got none")
	}

	has := map[string]bool{}
	for _, tool := range tools {
		has[tool.Name] = true
	}

	for _, required := range []string{
		"set_user_preferences",
		"get_user_readiness",
		"start_visa_job_search",
	} {
		if !has[required] {
			t.Fatalf("expected tool contract %q to exist", required)
		}
	}
}
