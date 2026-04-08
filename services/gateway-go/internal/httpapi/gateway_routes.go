package httpapi

import (
	"encoding/json"
	"net/http"
	"strings"
	"time"

	authn "agent-framework/services/gateway-go/internal/auth"
	"agent-framework/services/gateway-go/internal/config"
	"agent-framework/services/gateway-go/internal/gateway"
)

type gatewayRoutes struct {
	service *gateway.Service
	cfg     config.Config
}

func newGatewayRoutes(service *gateway.Service, cfg config.Config) gatewayRoutes {
	return gatewayRoutes{
		service: service,
		cfg:     cfg,
	}
}

func (g gatewayRoutes) register(mux *http.ServeMux) {
	g.registerPrefix(mux, "/api/v1/gateway")
	g.registerPrefix(mux, "/api/gateway")
}

func (g gatewayRoutes) registerPrefix(mux *http.ServeMux, prefix string) {
	mux.HandleFunc(prefix+"/nodes", g.handleNodes)
	mux.HandleFunc(prefix+"/online-users", g.handleOnlineUsers)
	mux.HandleFunc(prefix+"/users/", g.handleUserRoutes(prefix))
	mux.HandleFunc(prefix+"/events/", g.handleEventByID(prefix))
	mux.HandleFunc(prefix+"/push", g.handlePush)
	mux.HandleFunc(prefix+"/connections", g.handleConnections)
	mux.HandleFunc(prefix+"/connections/", g.handleConnectionByID(prefix))
}

func (g gatewayRoutes) handleNodes(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet {
		writeJSON(w, http.StatusMethodNotAllowed, map[string]any{"error": "method not allowed"})
		return
	}
	if _, ok := g.requireAdmin(w, r); !ok {
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{
		"success": true,
		"data":    g.service.ListNodes(),
	})
}

func (g gatewayRoutes) handleOnlineUsers(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet {
		writeJSON(w, http.StatusMethodNotAllowed, map[string]any{"error": "method not allowed"})
		return
	}
	if _, ok := g.requireAdmin(w, r); !ok {
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{
		"success": true,
		"data":    g.service.ListOnlineUsers(),
	})
}

func (g gatewayRoutes) handleUserRoutes(prefix string) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		path := strings.TrimPrefix(r.URL.Path, prefix+"/users/")
		parts := strings.Split(path, "/")
		if len(parts) < 2 || strings.TrimSpace(parts[0]) == "" {
			writeJSON(w, http.StatusNotFound, map[string]any{"success": false, "error": "user route not found"})
			return
		}
		userID := strings.TrimSpace(parts[0])
		switch parts[1] {
		case "connections":
			claims, ok := g.requireAuth(w, r)
			if !ok {
				return
			}
			scopedUserID, allowed := g.resolveUserScope(userID, claims)
			if !allowed {
				writeJSON(w, http.StatusForbidden, map[string]any{"success": false, "error": "forbidden"})
				return
			}
			includeOffline := strings.EqualFold(r.URL.Query().Get("include_offline"), "true") ||
				r.URL.Query().Get("include_offline") == "1"
			writeJSON(w, http.StatusOK, map[string]any{
				"success": true,
				"data":    g.service.ListUserConnections(scopedUserID, includeOffline),
			})
		case "offline-events":
			claims, ok := g.requireAuth(w, r)
			if !ok {
				return
			}
			scopedUserID, allowed := g.resolveUserScope(userID, claims)
			if !allowed {
				writeJSON(w, http.StatusForbidden, map[string]any{"success": false, "error": "forbidden"})
				return
			}
			writeJSON(w, http.StatusOK, map[string]any{
				"success": true,
				"data":    g.service.ListPendingEvents(scopedUserID),
			})
		default:
			writeJSON(w, http.StatusNotFound, map[string]any{"success": false, "error": "user route not found"})
		}
	}
}

func (g gatewayRoutes) handleEventByID(prefix string) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		path := strings.TrimSpace(strings.TrimPrefix(r.URL.Path, prefix+"/events/"))
		parts := strings.Split(path, "/")
		if len(parts) == 2 && parts[1] == "ack" {
			g.handleEventAck(w, r, strings.TrimSpace(parts[0]))
			return
		}

		if r.Method != http.MethodGet {
			writeJSON(w, http.StatusMethodNotAllowed, map[string]any{"error": "method not allowed"})
			return
		}
		claims, ok := g.requireAuth(w, r)
		if !ok {
			return
		}
		eventID := strings.TrimSpace(parts[0])
		event, ok := g.service.GetEvent(eventID)
		if !ok {
			writeJSON(w, http.StatusNotFound, map[string]any{"success": false, "error": "event not found"})
			return
		}
		if !g.canReadEvent(claims, event) {
			writeJSON(w, http.StatusForbidden, map[string]any{"success": false, "error": "forbidden"})
			return
		}
		writeJSON(w, http.StatusOK, map[string]any{
			"success": true,
			"data":    event,
		})
	}
}

func (g gatewayRoutes) handlePush(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		writeJSON(w, http.StatusMethodNotAllowed, map[string]any{"error": "method not allowed"})
		return
	}
	claims, ok := g.requireAuth(w, r)
	if !ok {
		return
	}
	var body struct {
		EventID         string         `json:"event_id"`
		CreatedAt       string         `json:"created_at"`
		UserID          string         `json:"user_id"`
		Event           string         `json:"event"`
		EventType       string         `json:"event_type"`
		Payload         map[string]any `json:"payload"`
		Target          string         `json:"target"`
		DeviceID        string         `json:"device_id"`
		ExcludeDeviceID string         `json:"exclude_device_id"`
		ConnectionID    string         `json:"connection_id"`
		ConversationID  string         `json:"conversation_id"`
		MessageID       string         `json:"message_id"`
		Metadata        map[string]any `json:"metadata"`
	}
	if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
		writeJSON(w, http.StatusBadRequest, map[string]any{"success": false, "error": "invalid json body"})
		return
	}
	eventType := strings.TrimSpace(body.Event)
	if eventType == "" {
		eventType = strings.TrimSpace(body.EventType)
	}
	userID := strings.TrimSpace(body.UserID)
	scopedUserID, allowed := g.resolveUserScope(userID, claims)
	if !allowed || strings.TrimSpace(scopedUserID) == "" {
		writeJSON(w, http.StatusForbidden, map[string]any{"success": false, "error": "forbidden"})
		return
	}
	if eventType == "" {
		writeJSON(w, http.StatusBadRequest, map[string]any{"success": false, "error": "event is required"})
		return
	}
	createdAt := time.Time{}
	if strings.TrimSpace(body.CreatedAt) != "" {
		parsedCreatedAt, err := time.Parse(time.RFC3339Nano, strings.TrimSpace(body.CreatedAt))
		if err != nil {
			writeJSON(w, http.StatusBadRequest, map[string]any{"success": false, "error": "created_at must be RFC3339"})
			return
		}
		createdAt = parsedCreatedAt.UTC()
	}
	result := g.service.Publish(gateway.Event{
		EventID:         strings.TrimSpace(body.EventID),
		UserID:          scopedUserID,
		EventType:       eventType,
		Target:          gateway.NormalizeTarget(strings.ToUpper(strings.TrimSpace(body.Target))),
		DeviceID:        strings.TrimSpace(body.DeviceID),
		ExcludeDeviceID: strings.TrimSpace(body.ExcludeDeviceID),
		ConnectionID:    strings.TrimSpace(body.ConnectionID),
		ConversationID:  strings.TrimSpace(body.ConversationID),
		MessageID:       strings.TrimSpace(body.MessageID),
		Payload:         body.Payload,
		Metadata:        body.Metadata,
		CreatedAt:       createdAt,
	})
	writeJSON(w, http.StatusOK, map[string]any{
		"success": true,
		"data":    result,
	})
}

func (g gatewayRoutes) handleConnections(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		writeJSON(w, http.StatusMethodNotAllowed, map[string]any{"error": "method not allowed"})
		return
	}
	claims, ok := g.requireAuth(w, r)
	if !ok {
		return
	}
	var body struct {
		ConnectionID string         `json:"connection_id"`
		UserID       string         `json:"user_id"`
		SID          string         `json:"sid"`
		Namespace    string         `json:"namespace"`
		DeviceID     string         `json:"device_id"`
		Metadata     map[string]any `json:"metadata"`
	}
	if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
		writeJSON(w, http.StatusBadRequest, map[string]any{"success": false, "error": "invalid json body"})
		return
	}
	if strings.TrimSpace(body.UserID) == "" || strings.TrimSpace(body.SID) == "" {
		writeJSON(w, http.StatusBadRequest, map[string]any{"success": false, "error": "user_id and sid are required"})
		return
	}
	scopedUserID, allowed := g.resolveUserScope(body.UserID, claims)
	if !allowed {
		writeJSON(w, http.StatusForbidden, map[string]any{"success": false, "error": "forbidden"})
		return
	}
	namespace := strings.TrimSpace(body.Namespace)
	if namespace == "" {
		namespace = g.cfg.Namespace
	}
	connection := g.service.Connect(
		strings.TrimSpace(body.ConnectionID),
		scopedUserID,
		body.SID,
		namespace,
		body.DeviceID,
		body.Metadata,
	)
	writeJSON(w, http.StatusCreated, map[string]any{
		"success": true,
		"data":    connection,
	})
}

func (g gatewayRoutes) handleConnectionByID(prefix string) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		path := strings.TrimPrefix(r.URL.Path, prefix+"/connections/")
		parts := strings.Split(path, "/")
		if len(parts) == 0 || strings.TrimSpace(parts[0]) == "" {
			writeJSON(w, http.StatusNotFound, map[string]any{"success": false, "error": "connection not found"})
			return
		}
		connectionID := strings.TrimSpace(parts[0])
		connection, ok := g.service.GetConnection(connectionID)
		if !ok {
			writeJSON(w, http.StatusNotFound, map[string]any{"success": false, "error": "connection not found"})
			return
		}
		claims, ok := g.requireAuth(w, r)
		if !ok {
			return
		}
		if !g.canManageConnection(claims, connection) {
			writeJSON(w, http.StatusForbidden, map[string]any{"success": false, "error": "forbidden"})
			return
		}

		if len(parts) == 2 && parts[1] == "heartbeat" {
			if r.Method != http.MethodPost {
				writeJSON(w, http.StatusMethodNotAllowed, map[string]any{"error": "method not allowed"})
				return
			}
			connection, ok := g.service.Touch(connectionID)
			if !ok {
				writeJSON(w, http.StatusNotFound, map[string]any{"success": false, "error": "connection not found"})
				return
			}
			writeJSON(w, http.StatusOK, map[string]any{"success": true, "data": connection})
			return
		}

		if len(parts) == 2 && parts[1] == "replay-pending" {
			if r.Method != http.MethodPost {
				writeJSON(w, http.StatusMethodNotAllowed, map[string]any{"error": "method not allowed"})
				return
			}
			replayed, ok := g.service.ReplayPending(connectionID)
			if !ok {
				writeJSON(w, http.StatusNotFound, map[string]any{"success": false, "error": "connection not found"})
				return
			}
			writeJSON(w, http.StatusOK, map[string]any{
				"success": true,
				"data": map[string]any{
					"connection_id":  connectionID,
					"replayed":       replayed,
					"replayed_count": len(replayed),
				},
			})
			return
		}

		if r.Method == http.MethodDelete {
			connection, ok := g.service.Disconnect(connectionID)
			if !ok {
				writeJSON(w, http.StatusNotFound, map[string]any{"success": false, "error": "connection not found"})
				return
			}
			writeJSON(w, http.StatusOK, map[string]any{"success": true, "data": connection})
			return
		}

		writeJSON(w, http.StatusMethodNotAllowed, map[string]any{"error": "method not allowed"})
	}
}

func (g gatewayRoutes) handleEventAck(w http.ResponseWriter, r *http.Request, eventID string) {
	if r.Method != http.MethodPost {
		writeJSON(w, http.StatusMethodNotAllowed, map[string]any{"error": "method not allowed"})
		return
	}
	claims, ok := g.requireAuth(w, r)
	if !ok {
		return
	}
	var body struct {
		ConnectionID string         `json:"connection_id"`
		AckPayload   map[string]any `json:"ack_payload"`
	}
	if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
		writeJSON(w, http.StatusBadRequest, map[string]any{"success": false, "error": "invalid json body"})
		return
	}
	connectionID := strings.TrimSpace(body.ConnectionID)
	if connectionID == "" {
		writeJSON(w, http.StatusBadRequest, map[string]any{"success": false, "error": "connection_id is required"})
		return
	}
	connection, ok := g.service.GetConnection(connectionID)
	if !ok {
		writeJSON(w, http.StatusNotFound, map[string]any{"success": false, "error": "connection not found"})
		return
	}
	if !g.canManageConnection(claims, connection) {
		writeJSON(w, http.StatusForbidden, map[string]any{"success": false, "error": "forbidden"})
		return
	}
	event, ok := g.service.GetEvent(eventID)
	if !ok {
		writeJSON(w, http.StatusNotFound, map[string]any{"success": false, "error": "event not found"})
		return
	}
	if !g.canReadEvent(claims, event) {
		writeJSON(w, http.StatusForbidden, map[string]any{"success": false, "error": "forbidden"})
		return
	}
	result, ok := g.service.Ack(eventID, connectionID, body.AckPayload)
	if !ok {
		writeJSON(w, http.StatusNotFound, map[string]any{"success": false, "error": "delivery not found"})
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"success": true, "data": result})
}

func (g gatewayRoutes) requireAuth(w http.ResponseWriter, r *http.Request) (authn.Claims, bool) {
	if !g.cfg.RequireAuth {
		return authn.Claims{}, true
	}
	authHeader := strings.TrimSpace(r.Header.Get("Authorization"))
	if !strings.HasPrefix(authHeader, "Bearer ") {
		writeJSON(w, http.StatusUnauthorized, map[string]any{"success": false, "error": "missing authentication"})
		return authn.Claims{}, false
	}
	token := strings.TrimSpace(strings.TrimPrefix(authHeader, "Bearer "))
	claims, err := authn.VerifyToken(token, g.cfg.AuthSecret)
	if err != nil {
		writeJSON(w, http.StatusUnauthorized, map[string]any{"success": false, "error": "invalid authentication"})
		return authn.Claims{}, false
	}
	return claims, true
}

func (g gatewayRoutes) requireAdmin(w http.ResponseWriter, r *http.Request) (authn.Claims, bool) {
	claims, ok := g.requireAuth(w, r)
	if !ok {
		return authn.Claims{}, false
	}
	if !g.cfg.RequireAuth {
		return claims, true
	}
	if !strings.EqualFold(strings.TrimSpace(claims.Role), "admin") {
		writeJSON(w, http.StatusForbidden, map[string]any{"success": false, "error": "admin access required"})
		return authn.Claims{}, false
	}
	return claims, true
}

func (g gatewayRoutes) resolveUserScope(requestedUserID string, claims authn.Claims) (string, bool) {
	if !g.cfg.RequireAuth {
		return strings.TrimSpace(requestedUserID), true
	}
	requestedUserID = strings.TrimSpace(requestedUserID)
	if requestedUserID == "" || requestedUserID == claims.UserID {
		return claims.UserID, true
	}
	if strings.EqualFold(strings.TrimSpace(claims.Role), "admin") {
		return requestedUserID, true
	}
	return "", false
}

func (g gatewayRoutes) canReadEvent(claims authn.Claims, event map[string]any) bool {
	if !g.cfg.RequireAuth {
		return true
	}
	if strings.EqualFold(strings.TrimSpace(claims.Role), "admin") {
		return true
	}
	userID, _ := event["user_id"].(string)
	return strings.TrimSpace(userID) == claims.UserID
}

func (g gatewayRoutes) canManageConnection(claims authn.Claims, connection gateway.Connection) bool {
	if !g.cfg.RequireAuth {
		return true
	}
	if strings.EqualFold(strings.TrimSpace(claims.Role), "admin") {
		return true
	}
	return strings.TrimSpace(connection.UserID) == claims.UserID
}
