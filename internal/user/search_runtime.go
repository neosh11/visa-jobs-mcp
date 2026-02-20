package user

import "errors"

var errSearchRunCancelled = errors.New("search run cancelled")

var linkedInClientFactory = func() linkedInClient {
	return newLiveLinkedInClient()
}
