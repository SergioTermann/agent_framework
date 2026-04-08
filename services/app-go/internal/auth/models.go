package auth

import "time"

type UserRole string

const (
	RoleAdmin  UserRole = "admin"
	RoleOwner  UserRole = "owner"
	RoleMember UserRole = "member"
	RoleViewer UserRole = "viewer"
	RoleGuest  UserRole = "guest"
)

type UserStatus string

const (
	StatusActive    UserStatus = "active"
	StatusInactive  UserStatus = "inactive"
	StatusSuspended UserStatus = "suspended"
	StatusDeleted   UserStatus = "deleted"
)

type User struct {
	UserID         string         `json:"user_id"`
	Username       string         `json:"username"`
	Email          string         `json:"email"`
	PasswordHash   string         `json:"-"`
	Role           UserRole       `json:"role"`
	Status         UserStatus     `json:"status"`
	CreatedAt      time.Time      `json:"created_at"`
	UpdatedAt      time.Time      `json:"updated_at"`
	LastLoginAt    *time.Time     `json:"last_login_at,omitempty"`
	FullName       string         `json:"full_name,omitempty"`
	AvatarURL      string         `json:"avatar_url,omitempty"`
	Phone          string         `json:"phone,omitempty"`
	Metadata       map[string]any `json:"metadata,omitempty"`
	OrganizationID string         `json:"organization_id,omitempty"`
	TeamIDs        []string       `json:"team_ids,omitempty"`
}

type Organization struct {
	OrganizationID string         `json:"organization_id"`
	Name           string         `json:"name"`
	Slug           string         `json:"slug"`
	CreatedAt      time.Time      `json:"created_at"`
	UpdatedAt      time.Time      `json:"updated_at"`
	Description    string         `json:"description,omitempty"`
	LogoURL        string         `json:"logo_url,omitempty"`
	Website        string         `json:"website,omitempty"`
	Settings       map[string]any `json:"settings,omitempty"`
	MemberCount    int            `json:"member_count"`
	TeamCount      int            `json:"team_count"`
}

type AuditLog struct {
	LogID        string         `json:"log_id"`
	UserID       string         `json:"user_id"`
	Action       string         `json:"action"`
	ResourceType string         `json:"resource_type"`
	ResourceID   string         `json:"resource_id,omitempty"`
	Timestamp    time.Time      `json:"timestamp"`
	IPAddress    string         `json:"ip_address,omitempty"`
	UserAgent    string         `json:"user_agent,omitempty"`
	Details      map[string]any `json:"details,omitempty"`
}

type Claims struct {
	UserID   string   `json:"user_id"`
	Username string   `json:"username"`
	Email    string   `json:"email"`
	Role     UserRole `json:"role"`
	Exp      int64    `json:"exp"`
	Iat      int64    `json:"iat"`
}
