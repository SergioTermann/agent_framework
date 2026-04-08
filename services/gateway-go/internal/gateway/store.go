package gateway

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"slices"
	"strings"
	"sync"
)

type Store struct {
	mu   sync.Mutex
	path string
}

type snapshot struct {
	Version     int          `json:"version"`
	Connections []Connection `json:"connections"`
	Events      []Event      `json:"events"`
	Deliveries  []Delivery   `json:"deliveries"`
}

func NewStore(path string) *Store {
	return &Store{path: strings.TrimSpace(path)}
}

func (s *Store) Load() (snapshot, bool, error) {
	s.mu.Lock()
	defer s.mu.Unlock()

	if s.path == "" {
		return snapshot{}, false, nil
	}
	if _, err := os.Stat(s.path); err != nil {
		if os.IsNotExist(err) {
			return snapshot{}, false, nil
		}
		return snapshot{}, false, fmt.Errorf("stat gateway store: %w", err)
	}

	data, err := os.ReadFile(s.path)
	if err != nil {
		return snapshot{}, false, fmt.Errorf("read gateway store: %w", err)
	}
	if len(data) == 0 {
		return snapshot{}, false, nil
	}

	var state snapshot
	if err := json.Unmarshal(data, &state); err != nil {
		return snapshot{}, false, fmt.Errorf("decode gateway store: %w", err)
	}
	return state, true, nil
}

func (s *Store) Save(state snapshot) error {
	s.mu.Lock()
	defer s.mu.Unlock()

	if s.path == "" {
		return nil
	}

	slices.SortFunc(state.Connections, func(a, b Connection) int {
		return strings.Compare(a.ConnectionID, b.ConnectionID)
	})
	slices.SortFunc(state.Events, func(a, b Event) int {
		return strings.Compare(a.EventID, b.EventID)
	})
	slices.SortFunc(state.Deliveries, func(a, b Delivery) int {
		if cmp := strings.Compare(a.EventID, b.EventID); cmp != 0 {
			return cmp
		}
		return strings.Compare(a.ConnectionID, b.ConnectionID)
	})

	state.Version = 1
	data, err := json.MarshalIndent(state, "", "  ")
	if err != nil {
		return fmt.Errorf("encode gateway store: %w", err)
	}
	if err := os.MkdirAll(filepath.Dir(s.path), 0o755); err != nil {
		return fmt.Errorf("create gateway store directory: %w", err)
	}
	tmpPath := s.path + ".tmp"
	if err := os.WriteFile(tmpPath, data, 0o644); err != nil {
		return fmt.Errorf("write gateway store temp file: %w", err)
	}
	if err := os.Rename(tmpPath, s.path); err != nil {
		return fmt.Errorf("replace gateway store file: %w", err)
	}
	return nil
}
