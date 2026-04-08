package gateway

import (
	"log"
	"slices"
	"strings"
	"sync"
	"time"

	"agent-framework/services/gateway-go/internal/config"
)

type Service struct {
	mu                 sync.RWMutex
	store              *Store
	offlineRetention   time.Duration
	completedRetention time.Duration
	node               Node
	connections        map[string]Connection
	userIndex          map[string][]string
	events             map[string]Event
	deliveries         map[string][]Delivery
	persistCh          chan struct{}
	persistDone        chan struct{}
	closeOnce          sync.Once
}

func NewService(cfg config.Config) *Service {
	now := time.Now().UTC()
	service := &Service{
		store:              NewStore(cfg.StateStorePath),
		offlineRetention:   cfg.OfflineRetention,
		completedRetention: cfg.CompletedRetention,
		node: Node{
			NodeID:        cfg.NodeID,
			Address:       cfg.ListenAddr,
			Status:        "UP",
			StartedAt:     now,
			LastHeartbeat: now,
			Metadata: map[string]any{
				"namespace": cfg.Namespace,
			},
			ConnectionCount: 0,
		},
		connections: make(map[string]Connection),
		userIndex:   make(map[string][]string),
		events:      make(map[string]Event),
		deliveries:  make(map[string][]Delivery),
		persistCh:   make(chan struct{}, 1),
		persistDone: make(chan struct{}),
	}
	service.restoreState(cfg, now)
	go service.persistLoop()
	service.Flush()
	return service
}

func (s *Service) ListNodes() []Node {
	s.mu.RLock()
	defer s.mu.RUnlock()
	node := s.node
	return []Node{node}
}

func (s *Service) ListOnlineUsers() []map[string]any {
	s.mu.RLock()
	defer s.mu.RUnlock()
	items := make([]map[string]any, 0, len(s.userIndex))
	for userID, connectionIDs := range s.userIndex {
		if len(connectionIDs) == 0 {
			continue
		}
		var latest time.Time
		onlineCount := 0
		for _, connectionID := range connectionIDs {
			if connection, ok := s.connections[connectionID]; ok {
				if connection.Status == "ONLINE" {
					onlineCount++
					if connection.LastSeenAt.After(latest) {
						latest = connection.LastSeenAt
					}
				}
			}
		}
		if latest.IsZero() {
			continue
		}
		items = append(items, map[string]any{
			"user_id":          userID,
			"connection_count": onlineCount,
			"last_seen_at":     latest,
		})
	}
	return items
}

func (s *Service) Connect(connectionID, userID, sid, namespace, deviceID string, metadata map[string]any) Connection {
	s.mu.Lock()
	defer s.mu.Unlock()

	now := time.Now().UTC()
	connectionID = strings.TrimSpace(connectionID)
	if connectionID == "" {
		connectionID = NewID("conn")
	}
	connection := Connection{
		ConnectionID: connectionID,
		SID:          strings.TrimSpace(sid),
		UserID:       strings.TrimSpace(userID),
		NodeID:       s.node.NodeID,
		Namespace:    strings.TrimSpace(namespace),
		DeviceID:     strings.TrimSpace(deviceID),
		ConnectedAt:  now,
		LastSeenAt:   now,
		Status:       "ONLINE",
		Metadata:     copyMap(metadata),
	}
	s.connections[connection.ConnectionID] = connection
	s.userIndex[connection.UserID] = append(s.userIndex[connection.UserID], connection.ConnectionID)
	s.node.ConnectionCount = s.onlineConnectionCountLocked()
	s.node.LastHeartbeat = now
	s.schedulePersistLocked()
	return connection
}

func (s *Service) Disconnect(connectionID string) (Connection, bool) {
	s.mu.Lock()
	defer s.mu.Unlock()

	connection, ok := s.connections[connectionID]
	if !ok {
		return Connection{}, false
	}
	connection.Status = "OFFLINE"
	connection.LastSeenAt = time.Now().UTC()
	s.connections[connectionID] = connection
	s.node.ConnectionCount = s.onlineConnectionCountLocked()
	s.node.LastHeartbeat = connection.LastSeenAt
	s.schedulePersistLocked()
	return connection, true
}

func (s *Service) GetConnection(connectionID string) (Connection, bool) {
	s.mu.RLock()
	defer s.mu.RUnlock()

	connection, ok := s.connections[connectionID]
	return connection, ok
}

func (s *Service) ReplayPending(connectionID string) ([]map[string]any, bool) {
	s.mu.Lock()
	defer s.mu.Unlock()

	connection, ok := s.connections[connectionID]
	if !ok {
		return nil, false
	}

	events := make([]Event, 0)
	for _, event := range s.events {
		if event.Status != "PENDING_OFFLINE" {
			continue
		}
		if matchesConnection(connection, event) {
			events = append(events, event)
		}
	}
	slices.SortFunc(events, func(a, b Event) int {
		if cmp := a.CreatedAt.Compare(b.CreatedAt); cmp != 0 {
			return cmp
		}
		return strings.Compare(a.EventID, b.EventID)
	})

	replayed := make([]map[string]any, 0, len(events))
	for _, event := range events {
		deliveredAt := time.Now().UTC()
		event.Status = "DELIVERED"
		event.DeliveredAt = &deliveredAt
		s.events[event.EventID] = event
		s.deliveries[event.EventID] = append(s.deliveries[event.EventID], Delivery{
			DeliveryID:   NewID("dlv"),
			EventID:      event.EventID,
			ConnectionID: connection.ConnectionID,
			SID:          connection.SID,
			DeviceID:     connection.DeviceID,
			Status:       "DELIVERED",
			DeliveredAt:  &deliveredAt,
		})
		replayed = append(replayed, map[string]any{
			"event_id":   event.EventID,
			"event_type": event.EventType,
			"envelope":   EventEnvelope(event),
		})
	}
	if len(replayed) > 0 {
		s.schedulePersistLocked()
	}
	return replayed, true
}

func (s *Service) Touch(connectionID string) (Connection, bool) {
	s.mu.Lock()
	defer s.mu.Unlock()

	connection, ok := s.connections[connectionID]
	if !ok {
		return Connection{}, false
	}
	connection.Status = "ONLINE"
	connection.LastSeenAt = time.Now().UTC()
	s.connections[connectionID] = connection
	s.node.ConnectionCount = s.onlineConnectionCountLocked()
	s.node.LastHeartbeat = connection.LastSeenAt
	s.schedulePersistLocked()
	return connection, true
}

func (s *Service) ListUserConnections(userID string, includeOffline bool) []Connection {
	s.mu.RLock()
	defer s.mu.RUnlock()

	connectionIDs := s.userIndex[userID]
	out := make([]Connection, 0, len(connectionIDs))
	for _, connectionID := range connectionIDs {
		connection, ok := s.connections[connectionID]
		if !ok {
			continue
		}
		if !includeOffline && connection.Status != "ONLINE" {
			continue
		}
		out = append(out, connection)
	}
	return out
}

func (s *Service) Publish(event Event) map[string]any {
	s.mu.Lock()
	defer s.mu.Unlock()

	now := time.Now().UTC()
	if strings.TrimSpace(event.EventID) == "" {
		event.EventID = NewID("evt")
	}
	if event.CreatedAt.IsZero() {
		event.CreatedAt = now
	}
	if event.Target == "" {
		event.Target = TargetAll
	}
	if event.Payload == nil {
		event.Payload = map[string]any{}
	}
	if event.Metadata == nil {
		event.Metadata = map[string]any{}
	}

	sessions := s.selectSessionsLocked(event)
	if len(sessions) == 0 {
		event.Status = "PENDING_OFFLINE"
		s.events[event.EventID] = event
		s.schedulePersistLocked()
		return map[string]any{
			"success":         true,
			"event_id":        event.EventID,
			"delivered_count": 0,
			"offline_queued":  true,
		}
	}

	event.Status = "DELIVERED"
	deliveredAt := now
	event.DeliveredAt = &deliveredAt
	s.events[event.EventID] = event

	deliveries := make([]Delivery, 0, len(sessions))
	for _, session := range sessions {
		deliveries = append(deliveries, Delivery{
			DeliveryID:   NewID("dlv"),
			EventID:      event.EventID,
			ConnectionID: session.ConnectionID,
			SID:          session.SID,
			DeviceID:     session.DeviceID,
			Status:       "DELIVERED",
			DeliveredAt:  &deliveredAt,
		})
	}
	s.deliveries[event.EventID] = deliveries
	s.schedulePersistLocked()
	return map[string]any{
		"success":         true,
		"event_id":        event.EventID,
		"delivered_count": len(deliveries),
		"offline_queued":  false,
	}
}

func (s *Service) ListPendingEvents(userID string) []Event {
	s.mu.RLock()
	defer s.mu.RUnlock()

	items := make([]Event, 0)
	for _, event := range s.events {
		if event.UserID == userID && event.Status == "PENDING_OFFLINE" {
			items = append(items, event)
		}
	}
	return items
}

func (s *Service) GetEvent(eventID string) (map[string]any, bool) {
	s.mu.RLock()
	defer s.mu.RUnlock()

	event, ok := s.events[eventID]
	if !ok {
		return nil, false
	}
	result := map[string]any{
		"event_id":          event.EventID,
		"event_type":        event.EventType,
		"user_id":           event.UserID,
		"conversation_id":   event.ConversationID,
		"message_id":        event.MessageID,
		"target":            event.Target,
		"device_id":         event.DeviceID,
		"exclude_device_id": event.ExcludeDeviceID,
		"connection_id":     event.ConnectionID,
		"payload":           event.Payload,
		"metadata":          event.Metadata,
		"status":            event.Status,
		"created_at":        event.CreatedAt,
		"delivered_at":      event.DeliveredAt,
		"acked_at":          event.AckedAt,
		"deliveries":        append([]Delivery(nil), s.deliveries[eventID]...),
	}
	return result, true
}

func (s *Service) Ack(eventID, connectionID string, ackPayload map[string]any) (map[string]any, bool) {
	s.mu.Lock()
	defer s.mu.Unlock()

	event, ok := s.events[eventID]
	if !ok {
		return nil, false
	}

	deliveries := s.deliveries[eventID]
	if len(deliveries) == 0 {
		return nil, false
	}

	ackedAt := time.Now().UTC()
	found := false
	for index := range deliveries {
		if deliveries[index].ConnectionID != connectionID {
			continue
		}
		deliveries[index].Status = "ACKED"
		deliveries[index].AckedAt = &ackedAt
		deliveries[index].AckPayload = copyMap(ackPayload)
		found = true
		break
	}
	if !found {
		return nil, false
	}

	s.deliveries[eventID] = deliveries
	event.Status = "ACKED"
	event.AckedAt = &ackedAt
	s.events[eventID] = event
	s.schedulePersistLocked()

	return map[string]any{
		"success":       true,
		"event_id":      eventID,
		"connection_id": connectionID,
		"acked_at":      ackedAt,
	}, true
}

func (s *Service) restoreState(cfg config.Config, now time.Time) {
	state, ok, err := s.store.Load()
	if err != nil {
		log.Printf("gateway-go store load failed: %v", err)
		return
	}
	if !ok {
		return
	}

	for _, connection := range state.Connections {
		if connection.ConnectionID == "" {
			continue
		}
		connection.Status = "OFFLINE"
		s.connections[connection.ConnectionID] = connection
		s.userIndex[connection.UserID] = append(s.userIndex[connection.UserID], connection.ConnectionID)
	}
	for _, event := range state.Events {
		if event.EventID == "" {
			continue
		}
		s.events[event.EventID] = event
	}
	for _, delivery := range state.Deliveries {
		if delivery.EventID == "" || delivery.ConnectionID == "" {
			continue
		}
		s.deliveries[delivery.EventID] = append(s.deliveries[delivery.EventID], delivery)
	}
	s.pruneLocked(now)

	s.node = Node{
		NodeID:        cfg.NodeID,
		Address:       cfg.ListenAddr,
		Status:        "UP",
		StartedAt:     now,
		LastHeartbeat: now,
		Metadata: map[string]any{
			"namespace": cfg.Namespace,
		},
		ConnectionCount: s.onlineConnectionCountLocked(),
	}
}

func (s *Service) Flush() {
	snapshot := s.snapshot()
	if err := s.store.Save(snapshot); err != nil {
		log.Printf("gateway-go store save failed: %v", err)
	}
}

func (s *Service) Close() {
	s.closeOnce.Do(func() {
		close(s.persistCh)
		<-s.persistDone
	})
}

func (s *Service) persistLoop() {
	defer close(s.persistDone)

	timer := time.NewTimer(time.Hour)
	if !timer.Stop() {
		select {
		case <-timer.C:
		default:
		}
	}

	pending := false
	for {
		var timerCh <-chan time.Time
		if pending {
			timerCh = timer.C
		}

		select {
		case _, ok := <-s.persistCh:
			if !ok {
				if pending {
					if !timer.Stop() {
						select {
						case <-timer.C:
						default:
						}
					}
				}
				s.Flush()
				return
			}
			if pending {
				if !timer.Stop() {
					select {
					case <-timer.C:
					default:
					}
				}
			}
			timer.Reset(50 * time.Millisecond)
			pending = true
		case <-timerCh:
			pending = false
			s.Flush()
		}
	}
}

func (s *Service) schedulePersistLocked() {
	s.pruneLocked(time.Now().UTC())
	select {
	case s.persistCh <- struct{}{}:
	default:
	}
}

func (s *Service) snapshot() snapshot {
	s.mu.RLock()
	defer s.mu.RUnlock()

	now := time.Now().UTC()
	connections := s.prunedConnectionsLocked(now)
	events, allowedEventIDs := s.prunedEventsLocked(now)
	deliveries := s.prunedDeliveriesLocked(allowedEventIDs)

	return snapshot{
		Connections: connections,
		Events:      events,
		Deliveries:  deliveries,
	}
}

func (s *Service) connectionsSnapshotLocked() []Connection {
	items := make([]Connection, 0, len(s.connections))
	for _, connection := range s.connections {
		items = append(items, connection)
	}
	return items
}

func (s *Service) eventsSnapshotLocked() []Event {
	items := make([]Event, 0, len(s.events))
	for _, event := range s.events {
		items = append(items, event)
	}
	return items
}

func (s *Service) deliveriesSnapshotLocked() []Delivery {
	count := 0
	for _, deliveries := range s.deliveries {
		count += len(deliveries)
	}
	items := make([]Delivery, 0, count)
	for _, deliveries := range s.deliveries {
		items = append(items, deliveries...)
	}
	return items
}

func (s *Service) prunedConnectionsLocked(now time.Time) []Connection {
	items := make([]Connection, 0, len(s.connections))
	for _, connection := range s.connections {
		if s.shouldPruneConnection(connection, now) {
			continue
		}
		items = append(items, connection)
	}
	return items
}

func (s *Service) prunedEventsLocked(now time.Time) ([]Event, map[string]struct{}) {
	items := make([]Event, 0, len(s.events))
	allowed := make(map[string]struct{}, len(s.events))
	for _, event := range s.events {
		if s.shouldPruneEvent(event, now) {
			continue
		}
		items = append(items, event)
		allowed[event.EventID] = struct{}{}
	}
	return items, allowed
}

func (s *Service) prunedDeliveriesLocked(allowedEventIDs map[string]struct{}) []Delivery {
	items := make([]Delivery, 0)
	for eventID, deliveries := range s.deliveries {
		if _, ok := allowedEventIDs[eventID]; !ok {
			continue
		}
		items = append(items, deliveries...)
	}
	return items
}

func (s *Service) pruneLocked(now time.Time) {
	for connectionID, connection := range s.connections {
		if s.shouldPruneConnection(connection, now) {
			delete(s.connections, connectionID)
			s.userIndex[connection.UserID] = removeConnectionID(s.userIndex[connection.UserID], connectionID)
			if len(s.userIndex[connection.UserID]) == 0 {
				delete(s.userIndex, connection.UserID)
			}
		}
	}

	for eventID, event := range s.events {
		if s.shouldPruneEvent(event, now) {
			delete(s.events, eventID)
			delete(s.deliveries, eventID)
		}
	}
}

func (s *Service) shouldPruneConnection(connection Connection, now time.Time) bool {
	if connection.Status == "ONLINE" {
		return false
	}
	if s.offlineRetention <= 0 {
		return false
	}
	return now.Sub(connection.LastSeenAt) > s.offlineRetention
}

func (s *Service) shouldPruneEvent(event Event, now time.Time) bool {
	if s.completedRetention <= 0 {
		return false
	}
	switch event.Status {
	case "DELIVERED":
		if event.DeliveredAt == nil {
			return now.Sub(event.CreatedAt) > s.completedRetention
		}
		return now.Sub(*event.DeliveredAt) > s.completedRetention
	case "ACKED":
		if event.AckedAt == nil {
			if event.DeliveredAt != nil {
				return now.Sub(*event.DeliveredAt) > s.completedRetention
			}
			return now.Sub(event.CreatedAt) > s.completedRetention
		}
		return now.Sub(*event.AckedAt) > s.completedRetention
	default:
		return false
	}
}

func (s *Service) onlineConnectionCountLocked() int {
	count := 0
	for _, connection := range s.connections {
		if connection.Status == "ONLINE" {
			count++
		}
	}
	return count
}

func (s *Service) selectSessionsLocked(event Event) []Connection {
	connectionIDs := s.userIndex[event.UserID]
	out := make([]Connection, 0, len(connectionIDs))
	for _, connectionID := range connectionIDs {
		connection, ok := s.connections[connectionID]
		if !ok || connection.Status != "ONLINE" {
			continue
		}
		if matchesConnection(connection, event) {
			out = append(out, connection)
		}
	}
	return out
}

func matchesConnection(connection Connection, event Event) bool {
	switch event.Target {
	case TargetConnection:
		return event.ConnectionID != "" && connection.ConnectionID == event.ConnectionID
	case TargetDevice:
		return event.DeviceID != "" && connection.DeviceID == event.DeviceID
	case TargetExcludeDevice:
		return connection.DeviceID != event.ExcludeDeviceID
	default:
		return true
	}
}

func copyMap(input map[string]any) map[string]any {
	if len(input) == 0 {
		return map[string]any{}
	}
	out := make(map[string]any, len(input))
	for key, value := range input {
		out[key] = value
	}
	return out
}

func removeConnectionID(values []string, target string) []string {
	index := slices.Index(values, target)
	if index < 0 {
		return values
	}
	return append(values[:index], values[index+1:]...)
}
