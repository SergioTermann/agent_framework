package executor

import (
	"testing"
	"time"
)

func TestSubmitAndComplete(t *testing.T) {
	svc := NewService(2)
	defer svc.Shutdown()

	task := svc.Submit("compute", map[string]any{"duration": 10}, 1)
	if task.Status != "queued" {
		t.Fatalf("expected queued, got %s", task.Status)
	}

	// wait for completion
	time.Sleep(200 * time.Millisecond)

	got, ok := svc.Get(task.ID)
	if !ok {
		t.Fatal("task not found")
	}
	if got.Status != "completed" {
		t.Fatalf("expected completed, got %s", got.Status)
	}
}

func TestCancelTask(t *testing.T) {
	svc := NewService(0) // no workers so tasks stay queued
	defer svc.Shutdown()

	task := svc.Submit("compute", map[string]any{"duration": 5000}, 1)
	if !svc.Cancel(task.ID) {
		t.Fatal("cancel should succeed for queued task")
	}

	got, _ := svc.Get(task.ID)
	if got.Status != "cancelled" {
		t.Fatalf("expected cancelled, got %s", got.Status)
	}
}

func TestStatistics(t *testing.T) {
	svc := NewService(2)
	defer svc.Shutdown()

	svc.Submit("compute", map[string]any{"duration": 10}, 1)
	svc.Submit("compute", map[string]any{"duration": 10}, 1)

	time.Sleep(200 * time.Millisecond)

	stats := svc.GetStatistics()
	if stats["total_submitted"].(int) != 2 {
		t.Fatalf("expected 2 submitted, got %v", stats["total_submitted"])
	}
	if stats["total_completed"].(int) != 2 {
		t.Fatalf("expected 2 completed, got %v", stats["total_completed"])
	}
}
