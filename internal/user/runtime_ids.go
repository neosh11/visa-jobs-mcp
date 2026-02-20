package user

import (
	"crypto/rand"
	"encoding/hex"
)

func newRunID() string {
	buf := make([]byte, 12)
	if _, err := rand.Read(buf); err == nil {
		return hex.EncodeToString(buf)
	}
	// Fallback to timestamp-based entropy if crypto/rand is unavailable.
	return hex.EncodeToString([]byte(utcNowISO()))
}
