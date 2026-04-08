package auth

import (
	"crypto/hmac"
	"crypto/sha256"
	"encoding/base64"
	"encoding/json"
	"fmt"
	"strings"
	"time"
)

type Claims struct {
	UserID   string `json:"user_id"`
	Username string `json:"username"`
	Email    string `json:"email"`
	Role     string `json:"role"`
	Exp      int64  `json:"exp"`
	Iat      int64  `json:"iat"`
}

var base64URL = base64.RawURLEncoding

func VerifyToken(token, secret string) (Claims, error) {
	var claims Claims
	parts := strings.Split(token, ".")
	if len(parts) != 3 {
		return claims, fmt.Errorf("invalid token format")
	}

	message := parts[0] + "." + parts[1]
	expected := sign(message, secret)
	if !hmac.Equal([]byte(expected), []byte(parts[2])) {
		return claims, fmt.Errorf("invalid token signature")
	}

	payloadBytes, err := base64URL.DecodeString(parts[1])
	if err != nil {
		return claims, fmt.Errorf("decode token payload: %w", err)
	}
	if err := json.Unmarshal(payloadBytes, &claims); err != nil {
		return claims, fmt.Errorf("unmarshal token payload: %w", err)
	}
	if time.Now().UTC().Unix() >= claims.Exp {
		return claims, fmt.Errorf("token expired")
	}
	if strings.TrimSpace(claims.UserID) == "" {
		return claims, fmt.Errorf("token missing user_id")
	}
	return claims, nil
}

func sign(message, secret string) string {
	mac := hmac.New(sha256.New, []byte(secret))
	_, _ = mac.Write([]byte(message))
	return base64URL.EncodeToString(mac.Sum(nil))
}
