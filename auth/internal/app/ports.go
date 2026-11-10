package app

import "time"

type TokenManager interface {
	GenerateAccessToken(userID, role string) (accessToken string, err error)
	ValidateAccessToken(tokenString string) (role string, err error)
	GenerateRefreshToken(userID string) (refreshToken string, expiresAt time.Time, err error)
	ValidateRefreshToken(tokenString string) (userID string, err error)
}

type Hasher interface {
	Hash(str string) (string, error)
	Verify(str, hash string) (bool, error)
}
