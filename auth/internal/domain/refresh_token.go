package domain

import (
	"context"
	"errors"
	"time"
	"uuid"
)

type RefreshTokenModel struct {
	ID          string
	UserID      string
	HashedToken string
	ExpiresAt   time.Time
	RevokedAt   *time.Time
	CreatedAt   time.Time
}

func NewRefreshTokenModel(
	userID string,
	hashedToken string,
	expiresAt time.Time) *RefreshTokenModel {
	return &RefreshTokenModel{
		ID:          uuid.New().String(),
		UserID:      userID,
		HashedToken: hashedToken,
		ExpiresAt:   expiresAt,
		RevokedAt:   nil,
		CreatedAt:   time.Now(),
	}
}

type RefreshTokenRepo interface {
	Create(ctx context.Context, token *RefreshTokenModel) error
	Get(ctx context.Context, hashedToken string) (*RefreshTokenModel, error)
	Revoke(ctx context.Context, hashedToken string) error
	RevokeAll(ctx context.Context, userID string) error
}

var (
	ErrTokenNotFound = errors.New("token not found")
	ErrTokenRevoked  = errors.New("token revoked")
)
