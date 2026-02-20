package user

import "testing"

func TestNewSiteClientRejectsUnsupportedSite(t *testing.T) {
	if _, err := newSiteClient("indeed"); err == nil {
		t.Fatal("expected error for unsupported site")
	}
}
