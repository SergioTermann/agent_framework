package auth

import (
	"fmt"
	"strings"
	"time"
)

type Service struct {
	store      *Store
	authSecret string
}

func NewService(store *Store, authSecret string) *Service {
	return &Service{
		store:      store,
		authSecret: authSecret,
	}
}

func (s *Service) Register(username, email, password, fullName string) (User, string, error) {
	username = strings.TrimSpace(username)
	email = strings.TrimSpace(email)
	password = strings.TrimSpace(password)
	fullName = strings.TrimSpace(fullName)

	if username == "" || email == "" || password == "" {
		return User{}, "", fmt.Errorf("missing required fields")
	}
	if _, exists := s.store.GetUserByUsername(username); exists {
		return User{}, "", fmt.Errorf("username already exists")
	}
	if _, exists := s.store.GetUserByEmail(email); exists {
		return User{}, "", fmt.Errorf("email already exists")
	}

	passwordHash, err := HashPassword(password)
	if err != nil {
		return User{}, "", err
	}
	userID, err := NewID()
	if err != nil {
		return User{}, "", err
	}

	now := time.Now().UTC()
	user := User{
		UserID:       userID,
		Username:     username,
		Email:        email,
		PasswordHash: passwordHash,
		Role:         RoleMember,
		Status:       StatusActive,
		CreatedAt:    now,
		UpdatedAt:    now,
		FullName:     fullName,
		Metadata:     map[string]any{},
		TeamIDs:      []string{},
	}
	if err := s.store.CreateUser(user); err != nil {
		return User{}, "", err
	}
	token, err := GenerateToken(user, s.authSecret, 24*time.Hour)
	return user, token, err
}

func (s *Service) Login(usernameOrEmail, password string) (User, string, error) {
	usernameOrEmail = strings.TrimSpace(usernameOrEmail)
	password = strings.TrimSpace(password)
	if usernameOrEmail == "" || password == "" {
		return User{}, "", fmt.Errorf("missing required fields")
	}

	var user User
	var ok bool
	if strings.Contains(usernameOrEmail, "@") {
		user, ok = s.store.GetUserByEmail(usernameOrEmail)
	} else {
		user, ok = s.store.GetUserByUsername(usernameOrEmail)
	}
	if !ok {
		return User{}, "", fmt.Errorf("user not found")
	}
	if !VerifyPassword(password, user.PasswordHash) {
		return User{}, "", fmt.Errorf("invalid password")
	}
	if user.Status != StatusActive {
		return User{}, "", fmt.Errorf("user status is %s", user.Status)
	}

	now := time.Now().UTC()
	user.LastLoginAt = &now
	user.UpdatedAt = now
	if err := s.store.UpdateUser(user); err != nil {
		return User{}, "", err
	}

	token, err := GenerateToken(user, s.authSecret, 24*time.Hour)
	return user, token, err
}

func (s *Service) VerifyToken(token string) (Claims, error) {
	return VerifyToken(token, s.authSecret)
}

func (s *Service) PermissionsForUser(user User) []string {
	return s.store.PermissionsFor(user.Role)
}

func (s *Service) GetUserByID(userID string) (User, bool) {
	return s.store.GetUserByID(userID)
}

func (s *Service) ListUsers(organizationID string, role UserRole, status UserStatus, limit, offset int) []User {
	return s.store.ListUsers(organizationID, role, status, limit, offset)
}

func (s *Service) UpdateUser(userID, fullName, organizationID string, role UserRole, status UserStatus) (User, error) {
	user, ok := s.store.GetUserByID(userID)
	if !ok {
		return User{}, fmt.Errorf("user not found")
	}
	if strings.TrimSpace(fullName) != "" {
		user.FullName = strings.TrimSpace(fullName)
	}
	if role != "" {
		user.Role = role
	}
	if status != "" {
		user.Status = status
	}
	if organizationID != "" {
		user.OrganizationID = strings.TrimSpace(organizationID)
	}
	user.UpdatedAt = time.Now().UTC()
	if err := s.store.UpdateUser(user); err != nil {
		return User{}, err
	}
	return user, nil
}

func (s *Service) SoftDeleteUser(userID string) (User, error) {
	user, ok := s.store.GetUserByID(userID)
	if !ok {
		return User{}, fmt.Errorf("user not found")
	}
	user.Status = StatusDeleted
	user.UpdatedAt = time.Now().UTC()
	if err := s.store.UpdateUser(user); err != nil {
		return User{}, err
	}
	return user, nil
}

func (s *Service) CreateOrganization(name, slug, description string) (Organization, error) {
	name = strings.TrimSpace(name)
	slug = strings.TrimSpace(slug)
	description = strings.TrimSpace(description)
	if name == "" || slug == "" {
		return Organization{}, fmt.Errorf("missing required fields")
	}
	id, err := NewID()
	if err != nil {
		return Organization{}, err
	}
	now := time.Now().UTC()
	org := Organization{
		OrganizationID: id,
		Name:           name,
		Slug:           slug,
		CreatedAt:      now,
		UpdatedAt:      now,
		Description:    description,
		Settings:       map[string]any{},
	}
	if err := s.store.CreateOrganization(org); err != nil {
		return Organization{}, err
	}
	return org, nil
}

func (s *Service) GetOrganizationByID(organizationID string) (Organization, bool) {
	return s.store.GetOrganizationByID(organizationID)
}

func (s *Service) CheckPermission(user User, permission string) bool {
	for _, item := range s.PermissionsForUser(user) {
		if item == permission {
			return true
		}
	}
	return false
}

func (s *Service) Store() *Store {
	return s.store
}
