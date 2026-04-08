package ratelimit

// Result holds the outcome of a rate limit check.
type Result struct {
	Allowed   bool
	Limit     int   // max requests in the window
	Remaining int   // requests remaining in the window
	ResetAt   int64 // Unix timestamp when the window resets
}

// Limiter defines the rate limiting interface.
type Limiter interface {
	// Allow checks if a request identified by key is allowed.
	Allow(key string) Result
}
