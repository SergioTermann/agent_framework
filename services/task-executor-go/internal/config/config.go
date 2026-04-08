package config

import (
	"os"
	"strconv"
	"strings"
)

type Config struct {
	ListenAddr string
	Workers    int
	StorePath  string
}

func Load() Config {
	return Config{
		ListenAddr: envOrDefault("TASK_EXECUTOR_LISTEN", ":7003"),
		Workers:    envIntOrDefault("TASK_EXECUTOR_WORKERS", 64),
		StorePath:  envOrDefault("TASK_EXECUTOR_STORE_PATH", "data/task_executor_store.json"),
	}
}

func envOrDefault(key, fallback string) string {
	if value := strings.TrimSpace(os.Getenv(key)); value != "" {
		return value
	}
	return fallback
}

func envIntOrDefault(key string, fallback int) int {
	if value := strings.TrimSpace(os.Getenv(key)); value != "" {
		if parsed, err := strconv.Atoi(value); err == nil {
			return parsed
		}
	}
	return fallback
}
