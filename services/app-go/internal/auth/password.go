package auth

import (
	"crypto/hmac"
	"crypto/rand"
	"crypto/sha256"
	"encoding/hex"
	"fmt"
	"strings"
)

const passwordIterations = 100000

func HashPassword(password string) (string, error) {
	salt := make([]byte, 16)
	if _, err := rand.Read(salt); err != nil {
		return "", fmt.Errorf("generate salt: %w", err)
	}
	return hashPasswordWithSalt(password, hex.EncodeToString(salt)), nil
}

func VerifyPassword(password, encoded string) bool {
	parts := strings.Split(encoded, "$")
	if len(parts) != 2 {
		return false
	}
	computed := hashPasswordWithSalt(password, parts[0])
	return hmac.Equal([]byte(computed), []byte(encoded))
}

func hashPasswordWithSalt(password, salt string) string {
	digest := []byte(salt + ":" + password)
	for i := 0; i < passwordIterations; i++ {
		sum := sha256.Sum256(digest)
		digest = sum[:]
	}
	return salt + "$" + hex.EncodeToString(digest)
}
