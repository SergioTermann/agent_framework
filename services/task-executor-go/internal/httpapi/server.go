package httpapi

import (
	"encoding/json"
	"net/http"
	"strings"
	"time"

	"agent-framework/services/task-executor-go/internal/executor"
	"agent-framework/services/task-executor-go/internal/config"
	"agent-framework/services/task-executor-go/internal/middleware"
)

type Server struct {
	httpServer *http.Server
	executor   *executor.Service
}

func NewServer(cfg config.Config) *Server {
	svc := executor.NewService(cfg.Workers)
	mux := http.NewServeMux()

	s := &Server{executor: svc}
	s.registerRoutes(mux, cfg)

	handler := middleware.Chain(
		mux,
		middleware.RequestLogger,
		middleware.Recovery,
	)

	s.httpServer = &http.Server{
		Addr:              cfg.ListenAddr,
		Handler:           handler,
		ReadHeaderTimeout: 10 * time.Second,
		ReadTimeout:       30 * time.Second,
		WriteTimeout:      120 * time.Second,
		IdleTimeout:       120 * time.Second,
	}
	return s
}

func (s *Server) ListenAndServe() error {
	err := s.httpServer.ListenAndServe()
	if err == http.ErrServerClosed {
		return nil
	}
	return err
}

func (s *Server) Shutdown() {
	s.executor.Shutdown()
}

func (s *Server) registerRoutes(mux *http.ServeMux, cfg config.Config) {
	mux.HandleFunc("/submit", s.handleSubmit)
	mux.HandleFunc("/status", s.handleLegacyStatus)
	mux.HandleFunc("/tasks", s.handleListTasks)
	mux.HandleFunc("/tasks/", s.handleTaskRouter)
	mux.HandleFunc("/statistics", s.handleStatistics)
	mux.HandleFunc("/clear", s.handleClear)
	mux.HandleFunc("/health", s.handleHealth)
}

func (s *Server) handleSubmit(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
		return
	}

	var payload map[string]any
	if err := json.NewDecoder(r.Body).Decode(&payload); err != nil {
		http.Error(w, err.Error(), http.StatusBadRequest)
		return
	}

	taskType := executor.AsString(payload["task_type"], executor.AsString(payload["type"], ""))
	if taskType == "" {
		http.Error(w, "task_type is required", http.StatusBadRequest)
		return
	}

	params := map[string]any{}
	if rawParams, ok := payload["params"].(map[string]any); ok {
		params = rawParams
	} else if rawPayload, ok := payload["payload"].(map[string]any); ok {
		params = rawPayload
	}

	priority := executor.AsInt(payload["priority"], 1)
	task := s.executor.Submit(taskType, params, priority)
	writeJSON(w, http.StatusOK, map[string]any{
		"task_id": task.ID,
		"status":  task.Status,
		"backend": "go",
	})
}

func (s *Server) handleTaskRouter(w http.ResponseWriter, r *http.Request) {
	path := strings.TrimPrefix(r.URL.Path, "/tasks/")
	if path == "" || path == r.URL.Path {
		if r.Method == http.MethodGet {
			s.handleListTasks(w, r)
			return
		}
		http.NotFound(w, r)
		return
	}

	parts := strings.Split(strings.Trim(path, "/"), "/")
	taskID := parts[0]

	if len(parts) == 1 && r.Method == http.MethodGet {
		s.handleGetTask(w, r, taskID)
		return
	}
	if len(parts) == 2 {
		switch parts[1] {
		case "status":
			if r.Method == http.MethodGet {
				s.handleGetTaskStatus(w, r, taskID)
				return
			}
		case "result":
			if r.Method == http.MethodGet {
				s.handleGetTaskResult(w, r, taskID)
				return
			}
		case "cancel":
			if r.Method == http.MethodPost {
				s.handleCancelTask(w, r, taskID)
				return
			}
		}
	}
	http.NotFound(w, r)
}

func (s *Server) handleGetTask(w http.ResponseWriter, _ *http.Request, taskID string) {
	task, ok := s.executor.Get(taskID)
	if !ok {
		http.Error(w, "task not found", http.StatusNotFound)
		return
	}
	writeJSON(w, http.StatusOK, task)
}

func (s *Server) handleGetTaskStatus(w http.ResponseWriter, _ *http.Request, taskID string) {
	task, ok := s.executor.Get(taskID)
	if !ok {
		http.Error(w, "task not found", http.StatusNotFound)
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{
		"task_id": task.ID,
		"status":  task.Status,
		"backend": task.Backend,
	})
}

func (s *Server) handleGetTaskResult(w http.ResponseWriter, _ *http.Request, taskID string) {
	task, ok := s.executor.Get(taskID)
	if !ok {
		http.Error(w, "task not found", http.StatusNotFound)
		return
	}

	switch task.Status {
	case "queued", "running":
		writeJSON(w, http.StatusBadRequest, map[string]any{"error": "task not finished", "status": task.Status})
	case "failed":
		writeJSON(w, http.StatusInternalServerError, map[string]any{"error": "task failed", "message": task.Error, "status": task.Status})
	case "cancelled":
		writeJSON(w, http.StatusBadRequest, map[string]any{"error": "task cancelled", "status": task.Status})
	default:
		writeJSON(w, http.StatusOK, map[string]any{
			"task_id": task.ID,
			"status":  task.Status,
			"result":  task.Result,
			"backend": task.Backend,
		})
	}
}

func (s *Server) handleCancelTask(w http.ResponseWriter, _ *http.Request, taskID string) {
	if !s.executor.Cancel(taskID) {
		writeJSON(w, http.StatusBadRequest, map[string]any{"error": "unable to cancel task"})
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{
		"task_id": taskID,
		"status":  "cancelled",
		"backend": "go",
	})
}

func (s *Server) handleListTasks(w http.ResponseWriter, r *http.Request) {
	status := strings.TrimSpace(r.URL.Query().Get("status"))
	limit := executor.AsInt(r.URL.Query().Get("limit"), 100)
	tasks := s.executor.List(status, limit)
	writeJSON(w, http.StatusOK, map[string]any{
		"tasks":   tasks,
		"count":   len(tasks),
		"backend": "go",
	})
}

func (s *Server) handleStatistics(w http.ResponseWriter, _ *http.Request) {
	writeJSON(w, http.StatusOK, s.executor.GetStatistics())
}

func (s *Server) handleClear(w http.ResponseWriter, r *http.Request) {
	olderThan := executor.AsFloat(r.URL.Query().Get("older_than"), 0)
	removed := s.executor.ClearCompleted(olderThan)
	writeJSON(w, http.StatusOK, map[string]any{
		"removed": removed,
		"backend": "go",
	})
}

func (s *Server) handleLegacyStatus(w http.ResponseWriter, r *http.Request) {
	taskID := r.URL.Query().Get("task_id")
	if taskID == "" {
		http.Error(w, "task_id is required", http.StatusBadRequest)
		return
	}
	s.handleGetTask(w, r, taskID)
}

func (s *Server) handleHealth(w http.ResponseWriter, _ *http.Request) {
	writeJSON(w, http.StatusOK, map[string]any{
		"status":  "ok",
		"service": "task-executor-go",
		"workers": s.executor.Workers,
	})
}

func writeJSON(w http.ResponseWriter, status int, payload any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(payload)
}
