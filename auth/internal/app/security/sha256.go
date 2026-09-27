package security

import (
	"crypto/sha256"
	"encoding/base64"
	"errors"
	"loregraph_auth/internal/config"
)

type TokenHasher struct {
	salt []byte
}

func NewTokenHasher(cfg config.SHA256Config) *TokenHasher {
	return &TokenHasher{
		salt: cfg.Salt,
	}
}

func (h *TokenHasher) Hash(token string) (string, error) {
	sum := sha256.Sum256(append([]byte(token), h.salt...))
	return base64.StdEncoding.EncodeToString(sum[:]), nil
}

func (h *TokenHasher) Verify(token, stored string) (bool, error) {
	return false, errors.New("not implemented")
}
