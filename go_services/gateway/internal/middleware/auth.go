package middleware

import (
	"context"
	"net/http"
	"strings"

	"agent-framework/gateway/internal/auth"
)

type contextKey string

const (
	ContextKeyUserID   contextKey = "user_id"
	ContextKeyUserRole contextKey = "user_role"
)

// publicPaths are exact paths that skip JWT auth.
var publicPaths = map[string]bool{
	"/api/auth/login":    true,
	"/api/auth/register": true,
	"/health":            true,
}

// Auth returns middleware that validates JWT tokens.
// Public paths and non-API paths skip validation.
func Auth(verifier *auth.Verifier) func(http.Handler) http.Handler {
	return func(next http.Handler) http.Handler {
		return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			path := r.URL.Path

			// Skip auth for public paths
			if publicPaths[path] {
				next.ServeHTTP(w, r)
				return
			}

			// Skip auth for static files
			if strings.HasPrefix(path, "/static/") {
				next.ServeHTTP(w, r)
				return
			}

			// Skip auth for non-API paths (HTML pages served by Flask)
			if !strings.HasPrefix(path, "/api/") {
				next.ServeHTTP(w, r)
				return
			}

			// Extract Bearer token
			header := r.Header.Get("Authorization")
			if header == "" {
				http.Error(w, `{"error":"authorization token required"}`, http.StatusUnauthorized)
				return
			}

			parts := strings.SplitN(header, " ", 2)
			if len(parts) != 2 || !strings.EqualFold(parts[0], "Bearer") {
				http.Error(w, `{"error":"invalid authorization header format"}`, http.StatusUnauthorized)
				return
			}

			claims, err := verifier.Verify(parts[1])
			if err != nil {
				status := http.StatusUnauthorized
				msg := `{"error":"` + err.Error() + `"}`
				http.Error(w, msg, status)
				return
			}

			// Set headers for Flask backend
			r.Header.Set("X-User-ID", claims.UserID)
			r.Header.Set("X-User-Role", claims.Role)

			// Also store in context for downstream middleware (e.g. rate limiter)
			ctx := context.WithValue(r.Context(), ContextKeyUserID, claims.UserID)
			ctx = context.WithValue(ctx, ContextKeyUserRole, claims.Role)
			next.ServeHTTP(w, r.WithContext(ctx))
		})
	}
}
