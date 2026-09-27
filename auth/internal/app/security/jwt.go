package security

import (
	"crypto/rsa"
	"errors"
	"fmt"
	"loregraph_auth/internal/config"
	"time"
	"uuid"

	"github.com/golang-jwt/jwt/v5"
)

type JWTManager struct {
	privateKey       *rsa.PrivateKey
	publicKey        *rsa.PublicKey
	AccessTTLMinutes int
	RefreshTTLDays   int
	Issuer           string
}

func NewJWTManager(cfg config.JWTConfig) *JWTManager {
	return &JWTManager{
		privateKey:       cfg.PrivateKey,
		publicKey:        cfg.PublicKey,
		AccessTTLMinutes: cfg.AccessTTLMinutes,
		RefreshTTLDays:   cfg.RefreshTTLDays,
		Issuer:           cfg.Issuer,
	}
}

var (
	ErrInvalidToken   = errors.New("invalid token")
	ErrTokenExpired   = errors.New("token expired")
	ErrUserIDNotMatch = errors.New("user id not match")
)

type AccessClaims struct {
	Role string `json:"role,omitempty"`
	jwt.RegisteredClaims
}

func (j *JWTManager) GenerateAccessToken(userID string, role string) (token string, err error) {
	claims := AccessClaims{
		Role: role,
		RegisteredClaims: jwt.RegisteredClaims{
			Subject:   userID,
			ExpiresAt: jwt.NewNumericDate(time.Now().Add(time.Duration(j.AccessTTLMinutes) * time.Minute)),
			IssuedAt:  jwt.NewNumericDate(time.Now()),
			ID:        uuid.New().String(),
			Issuer:    j.Issuer,
		},
	}
	token, err = jwt.NewWithClaims(jwt.SigningMethodRS256, claims).SignedString(j.privateKey)
	return token, err
}

func (j *JWTManager) ValidateAccessToken(accessToken string) (string, error) {
	claims := &AccessClaims{}
	token, err := jwt.ParseWithClaims(accessToken, claims, func(token *jwt.Token) (interface{}, error) {
		return j.publicKey, nil
	})
	if err != nil {
		if errors.Is(err, jwt.ErrTokenExpired) {
			return "", fmt.Errorf("validate access token: %w", ErrTokenExpired)
		}
		return "", fmt.Errorf("validate access token: %w", err)
	}
	if !token.Valid {
		return "", fmt.Errorf("validate access token: %w", ErrInvalidToken)
	}
	return claims.Subject, nil
}

type RefreshClaims struct {
	jwt.RegisteredClaims
}

func (j *JWTManager) GenerateRefreshToken(userID string) (token string, expiresAt time.Time, err error) {
	expiresAt = time.Now().Add(time.Duration(j.RefreshTTLDays) * 24 * time.Hour)
	claims := RefreshClaims{
		RegisteredClaims: jwt.RegisteredClaims{
			Subject:   userID,
			ExpiresAt: jwt.NewNumericDate(expiresAt),
			IssuedAt:  jwt.NewNumericDate(time.Now()),
			ID:        uuid.New().String(),
			Issuer:    j.Issuer,
		},
	}
	token, err = jwt.NewWithClaims(jwt.SigningMethodRS256, claims).SignedString(j.privateKey)
	return token, expiresAt, err
}

func (j *JWTManager) ValidateRefreshToken(refreshToken string) (string, error) {
	claims := &AccessClaims{}
	token, err := jwt.ParseWithClaims(refreshToken, claims, func(token *jwt.Token) (interface{}, error) {
		return j.publicKey, nil
	})
	if err != nil {
		if errors.Is(err, jwt.ErrTokenExpired) {
			return "", fmt.Errorf("validate refresh token: %w", ErrTokenExpired)
		}
		return "", fmt.Errorf("validate refresh token: %w", err)
	}
	if !token.Valid {
		return "", fmt.Errorf("validate refresh token: %w", ErrInvalidToken)
	}
	return claims.Subject, nil
}
