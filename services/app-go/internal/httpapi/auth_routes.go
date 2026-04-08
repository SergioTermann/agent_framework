package httpapi

import (
	"encoding/json"
	"net/http"
	"strconv"
	"strings"
	"time"

	"agent-framework/services/app-go/internal/auth"
)

type authRoutes struct {
	authService *auth.Service
}

func newAuthRoutes(authService *auth.Service) authRoutes {
	return authRoutes{authService: authService}
}

func (a authRoutes) register(mux *http.ServeMux) {
	mux.HandleFunc("/api/v1/auth/register", a.handleRegister)
	mux.HandleFunc("/api/v1/auth/login", a.handleLogin)
	mux.Handle("/api/v1/auth/me", a.requireAuth(http.HandlerFunc(a.handleMe)))
	mux.Handle("/api/v1/users", a.requireAuth(a.requirePermission("user:read", http.HandlerFunc(a.handleUsers))))
	mux.Handle("/api/v1/users/", a.requireAuth(http.HandlerFunc(a.handleUserByID)))
	mux.Handle("/api/v1/organizations", a.requireAuth(a.requirePermission("org:write", http.HandlerFunc(a.handleOrganizations))))
	mux.Handle("/api/v1/organizations/", a.requireAuth(a.requirePermission("org:read", http.HandlerFunc(a.handleOrganizationByID))))
}

func (a authRoutes) handleRegister(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		writeJSON(w, http.StatusMethodNotAllowed, map[string]any{"error": "method not allowed"})
		return
	}
	var body struct {
		Username string `json:"username"`
		Email    string `json:"email"`
		Password string `json:"password"`
		FullName string `json:"full_name"`
	}
	if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
		writeJSON(w, http.StatusBadRequest, map[string]any{"success": false, "error": "invalid json body"})
		return
	}
	user, token, err := a.authService.Register(body.Username, body.Email, body.Password, body.FullName)
	if err != nil {
		writeJSON(w, http.StatusBadRequest, map[string]any{"success": false, "error": err.Error()})
		return
	}
	writeJSON(w, http.StatusCreated, map[string]any{
		"success": true,
		"data": map[string]any{
			"user":  publicUser(user),
			"token": token,
		},
	})
}

func (a authRoutes) handleLogin(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		writeJSON(w, http.StatusMethodNotAllowed, map[string]any{"error": "method not allowed"})
		return
	}
	var body struct {
		Username string `json:"username"`
		Email    string `json:"email"`
		Password string `json:"password"`
	}
	if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
		writeJSON(w, http.StatusBadRequest, map[string]any{"success": false, "error": "invalid json body"})
		return
	}

	usernameOrEmail := strings.TrimSpace(body.Username)
	if usernameOrEmail == "" {
		usernameOrEmail = strings.TrimSpace(body.Email)
	}
	user, token, err := a.authService.Login(usernameOrEmail, body.Password)
	if err != nil {
		writeJSON(w, http.StatusUnauthorized, map[string]any{"success": false, "error": err.Error()})
		return
	}
	logID, _ := auth.NewID()
	a.authService.Store().AddAuditLog(auth.AuditLog{
		LogID:        logID,
		UserID:       user.UserID,
		Action:       "login",
		ResourceType: "auth",
		Timestamp:    time.Now().UTC(),
		IPAddress:    r.RemoteAddr,
		UserAgent:    r.UserAgent(),
	})
	writeJSON(w, http.StatusOK, map[string]any{
		"success": true,
		"data": map[string]any{
			"user":  publicUser(user),
			"token": token,
		},
	})
}

func (a authRoutes) handleMe(w http.ResponseWriter, r *http.Request) {
	user, ok := currentUser(r.Context())
	if !ok {
		writeJSON(w, http.StatusUnauthorized, map[string]any{"success": false, "error": "current user is not available"})
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{
		"success": true,
		"data": map[string]any{
			"user_id":         user.UserID,
			"username":        user.Username,
			"email":           user.Email,
			"full_name":       user.FullName,
			"role":            user.Role,
			"status":          user.Status,
			"organization_id": user.OrganizationID,
			"team_ids":        user.TeamIDs,
			"permissions":     a.authService.PermissionsForUser(user),
			"created_at":      user.CreatedAt,
			"last_login_at":   user.LastLoginAt,
		},
	})
}

func (a authRoutes) requireAuth(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		authHeader := strings.TrimSpace(r.Header.Get("Authorization"))
		if !strings.HasPrefix(authHeader, "Bearer ") {
			writeJSON(w, http.StatusUnauthorized, map[string]any{"success": false, "error": "missing authentication"})
			return
		}
		token := strings.TrimSpace(strings.TrimPrefix(authHeader, "Bearer "))
		claims, err := a.authService.VerifyToken(token)
		if err != nil {
			writeJSON(w, http.StatusUnauthorized, map[string]any{"success": false, "error": "invalid authentication"})
			return
		}
		user, ok := a.authService.Store().GetUserByID(claims.UserID)
		if !ok {
			writeJSON(w, http.StatusUnauthorized, map[string]any{"success": false, "error": "user not found"})
			return
		}
		next.ServeHTTP(w, r.WithContext(withCurrentUser(r.Context(), user)))
	})
}

func (a authRoutes) requirePermission(permission string, next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		user, ok := currentUser(r.Context())
		if !ok {
			writeJSON(w, http.StatusUnauthorized, map[string]any{"success": false, "error": "current user is not available"})
			return
		}
		if !a.authService.CheckPermission(user, permission) {
			writeJSON(w, http.StatusForbidden, map[string]any{"success": false, "error": "permission denied"})
			return
		}
		next.ServeHTTP(w, r)
	})
}

func (a authRoutes) handleUsers(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet {
		writeJSON(w, http.StatusMethodNotAllowed, map[string]any{"error": "method not allowed"})
		return
	}
	query := r.URL.Query()
	organizationID := strings.TrimSpace(query.Get("organization_id"))
	role := auth.UserRole(strings.TrimSpace(query.Get("role")))
	status := auth.UserStatus(strings.TrimSpace(query.Get("status")))
	limit := parseIntOrDefault(query.Get("limit"), 100)
	offset := parseIntOrDefault(query.Get("offset"), 0)

	users := a.authService.ListUsers(organizationID, role, status, limit, offset)
	items := make([]map[string]any, 0, len(users))
	for _, user := range users {
		items = append(items, map[string]any{
			"user_id":         user.UserID,
			"username":        user.Username,
			"email":           user.Email,
			"full_name":       user.FullName,
			"role":            user.Role,
			"status":          user.Status,
			"organization_id": user.OrganizationID,
			"created_at":      user.CreatedAt,
			"last_login_at":   user.LastLoginAt,
		})
	}
	writeJSON(w, http.StatusOK, map[string]any{
		"success": true,
		"data":    items,
		"total":   len(items),
	})
}

func (a authRoutes) handleUserByID(w http.ResponseWriter, r *http.Request) {
	userID := strings.TrimPrefix(r.URL.Path, "/api/v1/users/")
	if strings.TrimSpace(userID) == "" {
		writeJSON(w, http.StatusNotFound, map[string]any{"success": false, "error": "user not found"})
		return
	}

	switch r.Method {
	case http.MethodGet:
		user, ok := a.authService.GetUserByID(userID)
		if !ok {
			writeJSON(w, http.StatusNotFound, map[string]any{"success": false, "error": "user not found"})
			return
		}
		current, ok := currentUser(r.Context())
		if !ok || !a.authService.CheckPermission(current, "user:read") {
			writeJSON(w, http.StatusForbidden, map[string]any{"success": false, "error": "permission denied"})
			return
		}
		writeJSON(w, http.StatusOK, map[string]any{
			"success": true,
			"data": map[string]any{
				"user_id":         user.UserID,
				"username":        user.Username,
				"email":           user.Email,
				"full_name":       user.FullName,
				"role":            user.Role,
				"status":          user.Status,
				"organization_id": user.OrganizationID,
				"team_ids":        user.TeamIDs,
				"permissions":     a.authService.PermissionsForUser(user),
				"created_at":      user.CreatedAt,
				"updated_at":      user.UpdatedAt,
				"last_login_at":   user.LastLoginAt,
			},
		})
	case http.MethodPut:
		current, ok := currentUser(r.Context())
		if !ok || !a.authService.CheckPermission(current, "user:write") {
			writeJSON(w, http.StatusForbidden, map[string]any{"success": false, "error": "permission denied"})
			return
		}
		var body struct {
			FullName       string          `json:"full_name"`
			Role           auth.UserRole   `json:"role"`
			Status         auth.UserStatus `json:"status"`
			OrganizationID string          `json:"organization_id"`
		}
		if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
			writeJSON(w, http.StatusBadRequest, map[string]any{"success": false, "error": "invalid json body"})
			return
		}
		user, err := a.authService.UpdateUser(userID, body.FullName, body.OrganizationID, body.Role, body.Status)
		if err != nil {
			writeJSON(w, http.StatusNotFound, map[string]any{"success": false, "error": err.Error()})
			return
		}
		writeJSON(w, http.StatusOK, map[string]any{
			"success": true,
			"data": map[string]any{
				"user_id":   user.UserID,
				"username":  user.Username,
				"email":     user.Email,
				"full_name": user.FullName,
				"role":      user.Role,
				"status":    user.Status,
			},
		})
	case http.MethodDelete:
		current, ok := currentUser(r.Context())
		if !ok || !a.authService.CheckPermission(current, "user:delete") {
			writeJSON(w, http.StatusForbidden, map[string]any{"success": false, "error": "permission denied"})
			return
		}
		if _, err := a.authService.SoftDeleteUser(userID); err != nil {
			writeJSON(w, http.StatusNotFound, map[string]any{"success": false, "error": err.Error()})
			return
		}
		writeJSON(w, http.StatusOK, map[string]any{
			"success": true,
			"message": "user deleted",
		})
	default:
		writeJSON(w, http.StatusMethodNotAllowed, map[string]any{"error": "method not allowed"})
	}
}

func (a authRoutes) handleOrganizations(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		writeJSON(w, http.StatusMethodNotAllowed, map[string]any{"error": "method not allowed"})
		return
	}
	var body struct {
		Name        string `json:"name"`
		Slug        string `json:"slug"`
		Description string `json:"description"`
	}
	if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
		writeJSON(w, http.StatusBadRequest, map[string]any{"success": false, "error": "invalid json body"})
		return
	}
	org, err := a.authService.CreateOrganization(body.Name, body.Slug, body.Description)
	if err != nil {
		writeJSON(w, http.StatusBadRequest, map[string]any{"success": false, "error": err.Error()})
		return
	}
	writeJSON(w, http.StatusCreated, map[string]any{
		"success": true,
		"data": map[string]any{
			"organization_id": org.OrganizationID,
			"name":            org.Name,
			"slug":            org.Slug,
			"created_at":      org.CreatedAt,
		},
	})
}

func (a authRoutes) handleOrganizationByID(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet {
		writeJSON(w, http.StatusMethodNotAllowed, map[string]any{"error": "method not allowed"})
		return
	}
	organizationID := strings.TrimPrefix(r.URL.Path, "/api/v1/organizations/")
	org, ok := a.authService.GetOrganizationByID(organizationID)
	if !ok {
		writeJSON(w, http.StatusNotFound, map[string]any{"success": false, "error": "organization not found"})
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{
		"success": true,
		"data": map[string]any{
			"organization_id": org.OrganizationID,
			"name":            org.Name,
			"slug":            org.Slug,
			"description":     org.Description,
			"member_count":    org.MemberCount,
			"team_count":      org.TeamCount,
			"created_at":      org.CreatedAt,
			"updated_at":      org.UpdatedAt,
		},
	})
}

func parseIntOrDefault(value string, fallback int) int {
	if strings.TrimSpace(value) == "" {
		return fallback
	}
	parsed, err := strconv.Atoi(value)
	if err != nil {
		return fallback
	}
	return parsed
}

func publicUser(user auth.User) map[string]any {
	return map[string]any{
		"user_id":         user.UserID,
		"username":        user.Username,
		"email":           user.Email,
		"full_name":       user.FullName,
		"role":            user.Role,
		"organization_id": user.OrganizationID,
	}
}
