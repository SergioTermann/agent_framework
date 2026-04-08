package executor

import (
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"strings"
	"strconv"
	"time"
)

func RunTask(task *Task) (any, error) {
	switch task.TaskType {
	case "data_processing":
		return runDataProcessing(task)
	case "report_generation":
		return runReportGeneration(task)
	case "model_training":
		return runModelTraining(task)
	case "batch_operation":
		return runBatchOperation(task)
	case "compute":
		return runSimpleDelay(task, "computation completed")
	case "io":
		return runSimpleDelay(task, "io operation completed")
	case "llm":
		return runLLM(task)
	case "transform_data":
		return runTransformData(task)
	case "http_request":
		return runHTTPRequest(task)
	default:
		return nil, fmt.Errorf("unknown task type: %s", task.TaskType)
	}
}

func runDataProcessing(task *Task) (any, error) {
	dataSize := AsInt(task.Params["data_size"], 1000)
	delayMillis := AsFloat(task.Params["delay"], 0.001) * 1000
	multiplier := AsFloat(task.Params["multiplier"], 2)

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
	return map[string]any{
		"processed": dataSize,
		"sample":    sample,
	}, nil
}

func runReportGeneration(task *Task) (any, error) {
	reportType := AsString(task.Params["type"], "summary")
	time.Sleep(2 * time.Second)
	return map[string]any{
		"report_type":  reportType,
		"generated_at": time.Now().Format(time.RFC3339),
		"pages":        10,
		"url":          fmt.Sprintf("/reports/%s_report.pdf", reportType),
	}, nil
}

func runModelTraining(task *Task) (any, error) {
	modelType := AsString(task.Params["model_type"], "linear")
	epochs := AsInt(task.Params["epochs"], 10)
	epochDelayMillis := AsInt(task.Params["epoch_delay_ms"], 500)
	for i := 0; i < epochs; i++ {
		time.Sleep(time.Duration(epochDelayMillis) * time.Millisecond)
	}
	return map[string]any{
		"model_type": modelType,
		"epochs":     epochs,
		"accuracy":   0.95,
		"model_path": fmt.Sprintf("/models/%s_model.pkl", modelType),
	}, nil
}

func runBatchOperation(task *Task) (any, error) {
	operation := AsString(task.Params["operation"], "update")
	items := AsSlice(task.Params["items"])
	results := make([]map[string]any, 0, len(items))
	for _, item := range items {
		time.Sleep(100 * time.Millisecond)
		results = append(results, map[string]any{
			"item":      item,
			"operation": operation,
			"status":    "success",
		})
	}
	return map[string]any{
		"operation": operation,
		"count":     len(results),
		"results":   results,
	}, nil
}

func runSimpleDelay(task *Task, message string) (any, error) {
	durationMs := AsInt(task.Params["duration"], 100)
	time.Sleep(time.Duration(durationMs) * time.Millisecond)
	return map[string]any{"result": message}, nil
}

func runLLM(task *Task) (any, error) {
	durationMs := AsInt(task.Params["duration"], 100)
	time.Sleep(time.Duration(durationMs) * time.Millisecond)
	return map[string]any{"response": "LLM response"}, nil
}

func runTransformData(task *Task) (any, error) {
	transformType := AsString(task.Params["transform_type"], "")
	inputValue := task.Params["input_value"]

	var output any
	switch transformType {
	case "upper":
		output = strings.ToUpper(Stringify(inputValue))
	case "lower":
		output = strings.ToLower(Stringify(inputValue))
	case "json_parse":
		raw := Stringify(inputValue)
		if raw == "" {
			output = nil
			break
		}
		var parsed any
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

	return map[string]any{"output": output}, nil
}

func runHTTPRequest(task *Task) (any, error) {
	method := strings.ToUpper(AsString(task.Params["method"], "GET"))
	url := AsString(task.Params["url"], "")
	if url == "" {
		return nil, fmt.Errorf("url is required")
	}

	timeoutSeconds := AsFloat(task.Params["timeout"], 30)
	headers := AsMap(task.Params["headers"])

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
		request.Header.Set(key, Stringify(value))
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

	var parsedBody any
	trimmed := bytes.TrimSpace(responseBody)
	if len(trimmed) > 0 {
		if err := json.Unmarshal(trimmed, &parsedBody); err != nil {
			parsedBody = string(responseBody)
		}
	} else {
		parsedBody = ""
	}

	return map[string]any{
		"status_code": response.StatusCode,
		"headers":     response.Header,
		"body":        parsedBody,
	}, nil
}

// ─── Type helpers ────────────────────────────────────────────────────────────

func AsString(value any, fallback string) string {
	if v, ok := value.(string); ok && v != "" {
		return v
	}
	return fallback
}

func AsInt(value any, fallback int) int {
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
	return fallback
}

func AsFloat(value any, fallback float64) float64 {
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
	return fallback
}

func AsSlice(value any) []any {
	if v, ok := value.([]any); ok {
		return v
	}
	return []any{}
}

func AsMap(value any) map[string]any {
	if v, ok := value.(map[string]any); ok {
		return v
	}
	return map[string]any{}
}

func Stringify(value any) string {
	switch v := value.(type) {
	case string:
		return v
	case nil:
		return ""
	default:
		return fmt.Sprint(v)
	}
}
