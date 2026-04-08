package executor

import "time"

type Task struct {
	ID          string         `json:"task_id"`
	TaskType    string         `json:"task_type"`
	Params      map[string]any `json:"params"`
	Priority    int            `json:"priority"`
	Status      string         `json:"status"`
	Result      any            `json:"result,omitempty"`
	Error       string         `json:"error,omitempty"`
	CreatedAt   time.Time      `json:"created_at"`
	StartedAt   *time.Time     `json:"started_at,omitempty"`
	CompletedAt *time.Time     `json:"completed_at,omitempty"`
	Progress    float64        `json:"progress"`
	Backend     string         `json:"backend"`
	heapIndex   int
}

type TaskHeap []*Task

func (h TaskHeap) Len() int { return len(h) }
func (h TaskHeap) Less(i, j int) bool {
	if h[i].Priority != h[j].Priority {
		return h[i].Priority > h[j].Priority
	}
	return h[i].CreatedAt.Before(h[j].CreatedAt)
}
func (h TaskHeap) Swap(i, j int) {
	h[i], h[j] = h[j], h[i]
	h[i].heapIndex = i
	h[j].heapIndex = j
}
func (h *TaskHeap) Push(x any) {
	task := x.(*Task)
	task.heapIndex = len(*h)
	*h = append(*h, task)
}
func (h *TaskHeap) Pop() any {
	old := *h
	n := len(old)
	task := old[n-1]
	task.heapIndex = -1
	*h = old[:n-1]
	return task
}

type Statistics struct {
	TotalSubmitted int     `json:"total_submitted"`
	TotalCompleted int     `json:"total_completed"`
	TotalFailed    int     `json:"total_failed"`
	TotalCancelled int     `json:"total_cancelled"`
	TotalDuration  float64 `json:"total_duration"`
}
