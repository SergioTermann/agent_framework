package auth

import (
	"path/filepath"
	"testing"
)

func TestRegisterAndLogin(t *testing.T) {
	store := NewStore()
	service := NewService(store, "test-secret")

	user, token, err := service.Register("alice", "alice@example.com", "secret-123", "Alice")
	if err != nil {
		t.Fatalf("register failed: %v", err)
	}
	if user.Username != "alice" {
		t.Fatalf("unexpected username: %s", user.Username)
	}
	if token == "" {
		t.Fatal("expected token")
	}

	loggedIn, loginToken, err := service.Login("alice", "secret-123")
	if err != nil {
		t.Fatalf("login failed: %v", err)
	}
	if loggedIn.UserID != user.UserID {
		t.Fatalf("unexpected user id: %s", loggedIn.UserID)
	}
	if loginToken == "" {
		t.Fatal("expected login token")
	}
}

func TestCheckPermissionByRole(t *testing.T) {
	store := NewStore()
	service := NewService(store, "test-secret")
	user := User{Role: RoleViewer}

	if !service.CheckPermission(user, "workflow:read") {
		t.Fatal("viewer should have workflow:read")
	}
	if service.CheckPermission(user, "workflow:write") {
		t.Fatal("viewer should not have workflow:write")
	}
}

func TestFileStorePersistsUsers(t *testing.T) {
	storePath := filepath.Join(t.TempDir(), "auth-store.json")
	store, err := NewFileStore(storePath)
	if err != nil {
		t.Fatalf("create file store failed: %v", err)
	}
	service := NewService(store, "test-secret")

	user, _, err := service.Register("bob", "bob@example.com", "secret-456", "Bob")
	if err != nil {
		t.Fatalf("register failed: %v", err)
	}

	reloaded, err := NewFileStore(storePath)
	if err != nil {
		t.Fatalf("reload file store failed: %v", err)
	}

	found, ok := reloaded.GetUserByID(user.UserID)
	if !ok {
		t.Fatal("expected persisted user")
	}
	if found.Email != "bob@example.com" {
		t.Fatalf("unexpected email: %s", found.Email)
	}
}

func TestListUpdateDeleteAndOrganizationLifecycle(t *testing.T) {
	store := NewStore()
	service := NewService(store, "test-secret")

	user, _, err := service.Register("carol", "carol@example.com", "secret-789", "Carol")
	if err != nil {
		t.Fatalf("register failed: %v", err)
	}

	org, err := service.CreateOrganization("Acme", "acme", "Acme Org")
	if err != nil {
		t.Fatalf("create organization failed: %v", err)
	}

	updated, err := service.UpdateUser(user.UserID, "Carol Smith", org.OrganizationID, RoleOwner, StatusActive)
	if err != nil {
		t.Fatalf("update user failed: %v", err)
	}
	if updated.OrganizationID != org.OrganizationID {
		t.Fatalf("unexpected organization id: %s", updated.OrganizationID)
	}
	if updated.Role != RoleOwner {
		t.Fatalf("unexpected role: %s", updated.Role)
	}

	users := service.ListUsers(org.OrganizationID, RoleOwner, StatusActive, 100, 0)
	if len(users) != 1 {
		t.Fatalf("expected 1 user, got %d", len(users))
	}

	deleted, err := service.SoftDeleteUser(user.UserID)
	if err != nil {
		t.Fatalf("delete user failed: %v", err)
	}
	if deleted.Status != StatusDeleted {
		t.Fatalf("expected deleted status, got %s", deleted.Status)
	}

	if _, ok := service.GetOrganizationByID(org.OrganizationID); !ok {
		t.Fatal("expected organization to exist")
	}
}
