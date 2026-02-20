package user

import (
	"errors"
	"testing"

	"github.com/go-resty/resty/v2"
)

func TestRequestWithRateLimitBackoffRespectsCancellation(t *testing.T) {
	calls := 0
	_, _, _, err := requestWithRateLimitBackoff(
		func() (*resty.Response, error) {
			calls++
			return nil, errors.New("should not execute request when cancelled")
		},
		func() bool { return true },
	)
	if !errors.Is(err, errSearchRunCancelled) {
		t.Fatalf("expected errSearchRunCancelled, got %v", err)
	}
	if calls != 0 {
		t.Fatalf("expected zero request attempts when cancelled, got %d", calls)
	}
}

