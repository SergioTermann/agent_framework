package httpapi

import (
	"context"
	"errors"
	"fmt"
	"log"
	"net/http"
	"os"
	"time"

	"agent-framework/services/gateway-go/internal/config"
	"agent-framework/services/gateway-go/internal/gateway"
	"agent-framework/services/gateway-go/internal/middleware"
)

type Server struct {
	httpServer     *http.Server
	gatewayService *gateway.Service
}

func NewServer(cfg config.Config) *Server {
	mux := http.NewServeMux()
	gatewayService := gateway.NewService(cfg)
	registerRoutes(mux, cfg, gatewayService)

	handler := middleware.Chain(
		mux,
		middleware.RequestLogger,
		middleware.Recovery,
		middleware.CORS(cfg.CORSAllowedOrigins),
	)

	return &Server{
		gatewayService: gatewayService,
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
	log.Printf("gateway-go listening on %s", s.httpServer.Addr)
	err := s.httpServer.ListenAndServe()
	if errors.Is(err, http.ErrServerClosed) {
		return nil
	}
	return fmt.Errorf("gateway-go listen failed: %w", err)
}

func (s *Server) Shutdown(ctx context.Context) error {
	err := s.httpServer.Shutdown(ctx)
	s.gatewayService.Close()
	return err
}

func registerRoutes(mux *http.ServeMux, cfg config.Config, gatewayService *gateway.Service) {
	newGatewayRoutes(gatewayService, cfg).register(mux)

	mux.HandleFunc("/health", func(w http.ResponseWriter, r *http.Request) {
		writeJSON(w, http.StatusOK, map[string]any{
			"status":      "ok",
			"service":     "gateway-go",
			"app_backend": cfg.AppBackendURL,
			"ai_backend":  cfg.AIBackendURL,
		})
	})

	mux.HandleFunc("/ready", func(w http.ResponseWriter, r *http.Request) {
		writeJSON(w, http.StatusOK, map[string]any{
			"status":  "ready",
			"service": "gateway-go",
		})
	})

	mux.HandleFunc("/debug/routes", func(w http.ResponseWriter, r *http.Request) {
		writeJSON(w, http.StatusOK, map[string]any{
			"service": "gateway-go",
			"routes": []string{
				"/health",
				"/ready",
				"/debug/routes",
				"/api/gateway/nodes",
				"/api/gateway/online-users",
				"/api/gateway/users/{user_id}/connections",
				"/api/gateway/users/{user_id}/offline-events",
				"/api/gateway/events/{event_id}",
				"/api/gateway/events/{event_id}/ack",
				"/api/gateway/push",
				"/api/gateway/connections",
				"/api/gateway/connections/{connection_id}",
				"/api/gateway/connections/{connection_id}/heartbeat",
				"/api/v1/gateway/nodes",
				"/api/v1/gateway/online-users",
				"/api/v1/gateway/users/{user_id}/connections",
				"/api/v1/gateway/users/{user_id}/offline-events",
				"/api/v1/gateway/events/{event_id}",
				"/api/v1/gateway/events/{event_id}/ack",
				"/api/v1/gateway/push",
				"/api/v1/gateway/connections",
				"/api/v1/gateway/connections/{connection_id}",
				"/api/v1/gateway/connections/{connection_id}/heartbeat",
				"/static/*",
			},
			"notes": []string{
				"gateway control-plane routes are now implemented in Go",
				"legacy /api/gateway aliases are preserved for migration",
				"event ack and delivery status are now tracked in Go",
				"websocket delivery and chat orchestration are still pending",
			},
		})
	})

	staticDir := cfg.StaticDir
	if info, err := os.Stat(staticDir); err == nil && info.IsDir() {
		fileServer := http.FileServer(http.Dir(staticDir))
		mux.Handle("/static/", http.StripPrefix("/static/", fileServer))
	}
}
