package main

import (
    "bytes"
    "container/heap"
    "encoding/json"
    "fmt"
    "io"
    "log"
    "net/http"
    "sort"
    "strconv"
    "strings"
    "sync"
    "time"

    "github.com/google/uuid"
)

type Task struct {
    ID          string                 `json:"task_id"`
    TaskType    string                 `json:"task_type"`
    Params      map[string]interface{} `json:"params"`
    Priority    int                    `json:"priority"`
    Status      string                 `json:"status"`
    Result      interface{}            `json:"result,omitempty"`
    Error       string                 `json:"error,omitempty"`
    CreatedAt   time.Time              `json:"created_at"`
    StartedAt   *time.Time             `json:"started_at,omitempty"`
    CompletedAt *time.Time             `json:"completed_at,omitempty"`
    Progress    float64                `json:"progress"`
    Backend     string                 `json:"backend"`
    heapIndex   int                    `json:"-"`
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
func (h *TaskHeap) Push(x interface{}) {
    task := x.(*Task)
    task.heapIndex = len(*h)
    *h = append(*h, task)
}
func (h *TaskHeap) Pop() interface{} {
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

type TaskExecutor struct {
    mu       sync.RWMutex
    cond     *sync.Cond
    tasks    map[string]*Task
    taskHeap TaskHeap
    running  bool
    workers  int
    stats    Statistics
}

func NewTaskExecutor(workers int) *TaskExecutor {
    executor := &TaskExecutor{
        tasks:   make(map[string]*Task),
        taskHeap: make(TaskHeap, 0),
        running: true,
        workers: workers,
    }
    executor.cond = sync.NewCond(&executor.mu)
    heap.Init(&executor.taskHeap)

    for i := 0; i < workers; i++ {
        go executor.worker(i)
    }
    return executor
}

func (e *TaskExecutor) worker(id int) {
    log.Printf("Go worker %d started", id)
    for {
        task := e.nextTask()
        if task == nil {
            log.Printf("Go worker %d stopped", id)
            return
        }
        e.executeTask(task)
    }
}

func (e *TaskExecutor) nextTask() *Task {
    e.mu.Lock()
    defer e.mu.Unlock()

    for e.running {
        for e.taskHeap.Len() > 0 {
            task := heap.Pop(&e.taskHeap).(*Task)
            if task.Status == "cancelled" {
                continue
            }
            now := time.Now()
            task.Status = "running"
            task.StartedAt = &now
            task.Progress = 0.1
            return task
        }
        e.cond.Wait()
    }
    return nil
}

func (e *TaskExecutor) executeTask(task *Task) {
    result, err := runTask(task)

    e.mu.Lock()
    defer e.mu.Unlock()

    now := time.Now()
    task.CompletedAt = &now
    task.Progress = 1.0

    if err != nil {
        task.Status = "failed"
        task.Error = err.Error()
        e.stats.TotalFailed++
    } else {
        task.Status = "completed"
        task.Result = result
        e.stats.TotalCompleted++
    }

    if task.StartedAt != nil {
        e.stats.TotalDuration += now.Sub(*task.StartedAt).Seconds()
    }
}

func (e *TaskExecutor) SubmitTask(taskType string, params map[string]interface{}, priority int) *Task {
    e.mu.Lock()
    defer e.mu.Unlock()

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

    e.tasks[task.ID] = task
    heap.Push(&e.taskHeap, task)
    e.stats.TotalSubmitted++
    e.cond.Signal()
    return task
}

func (e *TaskExecutor) GetTask(taskID string) (*Task, bool) {
    e.mu.RLock()
    defer e.mu.RUnlock()
    task, ok := e.tasks[taskID]
    return task, ok
}

func (e *TaskExecutor) CancelTask(taskID string) bool {
    e.mu.Lock()
    defer e.mu.Unlock()

    task, ok := e.tasks[taskID]
    if !ok {
        return false
    }
    if task.Status != "queued" {
        return false
    }

    now := time.Now()
    task.Status = "cancelled"
    task.CompletedAt = &now
    task.Progress = 0.0
    e.stats.TotalCancelled++
    return true
}

func (e *TaskExecutor) ListTasks(status string, limit int) []*Task {
    e.mu.RLock()
    defer e.mu.RUnlock()

    tasks := make([]*Task, 0, len(e.tasks))
    for _, task := range e.tasks {
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

func (e *TaskExecutor) GetStatistics() map[string]interface{} {
    e.mu.RLock()
    defer e.mu.RUnlock()

    running := 0
    queued := 0
    for _, task := range e.tasks {
        switch task.Status {
        case "running":
            running++
        case "queued":
            queued++
        }
    }

    avgDuration := 0.0
    if e.stats.TotalCompleted > 0 {
        avgDuration = e.stats.TotalDuration / float64(e.stats.TotalCompleted)
    }

    return map[string]interface{}{
        "backend":         "go",
        "workers":         e.workers,
        "total_submitted": e.stats.TotalSubmitted,
        "total_completed": e.stats.TotalCompleted,
        "total_failed":    e.stats.TotalFailed,
        "total_cancelled": e.stats.TotalCancelled,
        "total_duration":  e.stats.TotalDuration,
        "avg_duration":    avgDuration,
        "queue_length":    queued,
        "running":         running,
        "stored_tasks":    len(e.tasks),
    }
}

func (e *TaskExecutor) ClearCompleted(olderThanSeconds float64) int {
    e.mu.Lock()
    defer e.mu.Unlock()

    now := time.Now()
    removed := 0
    for taskID, task := range e.tasks {
        if task.Status == "queued" || task.Status == "running" {
            continue
        }
        if olderThanSeconds > 0 {
            if task.CompletedAt == nil || now.Sub(*task.CompletedAt).Seconds() <= olderThanSeconds {
                continue
            }
        }
        delete(e.tasks, taskID)
        removed++
    }
    return removed
}

func (e *TaskExecutor) Shutdown() {
    e.mu.Lock()
    e.running = false
    e.mu.Unlock()
    e.cond.Broadcast()
}

func runTask(task *Task) (interface{}, error) {
    switch task.TaskType {
    case "data_processing":
        dataSize := asInt(task.Params["data_size"], 1000)
        delayMillis := asFloat(task.Params["delay"], 0.001) * 1000
        multiplier := asFloat(task.Params["multiplier"], 2)

        sampleSize := dataSize
        if sampleSize > 10 {
            sampleSize = 10
        }
        sample := make([]float64, 0, sampleSize)
        for i := 0; i < dataSize; i++ {
            if i < sampleSize {
                sample = append(sample, float64(i)*multiplier)
            }
            if delayMillis > 0 {
                time.Sleep(time.Duration(delayMillis) * time.Millisecond)
            }
        }
        return map[string]interface{}{
            "processed": dataSize,
            "sample":    sample,
        }, nil

    case "report_generation":
        reportType := asString(task.Params["type"], "summary")
        time.Sleep(2 * time.Second)
        return map[string]interface{}{
            "report_type":  reportType,
            "generated_at": time.Now().Format(time.RFC3339),
            "pages":        10,
            "url":          fmt.Sprintf("/reports/%s_report.pdf", reportType),
        }, nil

    case "model_training":
        modelType := asString(task.Params["model_type"], "linear")
        epochs := asInt(task.Params["epochs"], 10)
        epochDelayMillis := asInt(task.Params["epoch_delay_ms"], 500)
        for i := 0; i < epochs; i++ {
            time.Sleep(time.Duration(epochDelayMillis) * time.Millisecond)
        }
        return map[string]interface{}{
            "model_type": modelType,
            "epochs":     epochs,
            "accuracy":   0.95,
            "model_path": fmt.Sprintf("/models/%s_model.pkl", modelType),
        }, nil

    case "batch_operation":
        operation := asString(task.Params["operation"], "update")
        items := asSlice(task.Params["items"])
        results := make([]map[string]interface{}, 0, len(items))
        for _, item := range items {
            time.Sleep(100 * time.Millisecond)
            results = append(results, map[string]interface{}{
                "item":      item,
                "operation": operation,
                "status":    "success",
            })
        }
        return map[string]interface{}{
            "operation": operation,
            "count":     len(results),
            "results":   results,
        }, nil

    case "compute":
        durationMs := asInt(task.Params["duration"], 100)
        time.Sleep(time.Duration(durationMs) * time.Millisecond)
        return map[string]interface{}{"result": "computation completed"}, nil

    case "io":
        durationMs := asInt(task.Params["duration"], 100)
        time.Sleep(time.Duration(durationMs) * time.Millisecond)
        return map[string]interface{}{"result": "io operation completed"}, nil

    case "llm":
        durationMs := asInt(task.Params["duration"], 100)
        time.Sleep(time.Duration(durationMs) * time.Millisecond)
        return map[string]interface{}{"response": "LLM response"}, nil

    case "transform_data":
        transformType := asString(task.Params["transform_type"], "")
        inputValue := task.Params["input_value"]

        var output interface{}
        switch transformType {
        case "upper":
            output = strings.ToUpper(stringifyValue(inputValue))
        case "lower":
            output = strings.ToLower(stringifyValue(inputValue))
        case "json_parse":
            raw := stringifyValue(inputValue)
            if raw == "" {
                output = nil
                break
            }
            var parsed interface{}
            decoder := json.NewDecoder(strings.NewReader(raw))
            decoder.UseNumber()
            if err := decoder.Decode(&parsed); err != nil {
                return nil, fmt.Errorf("json_parse failed: %w", err)
            }
            output = parsed
        case "json_stringify":
            encoded, err := json.Marshal(inputValue)
            if err != nil {
                return nil, fmt.Errorf("json_stringify failed: %w", err)
            }
            output = string(encoded)
        default:
            return nil, fmt.Errorf("unsupported transform_type: %s", transformType)
        }

        return map[string]interface{}{
            "output": output,
        }, nil

    case "http_request":
        method := strings.ToUpper(asString(task.Params["method"], "GET"))
        url := asString(task.Params["url"], "")
        if url == "" {
            return nil, fmt.Errorf("url is required")
        }

        timeoutSeconds := asFloat(task.Params["timeout"], 30)
        headers := asMap(task.Params["headers"])

        var bodyReader io.Reader
        if rawBody, ok := task.Params["body"]; ok && rawBody != nil {
            encoded, err := json.Marshal(rawBody)
            if err != nil {
                return nil, fmt.Errorf("failed to encode request body: %w", err)
            }
            bodyReader = bytes.NewReader(encoded)
        }

        request, err := http.NewRequest(method, url, bodyReader)
        if err != nil {
            return nil, fmt.Errorf("failed to create request: %w", err)
        }

        for key, value := range headers {
            addHeaderValues(request.Header, key, value)
        }
        if bodyReader != nil && request.Header.Get("Content-Type") == "" {
            request.Header.Set("Content-Type", "application/json")
        }

        client := &http.Client{Timeout: time.Duration(timeoutSeconds * float64(time.Second))}
        response, err := client.Do(request)
        if err != nil {
            return nil, fmt.Errorf("http request failed: %w", err)
        }
        defer response.Body.Close()

        responseBody, err := io.ReadAll(response.Body)
        if err != nil {
            return nil, fmt.Errorf("failed to read response body: %w", err)
        }

        return map[string]interface{}{
            "status_code": response.StatusCode,
            "headers":     response.Header,
            "body":        parseHTTPResponseBody(responseBody),
        }, nil

    default:
        return nil, fmt.Errorf("unknown task type: %s", task.TaskType)
    }
}

func asString(value interface{}, defaultValue string) string {
    switch v := value.(type) {
    case string:
        if v != "" {
            return v
        }
    }
    return defaultValue
}

func asInt(value interface{}, defaultValue int) int {
    switch v := value.(type) {
    case float64:
        return int(v)
    case float32:
        return int(v)
    case int:
        return v
    case int64:
        return int(v)
    case json.Number:
        if parsed, err := v.Int64(); err == nil {
            return int(parsed)
        }
    case string:
        if parsed, err := strconv.Atoi(v); err == nil {
            return parsed
        }
    }
    return defaultValue
}

func asFloat(value interface{}, defaultValue float64) float64 {
    switch v := value.(type) {
    case float64:
        return v
    case float32:
        return float64(v)
    case int:
        return float64(v)
    case int64:
        return float64(v)
    case json.Number:
        if parsed, err := v.Float64(); err == nil {
            return parsed
        }
    case string:
        if parsed, err := strconv.ParseFloat(v, 64); err == nil {
            return parsed
        }
    }
    return defaultValue
}

func asSlice(value interface{}) []interface{} {
    switch v := value.(type) {
    case []interface{}:
        return v
    default:
        return []interface{}{}
    }
}

func asMap(value interface{}) map[string]interface{} {
    switch v := value.(type) {
    case map[string]interface{}:
        return v
    default:
        return map[string]interface{}{}
    }
}

func stringifyValue(value interface{}) string {
    switch v := value.(type) {
    case string:
        return v
    case nil:
        return ""
    default:
        return fmt.Sprint(v)
    }
}

func addHeaderValues(headers http.Header, key string, value interface{}) {
    switch v := value.(type) {
    case string:
        headers.Set(key, v)
    case []string:
        for _, item := range v {
            headers.Add(key, item)
        }
    case []interface{}:
        for _, item := range v {
            headers.Add(key, stringifyValue(item))
        }
    default:
        headers.Set(key, stringifyValue(v))
    }
}

func parseHTTPResponseBody(body []byte) interface{} {
    trimmed := bytes.TrimSpace(body)
    if len(trimmed) == 0 {
        return ""
    }

    var parsed interface{}
    if err := json.Unmarshal(trimmed, &parsed); err == nil {
        return parsed
    }
    return string(body)
}

var executor *TaskExecutor

func submitTaskHandler(w http.ResponseWriter, r *http.Request) {
    if r.Method != http.MethodPost {
        http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
        return
    }

    var payload map[string]interface{}
    if err := json.NewDecoder(r.Body).Decode(&payload); err != nil {
        http.Error(w, err.Error(), http.StatusBadRequest)
        return
    }

    taskType := asString(payload["task_type"], asString(payload["type"], ""))
    if taskType == "" {
        http.Error(w, "task_type is required", http.StatusBadRequest)
        return
    }

    params := map[string]interface{}{}
    if rawParams, ok := payload["params"].(map[string]interface{}); ok {
        params = rawParams
    } else if rawPayload, ok := payload["payload"].(map[string]interface{}); ok {
        params = rawPayload
    }

    priority := asInt(payload["priority"], 1)
    task := executor.SubmitTask(taskType, params, priority)
    writeJSON(w, http.StatusOK, map[string]interface{}{
        "task_id": task.ID,
        "status":  task.Status,
        "backend": "go",
    })
}

func taskRouter(w http.ResponseWriter, r *http.Request) {
    path := strings.TrimPrefix(r.URL.Path, "/tasks/")
    if path == "" || path == r.URL.Path {
        if r.Method == http.MethodGet {
            listTasksHandler(w, r)
            return
        }
        http.NotFound(w, r)
        return
    }

    parts := strings.Split(strings.Trim(path, "/"), "/")
    taskID := parts[0]
    if len(parts) == 1 && r.Method == http.MethodGet {
        getTaskHandler(w, r, taskID)
        return
    }
    if len(parts) == 2 {
        switch parts[1] {
        case "status":
            if r.Method == http.MethodGet {
                getTaskStatusHandler(w, r, taskID)
                return
            }
        case "result":
            if r.Method == http.MethodGet {
                getTaskResultHandler(w, r, taskID)
                return
            }
        case "cancel":
            if r.Method == http.MethodPost {
                cancelTaskHandler(w, r, taskID)
                return
            }
        }
    }

    http.NotFound(w, r)
}

func getTaskHandler(w http.ResponseWriter, r *http.Request, taskID string) {
    task, ok := executor.GetTask(taskID)
    if !ok {
        http.Error(w, "task not found", http.StatusNotFound)
        return
    }
    writeJSON(w, http.StatusOK, task)
}

func getTaskStatusHandler(w http.ResponseWriter, r *http.Request, taskID string) {
    task, ok := executor.GetTask(taskID)
    if !ok {
        http.Error(w, "task not found", http.StatusNotFound)
        return
    }
    writeJSON(w, http.StatusOK, map[string]interface{}{
        "task_id": task.ID,
        "status":  task.Status,
        "backend": task.Backend,
    })
}

func getTaskResultHandler(w http.ResponseWriter, r *http.Request, taskID string) {
    task, ok := executor.GetTask(taskID)
    if !ok {
        http.Error(w, "task not found", http.StatusNotFound)
        return
    }

    if task.Status == "queued" || task.Status == "running" {
        writeJSON(w, http.StatusBadRequest, map[string]interface{}{
            "error":  "task not finished",
            "status": task.Status,
        })
        return
    }
    if task.Status == "failed" {
        writeJSON(w, http.StatusInternalServerError, map[string]interface{}{
            "error":   "task failed",
            "message": task.Error,
            "status":  task.Status,
        })
        return
    }
    if task.Status == "cancelled" {
        writeJSON(w, http.StatusBadRequest, map[string]interface{}{
            "error":  "task cancelled",
            "status": task.Status,
        })
        return
    }

    writeJSON(w, http.StatusOK, map[string]interface{}{
        "task_id": task.ID,
        "status":  task.Status,
        "result":  task.Result,
        "backend": task.Backend,
    })
}

func cancelTaskHandler(w http.ResponseWriter, r *http.Request, taskID string) {
    if !executor.CancelTask(taskID) {
        writeJSON(w, http.StatusBadRequest, map[string]interface{}{
            "error": "unable to cancel task",
        })
        return
    }
    writeJSON(w, http.StatusOK, map[string]interface{}{
        "task_id": taskID,
        "status":  "cancelled",
        "backend": "go",
    })
}

func listTasksHandler(w http.ResponseWriter, r *http.Request) {
    status := strings.TrimSpace(r.URL.Query().Get("status"))
    limit := asInt(r.URL.Query().Get("limit"), 100)
    tasks := executor.ListTasks(status, limit)
    writeJSON(w, http.StatusOK, map[string]interface{}{
        "tasks":   tasks,
        "count":   len(tasks),
        "backend": "go",
    })
}

func statisticsHandler(w http.ResponseWriter, r *http.Request) {
    writeJSON(w, http.StatusOK, executor.GetStatistics())
}

func clearHandler(w http.ResponseWriter, r *http.Request) {
    olderThan := asFloat(r.URL.Query().Get("older_than"), 0)
    removed := executor.ClearCompleted(olderThan)
    writeJSON(w, http.StatusOK, map[string]interface{}{
        "removed": removed,
        "backend": "go",
    })
}

func legacyStatusHandler(w http.ResponseWriter, r *http.Request) {
    taskID := r.URL.Query().Get("task_id")
    if taskID == "" {
        http.Error(w, "task_id is required", http.StatusBadRequest)
        return
    }
    getTaskHandler(w, r, taskID)
}

func healthHandler(w http.ResponseWriter, r *http.Request) {
    writeJSON(w, http.StatusOK, map[string]interface{}{
        "status":  "ok",
        "backend": "go",
        "workers": executor.workers,
    })
}

func writeJSON(w http.ResponseWriter, statusCode int, payload interface{}) {
    w.Header().Set("Content-Type", "application/json")
    w.WriteHeader(statusCode)
    _ = json.NewEncoder(w).Encode(payload)
}

func main() {
    executor = NewTaskExecutor(64)

    mux := http.NewServeMux()
    mux.HandleFunc("/submit", submitTaskHandler)
    mux.HandleFunc("/status", legacyStatusHandler)
    mux.HandleFunc("/tasks", listTasksHandler)
    mux.HandleFunc("/tasks/", taskRouter)
    mux.HandleFunc("/statistics", statisticsHandler)
    mux.HandleFunc("/clear", clearHandler)
    mux.HandleFunc("/health", healthHandler)

    port := ":8080"
    log.Printf("Go task executor listening on %s", port)
    if err := http.ListenAndServe(port, mux); err != nil {
        log.Fatal(err)
    }
}
