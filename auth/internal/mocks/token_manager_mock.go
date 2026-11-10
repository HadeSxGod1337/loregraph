package mocks

import (
	"time"

	"github.com/stretchr/testify/mock"
)

type MockTokenManager struct {
	mock.Mock
}

func (m *MockTokenManager) GenerateAccessToken(testUserID string, testRole string) (testAccessToken string, err error) {
	args := m.Called(testUserID, testRole)
	return args.String(0), args.Error(1)
}
func (m *MockTokenManager) ValidateAccessToken(tokenString string) (testRole string, err error) {
	args := m.Called(tokenString)
	return args.String(0), args.Error(1)
}
func (m *MockTokenManager) GenerateRefreshToken(testUserID string) (testRefreshToken string, expiresAt time.Time, err error) {
	args := m.Called(testUserID)
	return args.String(0), args.Get(1).(time.Time), args.Error(2)
}
func (m *MockTokenManager) ValidateRefreshToken(tokenString string) (testRole string, err error) {
	args := m.Called(tokenString)
	return args.String(0), args.Error(1)
}
