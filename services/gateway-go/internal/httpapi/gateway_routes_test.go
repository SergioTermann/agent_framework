package httpapi

import (
	"bytes"
	"crypto/hmac"
	"crypto/sha256"
	"encoding/base64"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	authn "agent-framework/services/gateway-go/internal/auth"
	"agent-framework/services/gateway-go/internal/config"
	"agent-framework/services/gateway-go/internal/gateway"
)

func TestGatewayRoutesRequireAuthAndAllowScopedPush(t *testing.T) {
	cfg := config.Config{
		Namespace:   "/gateway",
		RequireAuth: true,
		AuthSecret:  "test-secret",
	}
	service := gateway.NewService(cfg)

	mux := http.NewServeMux()
	newGatewayRoutes(service, cfg).register(mux)

	req := httptest.NewRequest(http.MethodGet, "/api/gateway/nodes", nil)
	rec := httptest.NewRecorder()
	mux.ServeHTTP(rec, req)
	if rec.Code != http.StatusUnauthorized {
		t.Fatalf("expected 401 without auth, got %d", rec.Code)
	}

	body, err := json.Marshal(map[string]any{
		"event":   "notice",
		"payload": map[string]any{"kind": "self"},
	})
	if err != nil {
		t.Fatalf("marshal body: %v", err)
	}
	req = httptest.NewRequest(http.MethodPost, "/api/gateway/push", bytes.NewReader(body))
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("Authorization", "Bearer "+testToken(t, authn.Claims{
		UserID:   "user-42",
		Username: "demo",
		Email:    "demo@example.com",
		Role:     "member",
	}, cfg.AuthSecret))
	rec = httptest.NewRecorder()
	mux.ServeHTTP(rec, req)
	if rec.Code != http.StatusOK {
		t.Fatalf("expected scoped push to succeed, got %d: %s", rec.Code, rec.Body.String())
	}

	var payload map[string]any
	if err := json.Unmarshal(rec.Body.Bytes(), &payload); err != nil {
		t.Fatalf("unmarshal response: %v", err)
	}
	data, _ := payload["data"].(map[string]any)
	eventID, _ := data["event_id"].(string)
	if eventID == "" {
		t.Fatalf("expected event_id in response, got %#v", payload)
	}
	event, ok := service.GetEvent(eventID)
	if !ok {
		t.Fatal("expected event to be stored")
	}
	if event["user_id"] != "user-42" {
		t.Fatalf("expected scoped user_id user-42, got %v", event["user_id"])
	}
}

func TestGatewayRoutesAllowConnectionReplayForOwner(t *testing.T) {
	cfg := config.Config{
		Namespace:   "/gateway",
		RequireAuth: true,
		AuthSecret:  "test-secret",
	}
	service := gateway.NewService(cfg)
	t.Cleanup(service.Close)

	connection := service.Connect("conn-owner-1", "user-7", "sid-7", "/gateway", "device-7", nil)
	if _, ok := service.Disconnect(connection.ConnectionID); !ok {
		t.Fatal("expected disconnect to succeed")
	}
	service.Publish(gateway.Event{
		EventID:   "evt-owner-1",
		UserID:    "user-7",
		EventType: "notice",
		Payload:   map[string]any{"kind": "offline"},
	})
	if _, ok := service.Touch(connection.ConnectionID); !ok {
		t.Fatal("expected touch to restore connection online")
	}

	mux := http.NewServeMux()
	newGatewayRoutes(service, cfg).register(mux)

	req := httptest.NewRequest(
		http.MethodPost,
		"/api/gateway/connections/"+connection.ConnectionID+"/replay-pending",
		bytes.NewReader([]byte(`{}`)),
	)
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("Authorization", "Bearer "+testToken(t, authn.Claims{
		UserID:   "user-7",
		Username: "owner",
		Email:    "owner@example.com",
		Role:     "member",
	}, cfg.AuthSecret))
	rec := httptest.NewRecorder()
	mux.ServeHTTP(rec, req)
	if rec.Code != http.StatusOK {
		t.Fatalf("expected replay to succeed, got %d: %s", rec.Code, rec.Body.String())
	}

	event, ok := service.GetEvent("evt-owner-1")
	if !ok {
		t.Fatal("expected event to exist")
	}
	if event["status"] != "DELIVERED" {
		t.Fatalf("expected delivered event after replay, got %v", event["status"])
	}
}

func testToken(t *testing.T, claims authn.Claims, secret string) string {
	t.Helper()

	headerBytes, err := json.Marshal(map[string]string{
		"alg": "HS256",
		"typ": "JWT",
	})
	if err != nil {
		t.Fatalf("marshal header: %v", err)
	}
	if claims.Exp == 0 {
		claims.Exp = time.Now().UTC().Add(time.Hour).Unix()
	}
	if claims.Iat == 0 {
		claims.Iat = time.Now().UTC().Unix()
	}
	payloadBytes, err := json.Marshal(claims)
	if err != nil {
		t.Fatalf("marshal claims: %v", err)
	}
	message := base64.RawURLEncoding.EncodeToString(headerBytes) + "." + base64.RawURLEncoding.EncodeToString(payloadBytes)
	return message + "." + signTestToken(message, secret)
}

func signTestToken(message, secret string) string {
	mac := hmac.New(sha256.New, []byte(secret))
	_, _ = mac.Write([]byte(message))
	return base64.RawURLEncoding.EncodeToString(mac.Sum(nil))
}
