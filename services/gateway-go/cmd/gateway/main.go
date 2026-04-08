package main

import (
	"context"
	"log"
	"os"
	"os/signal"
	"syscall"
	"time"

	"agent-framework/services/gateway-go/internal/config"
	"agent-framework/services/gateway-go/internal/httpapi"
)

func main() {
	cfg := config.Load()
	srv := httpapi.NewServer(cfg)

	log.Printf("gateway-go starting")
	log.Printf("  listen=%s", cfg.ListenAddr)
	log.Printf("  app_backend=%s", cfg.AppBackendURL)
	log.Printf("  ai_backend=%s", cfg.AIBackendURL)
	log.Printf("  static_dir=%s", cfg.StaticDir)

	go func() {
		sigCh := make(chan os.Signal, 1)
		signal.Notify(sigCh, syscall.SIGINT, syscall.SIGTERM)
		sig := <-sigCh
		log.Printf("gateway-go received %v, shutting down", sig)

		ctx, cancel := context.WithTimeout(context.Background(), 15*time.Second)
		defer cancel()
		if err := srv.Shutdown(ctx); err != nil {
			log.Printf("gateway-go shutdown error: %v", err)
		}
	}()

	if err := srv.ListenAndServe(); err != nil {
		log.Fatal(err)
	}
}
