package config

import (
	"fmt"
	"os"
	"strings"
	"time"
)

type Config struct {
	ListenAddr string

	AppBackendURL      string
	AIBackendURL       string
	StaticDir          string
	StateStorePath     string
	NodeID             string
	Namespace          string
	AuthSecret         string
	RequireAuth        bool
	OfflineRetention   time.Duration
	CompletedRetention time.Duration

	CORSAllowedOrigins []string
}

func Load() Config {
	return Config{
		ListenAddr:         envOrDefault("GATEWAY_GO_LISTEN", ":7000"),
		AppBackendURL:      envOrDefault("APP_BACKEND_URL", "http://127.0.0.1:7001"),
		AIBackendURL:       envOrDefault("AI_BACKEND_URL", "http://127.0.0.1:7002"),
		StaticDir:          envOrDefault("FRONTEND_STATIC_DIR", "frontend/static"),
		StateStorePath:     envOrDefault("GATEWAY_GO_STORE_PATH", "data/gateway_go_store.json"),
		NodeID:             envOrDefault("GATEWAY_GO_NODE_ID", defaultNodeID()),
		Namespace:          envOrDefault("GATEWAY_GO_NAMESPACE", "/gateway"),
		AuthSecret:         resolveAuthSecret(),
		RequireAuth:        envBoolOrDefault("GATEWAY_REQUIRE_AUTH", false),
		OfflineRetention:   envDurationOrDefault("GATEWAY_GO_OFFLINE_RETENTION", 24*time.Hour),
		CompletedRetention: envDurationOrDefault("GATEWAY_GO_COMPLETED_RETENTION", 72*time.Hour),
		CORSAllowedOrigins: splitOrDefault("CORS_ALLOWED_ORIGINS", "*"),
	}
}

func envOrDefault(key, fallback string) string {
	if value := strings.TrimSpace(os.Getenv(key)); value != "" {
		return value
	}
	return fallback
}

func splitOrDefault(key, fallback string) []string {
	raw := envOrDefault(key, fallback)
	parts := strings.Split(raw, ",")
	values := make([]string, 0, len(parts))
	for _, part := range parts {
		part = strings.TrimSpace(part)
		if part != "" {
			values = append(values, part)
		}
	}
	return values
}

func envBoolOrDefault(key string, fallback bool) bool {
	value := strings.TrimSpace(os.Getenv(key))
	if value == "" {
		return fallback
	}
	switch strings.ToLower(value) {
	case "1", "true", "yes", "on":
		return true
	case "0", "false", "no", "off":
		return false
	default:
		return fallback
	}
}

func resolveAuthSecret() string {
	if value := strings.TrimSpace(os.Getenv("GATEWAY_AUTH_SECRET")); value != "" {
		return value
	}
	if value := strings.TrimSpace(os.Getenv("APP_AUTH_SECRET")); value != "" {
		return value
	}
	if value := strings.TrimSpace(os.Getenv("JWT_SECRET_KEY")); value != "" {
		return value
	}
	if value := strings.TrimSpace(os.Getenv("SECRET_KEY")); value != "" {
		return value
	}
	return "change-me-in-production"
}

func envDurationOrDefault(key string, fallback time.Duration) time.Duration {
	value := strings.TrimSpace(os.Getenv(key))
	if value == "" {
		return fallback
	}
	duration, err := time.ParseDuration(value)
	if err != nil {
		return fallback
	}
	return duration
}

func defaultNodeID() string {
	hostname, err := os.Hostname()
	if err != nil || strings.TrimSpace(hostname) == "" {
		hostname = "unknown"
	}
	return fmt.Sprintf("gw-%s-%d", hostname, time.Now().Unix())
}
