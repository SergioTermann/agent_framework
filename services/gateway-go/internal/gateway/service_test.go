package gateway

import (
	"path/filepath"
	"testing"
	"time"

	"agent-framework/services/gateway-go/internal/config"
)

func TestConnectPublishAndPendingEvents(t *testing.T) {
	service := NewService(config.Config{
		ListenAddr: ":7000",
		NodeID:     "gw-test",
		Namespace:  "/gateway",
	})
	t.Cleanup(service.Close)

	connection := service.Connect("", "user-1", "sid-1", "/gateway", "device-1", map[string]any{"source": "test"})
	if connection.ConnectionID == "" {
		t.Fatal("expected connection id")
	}

	result := service.Publish(Event{
		UserID:    "user-1",
		EventType: "chat.message",
		Payload:   map[string]any{"text": "hello"},
	})
	if result["delivered_count"].(int) != 1 {
		t.Fatalf("expected delivered_count=1, got %v", result["delivered_count"])
	}

	if _, ok := service.GetEvent(result["event_id"].(string)); !ok {
		t.Fatal("expected event to exist")
	}

	service.Disconnect(connection.ConnectionID)
	result = service.Publish(Event{
		UserID:    "user-1",
		EventType: "chat.message",
		Payload:   map[string]any{"text": "offline"},
	})
	if result["offline_queued"].(bool) != true {
		t.Fatalf("expected offline queue, got %v", result["offline_queued"])
	}

	pending := service.ListPendingEvents("user-1")
	if len(pending) != 1 {
		t.Fatalf("expected 1 pending event, got %d", len(pending))
	}
}

func TestConnectionFiltering(t *testing.T) {
	service := NewService(config.Config{
		ListenAddr: ":7000",
		NodeID:     "gw-test",
		Namespace:  "/gateway",
	})
	t.Cleanup(service.Close)

	first := service.Connect("", "user-2", "sid-2", "/gateway", "device-a", nil)
	second := service.Connect("", "user-2", "sid-3", "/gateway", "device-b", nil)

	result := service.Publish(Event{
		UserID:    "user-2",
		EventType: "notice",
		Target:    TargetDevice,
		DeviceID:  "device-a",
		Payload:   map[string]any{"kind": "single-device"},
	})
	if result["delivered_count"].(int) != 1 {
		t.Fatalf("expected one delivery, got %v", result["delivered_count"])
	}

	result = service.Publish(Event{
		UserID:       "user-2",
		EventType:    "notice",
		Target:       TargetConnection,
		ConnectionID: second.ConnectionID,
		Payload:      map[string]any{"kind": "single-connection"},
	})
	if result["delivered_count"].(int) != 1 {
		t.Fatalf("expected one connection delivery, got %v", result["delivered_count"])
	}

	if len(service.ListUserConnections("user-2", false)) != 2 {
		t.Fatal("expected two online connections")
	}

	service.Disconnect(first.ConnectionID)
	if len(service.ListUserConnections("user-2", false)) != 1 {
		t.Fatal("expected one online connection after disconnect")
	}
}

func TestAckDeliveredEvent(t *testing.T) {
	service := NewService(config.Config{
		ListenAddr: ":7000",
		NodeID:     "gw-test",
		Namespace:  "/gateway",
	})
	t.Cleanup(service.Close)

	connection := service.Connect("", "user-3", "sid-9", "/gateway", "device-z", nil)
	result := service.Publish(Event{
		UserID:    "user-3",
		EventType: "notice",
		Payload:   map[string]any{"kind": "ack-test"},
	})

	eventID, ok := result["event_id"].(string)
	if !ok || eventID == "" {
		t.Fatalf("expected event_id, got %v", result["event_id"])
	}

	ack, ok := service.Ack(eventID, connection.ConnectionID, map[string]any{"source": "test"})
	if !ok {
		t.Fatal("expected ack to succeed")
	}
	if ack["connection_id"] != connection.ConnectionID {
		t.Fatalf("expected connection_id=%s, got %v", connection.ConnectionID, ack["connection_id"])
	}

	event, ok := service.GetEvent(eventID)
	if !ok {
		t.Fatal("expected event to exist after ack")
	}
	if event["status"] != "ACKED" {
		t.Fatalf("expected event status ACKED, got %v", event["status"])
	}

	deliveries, ok := event["deliveries"].([]Delivery)
	if !ok || len(deliveries) != 1 {
		t.Fatalf("expected one delivery, got %#v", event["deliveries"])
	}
	if deliveries[0].Status != "ACKED" {
		t.Fatalf("expected delivery status ACKED, got %s", deliveries[0].Status)
	}
	if deliveries[0].AckedAt == nil {
		t.Fatal("expected delivery ack timestamp")
	}
	if deliveries[0].AckPayload["source"] != "test" {
		t.Fatalf("expected ack payload source=test, got %#v", deliveries[0].AckPayload)
	}
}

func TestConnectPreservesProvidedConnectionID(t *testing.T) {
	service := NewService(config.Config{
		ListenAddr: ":7000",
		NodeID:     "gw-test",
		Namespace:  "/gateway",
	})
	t.Cleanup(service.Close)

	connection := service.Connect("conn-python-1", "user-5", "sid-5", "/gateway", "device-5", nil)
	if connection.ConnectionID != "conn-python-1" {
		t.Fatalf("expected provided connection id, got %s", connection.ConnectionID)
	}
}

func TestReplayPendingMarksEventsDelivered(t *testing.T) {
	service := NewService(config.Config{
		ListenAddr: ":7000",
		NodeID:     "gw-test",
		Namespace:  "/gateway",
	})
	t.Cleanup(service.Close)

	connection := service.Connect("conn-replay-1", "user-6", "sid-6", "/gateway", "device-6", nil)
	service.Disconnect(connection.ConnectionID)

	queued := service.Publish(Event{
		EventID:   "evt-replay-1",
		UserID:    "user-6",
		EventType: "notice",
		Payload:   map[string]any{"kind": "offline"},
	})
	if queued["offline_queued"] != true {
		t.Fatalf("expected queued event, got %#v", queued)
	}

	if _, ok := service.Touch(connection.ConnectionID); !ok {
		t.Fatal("expected touch to restore connection online")
	}

	replayed, ok := service.ReplayPending(connection.ConnectionID)
	if !ok {
		t.Fatal("expected replay to succeed")
	}
	if len(replayed) != 1 {
		t.Fatalf("expected 1 replayed event, got %d", len(replayed))
	}
	if replayed[0]["event_id"] != "evt-replay-1" {
		t.Fatalf("expected replayed event id evt-replay-1, got %#v", replayed[0])
	}

	event, ok := service.GetEvent("evt-replay-1")
	if !ok {
		t.Fatal("expected event to exist")
	}
	if event["status"] != "DELIVERED" {
		t.Fatalf("expected delivered status after replay, got %v", event["status"])
	}
	deliveries, ok := event["deliveries"].([]Delivery)
	if !ok || len(deliveries) != 1 {
		t.Fatalf("expected one delivery after replay, got %#v", event["deliveries"])
	}
	if deliveries[0].ConnectionID != connection.ConnectionID {
		t.Fatalf("expected replay delivery on %s, got %s", connection.ConnectionID, deliveries[0].ConnectionID)
	}
}

func TestStatePersistsAcrossRestart(t *testing.T) {
	storePath := filepath.Join(t.TempDir(), "gateway_store.json")
	cfg := config.Config{
		ListenAddr:     ":7000",
		NodeID:         "gw-test",
		Namespace:      "/gateway",
		StateStorePath: storePath,
	}

	service := NewService(cfg)
	connection := service.Connect("", "user-4", "sid-4", "/gateway", "device-4", map[string]any{"source": "persist"})
	delivered := service.Publish(Event{
		UserID:    "user-4",
		EventType: "notice",
		Payload:   map[string]any{"kind": "delivered"},
	})
	deliveredEventID := delivered["event_id"].(string)
	if _, ok := service.Ack(deliveredEventID, connection.ConnectionID, map[string]any{"source": "persist-test"}); !ok {
		t.Fatal("expected delivered event ack to succeed")
	}

	service.Disconnect(connection.ConnectionID)
	queued := service.Publish(Event{
		UserID:    "user-4",
		EventType: "notice",
		Payload:   map[string]any{"kind": "offline"},
	})
	queuedEventID := queued["event_id"].(string)

	service.Close()
	restarted := NewService(cfg)
	t.Cleanup(restarted.Close)
	if len(restarted.ListUserConnections("user-4", false)) != 0 {
		t.Fatal("expected no online connections after restart")
	}
	connections := restarted.ListUserConnections("user-4", true)
	if len(connections) != 1 {
		t.Fatalf("expected 1 persisted connection, got %d", len(connections))
	}
	if connections[0].Status != "OFFLINE" {
		t.Fatalf("expected restarted connection to be OFFLINE, got %s", connections[0].Status)
	}

	ackedEvent, ok := restarted.GetEvent(deliveredEventID)
	if !ok {
		t.Fatal("expected acked event to persist")
	}
	if ackedEvent["status"] != "ACKED" {
		t.Fatalf("expected acked event status, got %v", ackedEvent["status"])
	}

	pending := restarted.ListPendingEvents("user-4")
	if len(pending) != 1 {
		t.Fatalf("expected 1 pending event after restart, got %d", len(pending))
	}
	if pending[0].EventID != queuedEventID {
		t.Fatalf("expected pending event %s, got %s", queuedEventID, pending[0].EventID)
	}
}

func TestPruneCompletedAndOfflineHistory(t *testing.T) {
	cfg := config.Config{
		ListenAddr:         ":7000",
		NodeID:             "gw-test",
		Namespace:          "/gateway",
		OfflineRetention:   time.Hour,
		CompletedRetention: time.Hour,
	}
	service := NewService(cfg)
	t.Cleanup(service.Close)

	now := time.Now().UTC()
	old := now.Add(-2 * time.Hour)

	service.mu.Lock()
	service.connections["conn-old"] = Connection{
		ConnectionID: "conn-old",
		UserID:       "user-old",
		Status:       "OFFLINE",
		LastSeenAt:   old,
	}
	service.userIndex["user-old"] = []string{"conn-old"}

	service.connections["conn-live"] = Connection{
		ConnectionID: "conn-live",
		UserID:       "user-live",
		Status:       "ONLINE",
		LastSeenAt:   now,
	}
	service.userIndex["user-live"] = []string{"conn-live"}

	deliveredAt := old
	ackedAt := old
	service.events["evt-old"] = Event{
		EventID:     "evt-old",
		UserID:      "user-old",
		EventType:   "notice",
		Status:      "ACKED",
		CreatedAt:   old,
		DeliveredAt: &deliveredAt,
		AckedAt:     &ackedAt,
	}
	service.deliveries["evt-old"] = []Delivery{{
		DeliveryID:   "dlv-old",
		EventID:      "evt-old",
		ConnectionID: "conn-old",
		Status:       "ACKED",
		AckedAt:      &ackedAt,
	}}

	service.events["evt-pending"] = Event{
		EventID:   "evt-pending",
		UserID:    "user-pending",
		EventType: "notice",
		Status:    "PENDING_OFFLINE",
		CreatedAt: old,
	}
	service.mu.Unlock()

	snapshot := service.snapshot()
	if len(snapshot.Connections) != 1 || snapshot.Connections[0].ConnectionID != "conn-live" {
		t.Fatalf("expected only live connection in snapshot, got %#v", snapshot.Connections)
	}
	if len(snapshot.Events) != 1 || snapshot.Events[0].EventID != "evt-pending" {
		t.Fatalf("expected only pending event in snapshot, got %#v", snapshot.Events)
	}
	if len(snapshot.Deliveries) != 0 {
		t.Fatalf("expected pruned deliveries, got %#v", snapshot.Deliveries)
	}
}
