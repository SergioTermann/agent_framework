package executor

import (
	"container/heap"
	"log"
	"sort"
	"sync"
	"time"

	"github.com/google/uuid"
)

type Service struct {
	mu       sync.RWMutex
	cond     *sync.Cond
	tasks    map[string]*Task
	taskHeap TaskHeap
	running  bool
	Workers  int
	stats    Statistics
}

func NewService(workers int) *Service {
	svc := &Service{
		tasks:    make(map[string]*Task),
		taskHeap: make(TaskHeap, 0),
		running:  true,
		Workers:  workers,
	}
	svc.cond = sync.NewCond(&svc.mu)
	heap.Init(&svc.taskHeap)

	for i := 0; i < workers; i++ {
		go svc.worker(i)
	}
	return svc
}

func (s *Service) worker(id int) {
	log.Printf("worker %d started", id)
	for {
		task := s.nextTask()
		if task == nil {
			log.Printf("worker %d stopped", id)
			return
		}
		s.executeTask(task)
	}
}

func (s *Service) nextTask() *Task {
	s.mu.Lock()
	defer s.mu.Unlock()

	for s.running {
		for s.taskHeap.Len() > 0 {
			task := heap.Pop(&s.taskHeap).(*Task)
			if task.Status == "cancelled" {
				continue
			}
			now := time.Now()
			task.Status = "running"
			task.StartedAt = &now
			task.Progress = 0.1
			return task
		}
		s.cond.Wait()
	}
	return nil
}

func (s *Service) executeTask(task *Task) {
	result, err := RunTask(task)

	s.mu.Lock()
	defer s.mu.Unlock()

	now := time.Now()
	task.CompletedAt = &now
	task.Progress = 1.0

	if err != nil {
		task.Status = "failed"
		task.Error = err.Error()
		s.stats.TotalFailed++
	} else {
		task.Status = "completed"
		task.Result = result
		s.stats.TotalCompleted++
	}

	if task.StartedAt != nil {
		s.stats.TotalDuration += now.Sub(*task.StartedAt).Seconds()
	}
}

func (s *Service) Submit(taskType string, params map[string]any, priority int) *Task {
	s.mu.Lock()
	defer s.mu.Unlock()

	task := &Task{
		ID:        "go_" + uuid.New().String(),
		TaskType:  taskType,
		Params:    params,
		Priority:  priority,
		Status:    "queued",
		CreatedAt: time.Now(),
		Progress:  0.0,
		Backend:   "go",
	}

	s.tasks[task.ID] = task
	heap.Push(&s.taskHeap, task)
	s.stats.TotalSubmitted++
	s.cond.Signal()
	return task
}

func (s *Service) Get(taskID string) (*Task, bool) {
	s.mu.RLock()
	defer s.mu.RUnlock()
	task, ok := s.tasks[taskID]
	return task, ok
}

func (s *Service) Cancel(taskID string) bool {
	s.mu.Lock()
	defer s.mu.Unlock()

	task, ok := s.tasks[taskID]
	if !ok || task.Status != "queued" {
		return false
	}

	now := time.Now()
	task.Status = "cancelled"
	task.CompletedAt = &now
	task.Progress = 0.0
	s.stats.TotalCancelled++
	return true
}

func (s *Service) List(status string, limit int) []*Task {
	s.mu.RLock()
	defer s.mu.RUnlock()

	tasks := make([]*Task, 0, len(s.tasks))
	for _, task := range s.tasks {
		if status == "" || task.Status == status {
			tasks = append(tasks, task)
		}
	}

	sort.Slice(tasks, func(i, j int) bool {
		return tasks[i].CreatedAt.After(tasks[j].CreatedAt)
	})

	if limit > 0 && len(tasks) > limit {
		tasks = tasks[:limit]
	}
	return tasks
}

func (s *Service) GetStatistics() map[string]any {
	s.mu.RLock()
	defer s.mu.RUnlock()

	running := 0
	queued := 0
	for _, task := range s.tasks {
		switch task.Status {
		case "running":
			running++
		case "queued":
			queued++
		}
	}

	avgDuration := 0.0
	if s.stats.TotalCompleted > 0 {
		avgDuration = s.stats.TotalDuration / float64(s.stats.TotalCompleted)
	}

	return map[string]any{
		"backend":         "go",
		"workers":         s.Workers,
		"total_submitted": s.stats.TotalSubmitted,
		"total_completed": s.stats.TotalCompleted,
		"total_failed":    s.stats.TotalFailed,
		"total_cancelled": s.stats.TotalCancelled,
		"total_duration":  s.stats.TotalDuration,
		"avg_duration":    avgDuration,
		"queue_length":    queued,
		"running":         running,
		"stored_tasks":    len(s.tasks),
	}
}

func (s *Service) ClearCompleted(olderThanSeconds float64) int {
	s.mu.Lock()
	defer s.mu.Unlock()

	now := time.Now()
	removed := 0
	for taskID, task := range s.tasks {
		if task.Status == "queued" || task.Status == "running" {
			continue
		}
		if olderThanSeconds > 0 {
			if task.CompletedAt == nil || now.Sub(*task.CompletedAt).Seconds() <= olderThanSeconds {
				continue
			}
		}
		delete(s.tasks, taskID)
		removed++
	}
	return removed
}

func (s *Service) Shutdown() {
	s.mu.Lock()
	s.running = false
	s.mu.Unlock()
	s.cond.Broadcast()
}
