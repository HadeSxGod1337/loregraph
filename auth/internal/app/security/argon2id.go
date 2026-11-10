package security

import (
	"fmt"
	"loregraph_auth/internal/config"

	"github.com/alexedwards/argon2id"
)

type Argon2Hasher struct {
	params *argon2id.Params

	pepper string
}

func NewArgon2Hasher(cfg config.Argon2Config) *Argon2Hasher {
	return &Argon2Hasher{
		params: &argon2id.Params{
			Memory:      cfg.Memory,
			Iterations:  cfg.Iterations,
			Parallelism: cfg.Parallelism,
			SaltLength:  cfg.SaltLength,
			KeyLength:   cfg.KeyLength,
		},

		pepper: cfg.Pepper,
	}
}

func (a *Argon2Hasher) Hash(password string) (string, error) {
	passwordWithPepper := password + a.pepper
	hash, err := argon2id.CreateHash(passwordWithPepper, a.params)
	if err != nil {
		return "", fmt.Errorf("argon2id hash creation failed: %w", err)
	}
	return hash, nil
}

func (a *Argon2Hasher) Verify(password, hash string) (bool, error) {
	passwordWithPepper := password + a.pepper
	ok, err := argon2id.ComparePasswordAndHash(passwordWithPepper, hash)
	if err != nil {
		fmt.Println("Ошибка проверки хэша:", err, " Pass:", passwordWithPepper, " Hash:", hash)
		return false, fmt.Errorf("argon2id hash verification failed: %w", err)
	}
	return ok, nil
}
