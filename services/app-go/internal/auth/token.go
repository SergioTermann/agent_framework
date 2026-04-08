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

var base64URL = base64.RawURLEncoding

func GenerateToken(user User, secret string, expiresIn time.Duration) (string, error) {
	now := time.Now().UTC()
	claims := Claims{
		UserID:   user.UserID,
		Username: user.Username,
		Email:    user.Email,
		Role:     user.Role,
		Exp:      now.Add(expiresIn).Unix(),
		Iat:      now.Unix(),
	}
	header := map[string]string{
		"alg": "HS256",
		"typ": "JWT",
	}
	return signToken(header, claims, secret)
}

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
	return claims, nil
}

func signToken(header any, claims Claims, secret string) (string, error) {
	headerBytes, err := json.Marshal(header)
	if err != nil {
		return "", fmt.Errorf("marshal token header: %w", err)
	}
	payloadBytes, err := json.Marshal(claims)
	if err != nil {
		return "", fmt.Errorf("marshal token payload: %w", err)
	}
	message := base64URL.EncodeToString(headerBytes) + "." + base64URL.EncodeToString(payloadBytes)
	return message + "." + sign(message, secret), nil
}

func sign(message, secret string) string {
	mac := hmac.New(sha256.New, []byte(secret))
	_, _ = mac.Write([]byte(message))
	return base64URL.EncodeToString(mac.Sum(nil))
}
