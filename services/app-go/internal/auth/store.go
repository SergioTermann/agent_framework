package auth

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"sync"
)

type Store struct {
	mu         sync.RWMutex
	path       string
	byID       map[string]User
	byUsername map[string]string
	byEmail    map[string]string
	orgsByID   map[string]Organization
	orgsBySlug map[string]string
	auditLogs  []AuditLog
	rolePerms  map[UserRole][]string
}

func NewStore() *Store {
	return &Store{
		byID:       make(map[string]User),
		byUsername: make(map[string]string),
		byEmail:    make(map[string]string),
		orgsByID:   make(map[string]Organization),
		orgsBySlug: make(map[string]string),
		rolePerms:  defaultRolePermissions(),
		auditLogs:  make([]AuditLog, 0, 32),
	}
}

func NewFileStore(path string) (*Store, error) {
	store := NewStore()
	store.path = strings.TrimSpace(path)
	if store.path == "" {
		return store, nil
	}
	if err := store.load(); err != nil {
		return nil, err
	}
	return store, nil
}

func (s *Store) CreateUser(user User) error {
	s.mu.Lock()
	defer s.mu.Unlock()

	if _, ok := s.byUsername[strings.ToLower(user.Username)]; ok {
		return fmt.Errorf("username already exists")
	}
	if _, ok := s.byEmail[strings.ToLower(user.Email)]; ok {
		return fmt.Errorf("email already exists")
	}

	s.byID[user.UserID] = user
	s.byUsername[strings.ToLower(user.Username)] = user.UserID
	s.byEmail[strings.ToLower(user.Email)] = user.UserID
	if err := s.saveLocked(); err != nil {
		return err
	}
	return nil
}

func (s *Store) UpdateUser(user User) error {
	s.mu.Lock()
	defer s.mu.Unlock()

	if existing, ok := s.byID[user.UserID]; ok {
		delete(s.byUsername, strings.ToLower(existing.Username))
		delete(s.byEmail, strings.ToLower(existing.Email))
	}
	s.byID[user.UserID] = user
	s.byUsername[strings.ToLower(user.Username)] = user.UserID
	s.byEmail[strings.ToLower(user.Email)] = user.UserID
	return s.saveLocked()
}

func (s *Store) GetUserByID(userID string) (User, bool) {
	s.mu.RLock()
	defer s.mu.RUnlock()
	user, ok := s.byID[userID]
	return user, ok
}

func (s *Store) GetUserByUsername(username string) (User, bool) {
	s.mu.RLock()
	defer s.mu.RUnlock()
	userID, ok := s.byUsername[strings.ToLower(username)]
	if !ok {
		return User{}, false
	}
	user, exists := s.byID[userID]
	return user, exists
}

func (s *Store) GetUserByEmail(email string) (User, bool) {
	s.mu.RLock()
	defer s.mu.RUnlock()
	userID, ok := s.byEmail[strings.ToLower(email)]
	if !ok {
		return User{}, false
	}
	user, exists := s.byID[userID]
	return user, exists
}

func (s *Store) ListUsers(organizationID string, role UserRole, status UserStatus, limit, offset int) []User {
	s.mu.RLock()
	defer s.mu.RUnlock()

	users := make([]User, 0, len(s.byID))
	for _, user := range s.byID {
		if organizationID != "" && user.OrganizationID != organizationID {
			continue
		}
		if role != "" && user.Role != role {
			continue
		}
		if status != "" && user.Status != status {
			continue
		}
		users = append(users, user)
	}

	if offset < 0 {
		offset = 0
	}
	if offset >= len(users) {
		return []User{}
	}
	end := len(users)
	if limit > 0 && offset+limit < end {
		end = offset + limit
	}
	return append([]User(nil), users[offset:end]...)
}

func (s *Store) CreateOrganization(org Organization) error {
	s.mu.Lock()
	defer s.mu.Unlock()

	if _, ok := s.orgsBySlug[strings.ToLower(org.Slug)]; ok {
		return fmt.Errorf("organization slug already exists")
	}

	s.orgsByID[org.OrganizationID] = org
	s.orgsBySlug[strings.ToLower(org.Slug)] = org.OrganizationID
	return s.saveLocked()
}

func (s *Store) GetOrganizationByID(organizationID string) (Organization, bool) {
	s.mu.RLock()
	defer s.mu.RUnlock()
	org, ok := s.orgsByID[organizationID]
	return org, ok
}

func (s *Store) AddAuditLog(log AuditLog) {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.auditLogs = append(s.auditLogs, log)
	_ = s.saveLocked()
}

func (s *Store) PermissionsFor(role UserRole) []string {
	s.mu.RLock()
	defer s.mu.RUnlock()
	perms := s.rolePerms[role]
	out := make([]string, len(perms))
	copy(out, perms)
	return out
}

func defaultRolePermissions() map[UserRole][]string {
	all := []string{
		"workflow:read", "workflow:write", "workflow:delete", "workflow:execute",
		"conversation:read", "conversation:write", "conversation:delete",
		"knowledge:read", "knowledge:write", "knowledge:delete",
		"user:read", "user:write", "user:delete",
		"org:read", "org:write", "org:delete",
	}

	owner := filter(all, func(item string) bool { return !strings.Contains(item, "delete") })
	member := filter(all, func(item string) bool {
		return strings.HasSuffix(item, ":read") || strings.HasSuffix(item, ":write") || strings.HasSuffix(item, ":execute")
	})
	viewer := filter(all, func(item string) bool { return strings.HasSuffix(item, ":read") })

	return map[UserRole][]string{
		RoleAdmin:  all,
		RoleOwner:  owner,
		RoleMember: member,
		RoleViewer: viewer,
		RoleGuest:  {"workflow:read", "conversation:read"},
	}
}

func filter(values []string, keep func(string) bool) []string {
	out := make([]string, 0, len(values))
	for _, value := range values {
		if keep(value) {
			out = append(out, value)
		}
	}
	return out
}

type persistedStore struct {
	Users         []User                `json:"users"`
	Organizations []Organization        `json:"organizations"`
	AuditLogs     []AuditLog            `json:"audit_logs"`
	RolePerms     map[UserRole][]string `json:"role_permissions"`
}

func (s *Store) load() error {
	if _, err := os.Stat(s.path); err != nil {
		if os.IsNotExist(err) {
			return nil
		}
		return fmt.Errorf("stat auth store: %w", err)
	}

	data, err := os.ReadFile(s.path)
	if err != nil {
		return fmt.Errorf("read auth store: %w", err)
	}
	if len(data) == 0 {
		return nil
	}

	var snapshot persistedStore
	if err := json.Unmarshal(data, &snapshot); err != nil {
		return fmt.Errorf("decode auth store: %w", err)
	}

	s.byID = make(map[string]User, len(snapshot.Users))
	s.byUsername = make(map[string]string, len(snapshot.Users))
	s.byEmail = make(map[string]string, len(snapshot.Users))
	s.orgsByID = make(map[string]Organization, len(snapshot.Organizations))
	s.orgsBySlug = make(map[string]string, len(snapshot.Organizations))
	for _, user := range snapshot.Users {
		s.byID[user.UserID] = user
		s.byUsername[strings.ToLower(user.Username)] = user.UserID
		s.byEmail[strings.ToLower(user.Email)] = user.UserID
	}
	for _, org := range snapshot.Organizations {
		s.orgsByID[org.OrganizationID] = org
		s.orgsBySlug[strings.ToLower(org.Slug)] = org.OrganizationID
	}
	s.auditLogs = snapshot.AuditLogs
	if len(snapshot.RolePerms) != 0 {
		s.rolePerms = snapshot.RolePerms
	}
	return nil
}

func (s *Store) saveLocked() error {
	if s.path == "" {
		return nil
	}
	users := make([]User, 0, len(s.byID))
	for _, user := range s.byID {
		users = append(users, user)
	}
	orgs := make([]Organization, 0, len(s.orgsByID))
	for _, org := range s.orgsByID {
		orgs = append(orgs, org)
	}
	snapshot := persistedStore{
		Users:         users,
		Organizations: orgs,
		AuditLogs:     append([]AuditLog(nil), s.auditLogs...),
		RolePerms:     s.rolePerms,
	}
	data, err := json.MarshalIndent(snapshot, "", "  ")
	if err != nil {
		return fmt.Errorf("encode auth store: %w", err)
	}
	if err := os.MkdirAll(filepath.Dir(s.path), 0o755); err != nil {
		return fmt.Errorf("create auth store directory: %w", err)
	}
	tmpPath := s.path + ".tmp"
	if err := os.WriteFile(tmpPath, data, 0o644); err != nil {
		return fmt.Errorf("write auth store temp file: %w", err)
	}
	if err := os.Rename(tmpPath, s.path); err != nil {
		return fmt.Errorf("replace auth store file: %w", err)
	}
	return nil
}
