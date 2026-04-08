package config

import (
	"os"
	"strings"
)

type Config struct {
	ListenAddr    string
	AIBackendURL  string
	AuthSecret    string
	AuthStorePath string
}

func Load() Config {
	return Config{
		ListenAddr:    envOrDefault("APP_GO_LISTEN", ":7001"),
		AIBackendURL:  envOrDefault("AI_BACKEND_URL", "http://127.0.0.1:7002"),
		AuthSecret:    envOrDefault("APP_AUTH_SECRET", "change-me-in-production"),
		AuthStorePath: envOrDefault("APP_AUTH_STORE_PATH", "data/app_go_auth_store.json"),
	}
}

func envOrDefault(key, fallback string) string {
	if value := strings.TrimSpace(os.Getenv(key)); value != "" {
		return value
	}
	return fallback
}
