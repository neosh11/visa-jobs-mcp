package user

import "testing"

func TestListOrEmptySupportsStringSlices(t *testing.T) {
	values := listOrEmpty([]string{"a", "b"})
	if len(values) != 2 {
		t.Fatalf("expected 2 values, got %d", len(values))
	}
	if got, _ := values[0].(string); got != "a" {
		t.Fatalf("expected first value 'a', got %#v", values[0])
	}
}
