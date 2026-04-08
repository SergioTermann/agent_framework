package httpapi

import (
	"context"

	"agent-framework/services/app-go/internal/auth"
)

type contextKey string

const userContextKey contextKey = "current_user"

func withCurrentUser(ctx context.Context, user auth.User) context.Context {
	return context.WithValue(ctx, userContextKey, user)
}

func currentUser(ctx context.Context) (auth.User, bool) {
	user, ok := ctx.Value(userContextKey).(auth.User)
	return user, ok
}
