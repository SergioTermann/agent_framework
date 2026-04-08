package middleware

import (
	"net"
	"net/http"
	"strconv"

	"agent-framework/gateway/internal/ratelimit"
)

// RateLimit returns middleware that enforces rate limiting.
// Authenticated users are keyed by X-User-ID, others by remote IP.
func RateLimit(limiter ratelimit.Limiter) func(http.Handler) http.Handler {
	return func(next http.Handler) http.Handler {
		return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			// Determine rate limit key
			key := ""
			if uid, ok := r.Context().Value(ContextKeyUserID).(string); ok && uid != "" {
				key = "user:" + uid
			} else {
				ip, _, err := net.SplitHostPort(r.RemoteAddr)
				if err != nil {
					ip = r.RemoteAddr
				}
				key = "ip:" + ip
			}

			res := limiter.Allow(key)

			// Always set rate limit headers
			w.Header().Set("X-RateLimit-Limit", strconv.Itoa(res.Limit))
			w.Header().Set("X-RateLimit-Remaining", strconv.Itoa(res.Remaining))
			w.Header().Set("X-RateLimit-Reset", strconv.FormatInt(res.ResetAt, 10))

			if !res.Allowed {
				w.Header().Set("Retry-After", strconv.FormatInt(res.ResetAt, 10))
				http.Error(w, `{"error":"rate limit exceeded"}`, http.StatusTooManyRequests)
				return
			}

			next.ServeHTTP(w, r)
		})
	}
}
