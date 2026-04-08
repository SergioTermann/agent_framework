package config

import (
	"os"
	"strconv"
	"strings"
)

type Config struct {
	ListenAddr string

	PythonBackendURL       string
	GatewayControlPlaneURL string

	JWTSecretKey string
	SecretKey    string
	StaticDir    string

	CORSAllowedOrigins []string

	RateLimitAPIMax     int
	RateLimitAPIWindow  int
	RateLimitUserMax    int
	RateLimitUserWindow int
}

func Load() *Config {
	return &Config{
		ListenAddr:             envOrDefault("GATEWAY_LISTEN", ":5000"),
		PythonBackendURL:       envOrDefault("PYTHON_BACKEND_URL", "http://127.0.0.1:5001"),
		GatewayControlPlaneURL: envOrDefault("GATEWAY_CONTROL_PLANE_URL", "http://127.0.0.1:7000"),
		JWTSecretKey:           envOrDefault("JWT_SECRET_KEY", "your-jwt-secret-key"),
		SecretKey:              envOrDefault("SECRET_KEY", "agent-framework-secret-key-change-in-production"),
		StaticDir:              envOrDefault("STATIC_DIR", "src/agent_framework/static"),
		CORSAllowedOrigins:     splitOrDefault("CORS_ALLOWED_ORIGINS", "*"),
		RateLimitAPIMax:        envIntOrDefault("RATE_LIMIT_API_MAX", 100),
		RateLimitAPIWindow:     envIntOrDefault("RATE_LIMIT_API_WINDOW", 60),
		RateLimitUserMax:       envIntOrDefault("RATE_LIMIT_USER_MAX", 1000),
		RateLimitUserWindow:    envIntOrDefault("RATE_LIMIT_USER_WINDOW", 3600),
	}
}

func envOrDefault(key, fallback string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return fallback
}

func envIntOrDefault(key string, fallback int) int {
	if v := os.Getenv(key); v != "" {
		if n, err := strconv.Atoi(v); err == nil {
			return n
		}
	}
	return fallback
}

func splitOrDefault(key, fallback string) []string {
	v := os.Getenv(key)
	if v == "" {
		v = fallback
	}
	parts := strings.Split(v, ",")
	out := make([]string, 0, len(parts))
	for _, p := range parts {
		p = strings.TrimSpace(p)
		if p != "" {
			out = append(out, p)
		}
	}
	return out
}
