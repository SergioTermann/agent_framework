package main

import (
	"context"
	"log"
	"net/http"
	"os"
	"os/signal"
	"syscall"
	"time"

	"agent-framework/gateway/internal/auth"
	"agent-framework/gateway/internal/config"
	"agent-framework/gateway/internal/middleware"
	"agent-framework/gateway/internal/proxy"
	"agent-framework/gateway/internal/ratelimit"

	"github.com/go-chi/chi/v5"
	chimw "github.com/go-chi/chi/v5/middleware"
)

func main() {
	cfg := config.Load()

	log.Printf("Go API Gateway starting")
	log.Printf("  Listen:        %s", cfg.ListenAddr)
	log.Printf("  App backend:   %s", cfg.PythonBackendURL)
	log.Printf("  Control plane: %s", cfg.GatewayControlPlaneURL)
	log.Printf("  Static:        %s", cfg.StaticDir)

	jwtVerifier := auth.NewVerifier(cfg.JWTSecretKey)
	apiLimiter := ratelimit.NewSlidingWindow(cfg.RateLimitAPIMax, cfg.RateLimitAPIWindow)
	defer apiLimiter.Stop()

	r := chi.NewRouter()
	r.Use(chimw.RequestID)
	r.Use(middleware.Logger)
	r.Use(middleware.Recovery)
	r.Use(middleware.NewCORS(cfg.CORSAllowedOrigins).Handler)

	r.Get("/health", func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusOK)
		_, _ = w.Write([]byte(`{"status":"ok","service":"go-gateway"}`))
	})

	fileServer := http.StripPrefix("/static/", http.FileServer(http.Dir(cfg.StaticDir)))
	r.Handle("/static/*", fileServer)

	appProxyHandler := proxy.Handler(cfg.PythonBackendURL)
	controlPlaneProxyHandler := proxy.Handler(cfg.GatewayControlPlaneURL)

	r.Group(func(r chi.Router) {
		r.Use(middleware.Auth(jwtVerifier))
		r.Use(middleware.RateLimit(apiLimiter))
		r.Handle("/api/gateway", controlPlaneProxyHandler)
		r.Handle("/api/gateway/*", controlPlaneProxyHandler)
		r.Handle("/api/v1/gateway", controlPlaneProxyHandler)
		r.Handle("/api/v1/gateway/*", controlPlaneProxyHandler)
		r.Handle("/*", appProxyHandler)
	})

	srv := &http.Server{
		Addr:         cfg.ListenAddr,
		Handler:      r,
		ReadTimeout:  30 * time.Second,
		WriteTimeout: 120 * time.Second,
		IdleTimeout:  120 * time.Second,
	}

	go func() {
		sigCh := make(chan os.Signal, 1)
		signal.Notify(sigCh, syscall.SIGINT, syscall.SIGTERM)
		sig := <-sigCh
		log.Printf("Received %v, shutting down gracefully...", sig)

		ctx, cancel := context.WithTimeout(context.Background(), 15*time.Second)
		defer cancel()
		if err := srv.Shutdown(ctx); err != nil {
			log.Printf("HTTP server shutdown error: %v", err)
		}
	}()

	log.Printf("Gateway listening on %s", cfg.ListenAddr)
	if err := srv.ListenAndServe(); err != nil && err != http.ErrServerClosed {
		log.Fatalf("Server failed: %v", err)
	}
	log.Println("Gateway stopped")
}
