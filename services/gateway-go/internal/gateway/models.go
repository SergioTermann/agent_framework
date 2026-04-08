package gateway

import (
	"crypto/rand"
	"encoding/hex"
	"fmt"
	"time"
)

type PushTarget string

const (
	TargetAll           PushTarget = "ALL"
	TargetDevice        PushTarget = "DEVICE"
	TargetExcludeDevice PushTarget = "EXCLUDE_DEVICE"
	TargetConnection    PushTarget = "CONNECTION"
)

type Node struct {
	NodeID          string         `json:"node_id"`
	Address         string         `json:"address"`
	Status          string         `json:"status"`
	StartedAt       time.Time      `json:"started_at"`
	LastHeartbeat   time.Time      `json:"last_heartbeat"`
	Metadata        map[string]any `json:"metadata,omitempty"`
	ConnectionCount int            `json:"connection_count"`
}

type Connection struct {
	ConnectionID string         `json:"connection_id"`
	SID          string         `json:"sid"`
	UserID       string         `json:"user_id"`
	NodeID       string         `json:"node_id"`
	Namespace    string         `json:"namespace"`
	DeviceID     string         `json:"device_id,omitempty"`
	ConnectedAt  time.Time      `json:"connected_at"`
	LastSeenAt   time.Time      `json:"last_seen_at"`
	Status       string         `json:"status"`
	Metadata     map[string]any `json:"metadata,omitempty"`
}

type Event struct {
	EventID         string         `json:"event_id"`
	EventType       string         `json:"event_type"`
	UserID          string         `json:"user_id"`
	ConversationID  string         `json:"conversation_id,omitempty"`
	MessageID       string         `json:"message_id,omitempty"`
	Target          PushTarget     `json:"target"`
	DeviceID        string         `json:"device_id,omitempty"`
	ExcludeDeviceID string         `json:"exclude_device_id,omitempty"`
	ConnectionID    string         `json:"connection_id,omitempty"`
	Payload         map[string]any `json:"payload"`
	Metadata        map[string]any `json:"metadata,omitempty"`
	Status          string         `json:"status"`
	CreatedAt       time.Time      `json:"created_at"`
	DeliveredAt     *time.Time     `json:"delivered_at,omitempty"`
	AckedAt         *time.Time     `json:"acked_at,omitempty"`
}

type Delivery struct {
	DeliveryID   string         `json:"delivery_id"`
	EventID      string         `json:"event_id"`
	ConnectionID string         `json:"connection_id"`
	SID          string         `json:"sid"`
	DeviceID     string         `json:"device_id,omitempty"`
	Status       string         `json:"status"`
	DeliveredAt  *time.Time     `json:"delivered_at,omitempty"`
	AckedAt      *time.Time     `json:"acked_at,omitempty"`
	AckPayload   map[string]any `json:"ack_payload,omitempty"`
}

func NormalizeTarget(value string) PushTarget {
	switch PushTarget(value) {
	case TargetDevice, TargetExcludeDevice, TargetConnection:
		return PushTarget(value)
	default:
	}
	switch value {
	case "CURRENT_DEVICE":
		return TargetDevice
	case "CURRENT_CONNECTION":
		return TargetConnection
	case "EXCLUDE_CURRENT_DEVICE":
		return TargetExcludeDevice
	default:
		return TargetAll
	}
}

func EventEnvelope(event Event) map[string]any {
	return map[string]any{
		"traceId":   event.EventID,
		"event":     event.EventType,
		"timestamp": event.CreatedAt.UnixMilli(),
		"data":      event.Payload,
		"ackId":     event.EventID,
		"metadata":  event.Metadata,
	}
}

func NewID(prefix string) string {
	buf := make([]byte, 8)
	if _, err := rand.Read(buf); err != nil {
		return fmt.Sprintf("%s-%d", prefix, time.Now().UnixNano())
	}
	return fmt.Sprintf("%s-%s", prefix, hex.EncodeToString(buf))
}
