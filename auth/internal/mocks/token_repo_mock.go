package mocks

import (
	"context"
	"loregraph_auth/internal/domain"

	"github.com/stretchr/testify/mock"
)

type MockTokenRepo struct {
	mock.Mock
}

func (m *MockTokenRepo) Create(ctx context.Context, token *domain.RefreshTokenModel) error {
	args := m.Called(ctx, token)
	return args.Error(0)
}
func (m *MockTokenRepo) Get(ctx context.Context, hashedToken string) (*domain.RefreshTokenModel, error) {
	args := m.Called(ctx, hashedToken)
	return args.Get(0).(*domain.RefreshTokenModel), args.Error(1)
}
func (m *MockTokenRepo) Revoke(ctx context.Context, hashedToken string) error {
	args := m.Called(ctx, hashedToken)
	return args.Error(0)
}
func (m *MockTokenRepo) RevokeAll(ctx context.Context, testUserID string) error {
	args := m.Called(ctx, testUserID)
	return args.Error(0)
}
