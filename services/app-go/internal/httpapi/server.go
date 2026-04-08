package httpapi

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"log"
	"net/http"
	"time"

	"agent-framework/services/app-go/internal/auth"
	"agent-framework/services/app-go/internal/config"
	"agent-framework/services/app-go/internal/middleware"
)

type Server struct {
	httpServer *http.Server
}

func NewServer(cfg config.Config) *Server {
	mux := http.NewServeMux()
	registerRoutes(mux, cfg)

	handler := middleware.Chain(
		mux,
		middleware.RequestLogger,
		middleware.Recovery,
	)

	return &Server{
		httpServer: &http.Server{
			Addr:              cfg.ListenAddr,
			Handler:           handler,
			ReadHeaderTimeout: 10 * time.Second,
			ReadTimeout:       30 * time.Second,
			WriteTimeout:      120 * time.Second,
			IdleTimeout:       120 * time.Second,
		},
	}
}

func (s *Server) ListenAndServe() error {
	log.Printf("app-go listening on %s", s.httpServer.Addr)
	err := s.httpServer.ListenAndServe()
	if errors.Is(err, http.ErrServerClosed) {
		return nil
	}
	return fmt.Errorf("app-go listen failed: %w", err)
}

func (s *Server) Shutdown(ctx context.Context) error {
	return s.httpServer.Shutdown(ctx)
}

func registerRoutes(mux *http.ServeMux, cfg config.Config) {
	authStore := mustAuthStore(cfg.AuthStorePath)
	authService := auth.NewService(authStore, cfg.AuthSecret)
	newAuthRoutes(authService).register(mux)

	mux.HandleFunc("/health", func(w http.ResponseWriter, r *http.Request) {
		writeJSON(w, http.StatusOK, map[string]any{
			"status":     "ok",
			"service":    "app-go",
			"ai_backend": cfg.AIBackendURL,
		})
	})

	mux.HandleFunc("/api/v1/system/language-plan", func(w http.ResponseWriter, r *http.Request) {
		writeJSON(w, http.StatusOK, map[string]any{
			"service": "app-go",
			"control_plane": []string{
				"auth",
				"applications",
				"conversations",
				"api_keys",
				"webhooks",
			},
			"delegates_to_ai": []string{
				"unified_chat",
				"context_building",
				"multi_agent",
			},
		})
	})

	mux.HandleFunc("/api/v1/system/migration-status", func(w http.ResponseWriter, r *http.Request) {
		writeJSON(w, http.StatusOK, map[string]any{
			"service": "app-go",
			"status":  "bootstrap",
			"notes": []string{
				"control-plane service skeleton is active",
				"legacy Python APIs are not migrated yet",
			},
		})
	})
}

func writeJSON(w http.ResponseWriter, status int, payload any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(payload)
}

func mustAuthStore(path string) *auth.Store {
	store, err := auth.NewFileStore(path)
	if err != nil {
		panic(err)
	}
	return store
}
