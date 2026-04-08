package ratelimit

import (
	"sync"
	"time"
)

// SlidingWindowLimiter implements a sliding window rate limiter
// semantically consistent with the Python SlidingWindowLimiter.
type SlidingWindowLimiter struct {
	maxRequests int
	windowSecs  int64

	mu       sync.Mutex
	requests map[string][]int64 // key → sorted list of request Unix timestamps (seconds)

	stopCh chan struct{}
}

// NewSlidingWindow creates a limiter that allows maxRequests within windowSecs.
// It starts a background goroutine to clean up expired entries.
func NewSlidingWindow(maxRequests, windowSecs int) *SlidingWindowLimiter {
	l := &SlidingWindowLimiter{
		maxRequests: maxRequests,
		windowSecs:  int64(windowSecs),
		requests:    make(map[string][]int64),
		stopCh:      make(chan struct{}),
	}
	go l.cleanup()
	return l
}

// Allow checks if a request for key is within limits.
func (l *SlidingWindowLimiter) Allow(key string) Result {
	now := time.Now().Unix()
	windowStart := now - l.windowSecs

	l.mu.Lock()
	defer l.mu.Unlock()

	// Remove expired timestamps (before window start)
	reqs := l.requests[key]
	idx := 0
	for idx < len(reqs) && reqs[idx] <= windowStart {
		idx++
	}
	reqs = reqs[idx:]

	resetAt := now + l.windowSecs

	if len(reqs) >= l.maxRequests {
		l.requests[key] = reqs
		return Result{Allowed: false, Limit: l.maxRequests, Remaining: 0, ResetAt: resetAt}
	}

	// Allow and record
	reqs = append(reqs, now)
	l.requests[key] = reqs
	return Result{
		Allowed:   true,
		Limit:     l.maxRequests,
		Remaining: l.maxRequests - len(reqs),
		ResetAt:   resetAt,
	}
}

// Stop terminates the background cleanup goroutine.
func (l *SlidingWindowLimiter) Stop() {
	close(l.stopCh)
}

// cleanup runs periodically to remove keys with only expired timestamps.
func (l *SlidingWindowLimiter) cleanup() {
	ticker := time.NewTicker(60 * time.Second)
	defer ticker.Stop()
	for {
		select {
		case <-l.stopCh:
			return
		case <-ticker.C:
			now := time.Now().Unix()
			windowStart := now - l.windowSecs

			l.mu.Lock()
			for key, reqs := range l.requests {
				idx := 0
				for idx < len(reqs) && reqs[idx] <= windowStart {
					idx++
				}
				if idx == len(reqs) {
					delete(l.requests, key)
				} else if idx > 0 {
					l.requests[key] = reqs[idx:]
				}
			}
			l.mu.Unlock()
		}
	}
}
