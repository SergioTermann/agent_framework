package main

import (
	"context"
	"log"
	"os"
	"os/signal"
	"syscall"
	"time"

	"agent-framework/services/task-executor-go/internal/config"
	"agent-framework/services/task-executor-go/internal/httpapi"
)

func main() {
	cfg := config.Load()
	srv := httpapi.NewServer(cfg)

	log.Printf("task-executor-go starting")
	log.Printf("  listen=%s", cfg.ListenAddr)
	log.Printf("  workers=%d", cfg.Workers)

	go func() {
		sigCh := make(chan os.Signal, 1)
		signal.Notify(sigCh, syscall.SIGINT, syscall.SIGTERM)
		sig := <-sigCh
		log.Printf("task-executor-go received %v, shutting down", sig)

		_, cancel := context.WithTimeout(context.Background(), 15*time.Second)
		defer cancel()
		srv.Shutdown()
	}()

	if err := srv.ListenAndServe(); err != nil {
		log.Fatal(err)
	}
}
