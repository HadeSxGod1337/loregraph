package app

import (
	"context"
	"errors"
	"log/slog"
	"loregraph_auth/internal/app/security"
	"loregraph_auth/internal/domain"
	"loregraph_auth/internal/mocks"
	"loregraph_auth/internal/testutils"
	"testing"
	"time"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/mock"
)

type testDeps struct {
	userRepo     *mocks.MockUserRepo
	tokenRepo    *mocks.MockTokenRepo
	passHasher   *mocks.MockHasher
	tokenHasher  *mocks.MockHasher
	tokenManager *mocks.MockTokenManager
	service      *AuthService
}

func setupTest(t *testing.T) *testDeps {

	mockUserRepo := new(mocks.MockUserRepo)
	mockTokenRepo := new(mocks.MockTokenRepo)
	mockPassHasher := new(mocks.MockHasher)
	mockTokenHasher := new(mocks.MockHasher)
	mockTokenManager := new(mocks.MockTokenManager)
	logger := slog.Default()

	svc := NewAuthService(
		mockUserRepo,
		mockTokenRepo,
		mockPassHasher,
		mockTokenHasher,
		mockTokenManager,
		logger,
	)

	t.Cleanup(func() {
		mockUserRepo.AssertExpectations(t)
		mockTokenRepo.AssertExpectations(t)
		mockPassHasher.AssertExpectations(t)
		mockTokenHasher.AssertExpectations(t)
		mockTokenManager.AssertExpectations(t)
	})

	return &testDeps{
		userRepo:     mockUserRepo,
		tokenRepo:    mockTokenRepo,
		passHasher:   mockPassHasher,
		tokenHasher:  mockTokenHasher,
		tokenManager: mockTokenManager,
		service:      svc,
	}
}

var (
	errFailed = errors.New("failed")
	expiresAt = time.Date(2026, 1, 1, 0, 0, 0, 0, time.UTC)
)

// ===================
// Login
// ===================

func TestAuthService_Login(t *testing.T) {
	user := &domain.User{ID: testutils.TestUserID, Email: testutils.TestEmail, HashedPassword: testutils.TestHashedPassword, Role: testutils.TestRole}
	tests := []struct {
		name       string
		setupMocks func(*testDeps)

		email    string
		password string

		wantErr         error
		wantErrContains string

		wantAccess  string
		wantRefresh string

		wantUserID string
	}{
		{
			name: "Success",
			setupMocks: func(deps *testDeps) {
				deps.userRepo.On("FindByEmail", mock.Anything, testutils.TestEmail).Return(user, nil)
				deps.passHasher.On("Verify", testutils.TestPassword, testutils.TestHashedPassword).Return(true, nil)

				deps.tokenManager.On("GenerateAccessToken", testutils.TestUserID, testutils.TestRole).Return(testutils.TestAccessToken, nil)
				deps.tokenManager.On("GenerateRefreshToken", testutils.TestUserID).Return(testutils.TestRefreshToken, time.Now().Add(time.Hour), nil)
				deps.tokenHasher.On("Hash", testutils.TestRefreshToken).Return(testutils.TestHashedRefreshToken, nil)
				deps.tokenRepo.On("Create", mock.Anything, mock.AnythingOfType("*domain.RefreshTokenModel")).Return(nil)
			},
			wantErr:     nil,
			wantAccess:  testutils.TestAccessToken,
			wantRefresh: testutils.TestRefreshToken,
			wantUserID:  testutils.TestUserID,
		},
		{
			name: "Invalid credentials",

			setupMocks: func(deps *testDeps) {
			},
			email:       "wrong email",
			wantErr:     domain.ErrUserInvalidCredentials,
			wantAccess:  "",
			wantRefresh: "",
			wantUserID:  "",
		},
		{
			name: "DB FindByEmail: User not found",
			setupMocks: func(deps *testDeps) {
				deps.userRepo.On("FindByEmail", mock.Anything, testutils.TestEmail).Return(nil, domain.ErrUserNotFound)

			},
			wantErr:     domain.ErrUserInvalidCredentials,
			wantAccess:  "",
			wantRefresh: "",
			wantUserID:  "",
		},
		{
			name: "DB FindByEmail: error",
			setupMocks: func(deps *testDeps) {
				deps.userRepo.On("FindByEmail", mock.Anything, testutils.TestEmail).Return(nil, errFailed)
			},
			wantErrContains: "db find by email",
			wantAccess:      "",
			wantRefresh:     "",
			wantUserID:      "",
		},
		{
			name: "Verify: wrong password",
			setupMocks: func(deps *testDeps) {
				deps.userRepo.On("FindByEmail", mock.Anything, testutils.TestEmail).Return(user, nil)
				deps.passHasher.On("Verify", testutils.TestPassword, testutils.TestHashedPassword).Return(false, nil)
			},
			wantErr:     domain.ErrUserInvalidCredentials,
			wantAccess:  "",
			wantRefresh: "",
			wantUserID:  "",
		},
		{
			name: "Verify: error",
			setupMocks: func(deps *testDeps) {
				deps.userRepo.On("FindByEmail", mock.Anything, testutils.TestEmail).Return(user, nil)
				deps.passHasher.On("Verify", testutils.TestPassword, testutils.TestHashedPassword).Return(false, errFailed)
			},
			wantErrContains: "password verification error",
			wantAccess:      "",
			wantRefresh:     "",
			wantUserID:      "",
		},
		{
			name: "generateTokenPair: error",
			setupMocks: func(deps *testDeps) {
				deps.userRepo.On("FindByEmail", mock.Anything, testutils.TestEmail).Return(user, nil)
				deps.passHasher.On("Verify", testutils.TestPassword, testutils.TestHashedPassword).Return(true, nil)

				deps.tokenManager.On("GenerateAccessToken", testutils.TestUserID, testutils.TestRole).Return("", errFailed)
			},
			wantErrContains: "failed to generate access token",
			wantAccess:      "",
			wantRefresh:     "",
			wantUserID:      "",
		},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			deps := setupTest(t)
			ctx := context.Background()

			tt.setupMocks(deps)

			if tt.email == "" {
				tt.email = testutils.TestEmail
			}
			if tt.password == "" {
				tt.password = testutils.TestPassword
			}
			access, refresh, userID, err := deps.service.Login(ctx, tt.email, tt.password)

			testutils.AssertError(t, err, tt.wantErr, tt.wantErrContains)

			assert.Equal(t, tt.wantAccess, access)
			assert.Equal(t, tt.wantRefresh, refresh)
			assert.Equal(t, tt.wantUserID, userID)
		})
	}
}

// ===================
// Register
// ===================

func TestAuthService_Register(t *testing.T) {
	tests := []struct {
		name       string
		setupMocks func(*testDeps)

		email    string
		password string

		wantErr         error
		wantErrContains string

		wantAccess  string
		wantRefresh string
		wantUserID  string
	}{
		{
			name: "Success",

			setupMocks: func(deps *testDeps) {
				deps.userRepo.On("FindByEmail", mock.Anything, testutils.TestEmail).Return(nil, domain.ErrUserNotFound)
				deps.passHasher.On("Hash", testutils.TestPassword).Return(testutils.TestHashedPassword, nil)
				deps.userRepo.On("Create", mock.Anything, mock.MatchedBy(func(u *domain.User) bool {
					u.ID = testutils.TestUserID
					return u.Email == testutils.TestEmail && u.HashedPassword == testutils.TestHashedPassword
				})).Return(nil)

				deps.tokenManager.On("GenerateAccessToken", mock.Anything, testutils.TestRole).Return(testutils.TestAccessToken, nil)
				deps.tokenManager.On("GenerateRefreshToken", mock.Anything).Return(testutils.TestRefreshToken, expiresAt, nil)
				deps.tokenHasher.On("Hash", testutils.TestRefreshToken).Return(testutils.TestHashedRefreshToken, nil)
				deps.tokenRepo.On("Create", mock.Anything, mock.AnythingOfType("*domain.RefreshTokenModel")).Return(nil)
			},
			wantErr:     nil,
			wantAccess:  testutils.TestAccessToken,
			wantRefresh: testutils.TestRefreshToken,
			wantUserID:  testutils.TestUserID,
		},
		{
			name: "Invalid credentials",

			setupMocks: func(deps *testDeps) {
			},
			email:       "wrong email",
			wantErr:     domain.ErrUserInvalidCredentials,
			wantAccess:  "",
			wantRefresh: "",
			wantUserID:  "",
		},
		{
			name: "DB FindByEmail: user already exists",

			setupMocks: func(deps *testDeps) {

				deps.userRepo.On("FindByEmail", mock.Anything, testutils.TestEmail).Return(&domain.User{Email: testutils.TestEmail}, nil)
			},
			wantErr:     domain.ErrUserAlreadyExists,
			wantAccess:  "",
			wantRefresh: "",
			wantUserID:  "",
		},
		{
			name: "DB FindByEmail: error",

			setupMocks: func(deps *testDeps) {
				deps.userRepo.On("FindByEmail", mock.Anything, testutils.TestEmail).Return(nil, errFailed)
			},
			wantErrContains: "db error",
			wantAccess:      "",
			wantRefresh:     "",
			wantUserID:      "",
		},
		{
			name: "Hash: error",

			setupMocks: func(deps *testDeps) {
				deps.userRepo.On("FindByEmail", mock.Anything, testutils.TestEmail).Return(nil, domain.ErrUserNotFound)
				deps.passHasher.On("Hash", testutils.TestPassword).Return("", errFailed)
			},
			wantErrContains: "hash error",
			wantAccess:      "",
			wantRefresh:     "",
			wantUserID:      "",
		},
		{
			name: "DB Create: error",

			setupMocks: func(deps *testDeps) {
				deps.userRepo.On("FindByEmail", mock.Anything, testutils.TestEmail).Return(nil, domain.ErrUserNotFound)
				deps.passHasher.On("Hash", testutils.TestPassword).Return(testutils.TestHashedPassword, nil)
				deps.userRepo.On("Create", mock.Anything, mock.MatchedBy(func(u *domain.User) bool {
					u.ID = testutils.TestUserID
					return u.Email == testutils.TestEmail && u.HashedPassword == testutils.TestHashedPassword
				})).Return(errors.New("failed to create user"))
			},
			wantErrContains: "user create error",
			wantAccess:      "",
			wantRefresh:     "",
			wantUserID:      "",
		},
		{
			name: "generateTokenPair: error",

			setupMocks: func(deps *testDeps) {
				deps.userRepo.On("FindByEmail", mock.Anything, testutils.TestEmail).Return(nil, domain.ErrUserNotFound)
				deps.passHasher.On("Hash", testutils.TestPassword).Return(testutils.TestHashedPassword, nil)
				deps.userRepo.On("Create", mock.Anything, mock.MatchedBy(func(u *domain.User) bool {
					u.ID = testutils.TestUserID
					return u.Email == testutils.TestEmail && u.HashedPassword == testutils.TestHashedPassword
				})).Return(nil)
				deps.tokenManager.On("GenerateAccessToken", mock.Anything, testutils.TestRole).Return(testutils.TestAccessToken, errFailed)
			},
			wantErrContains: "failed to generate access token",
			wantAccess:      "",
			wantRefresh:     "",
			wantUserID:      "",
		},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			deps := setupTest(t)
			ctx := context.Background()

			tt.setupMocks(deps)

			if tt.email == "" {
				tt.email = testutils.TestEmail
			}
			if tt.password == "" {
				tt.password = testutils.TestPassword
			}
			access, refresh, userID, err := deps.service.Register(ctx, tt.email, tt.password)

			testutils.AssertError(t, err, tt.wantErr, tt.wantErrContains)

			assert.Equal(t, tt.wantAccess, access)
			assert.Equal(t, tt.wantRefresh, refresh)
			assert.Equal(t, tt.wantUserID, userID)
		})
	}
}

// ===================
// Refresh
// ===================

func TestAuthService_Refresh(t *testing.T) {
	expiresAt := time.Date(2026, 1, 1, 0, 0, 0, 0, time.UTC)

	tests := []struct {
		name       string
		setupMocks func(*testDeps)

		wantErr         error
		wantErrContains string

		wantAccess  string
		wantRefresh string
	}{
		{
			name: "Success",
			setupMocks: func(deps *testDeps) {
				deps.tokenManager.On("ValidateRefreshToken", testutils.TestRefreshToken).Return(testutils.TestUserID, nil)
				deps.tokenHasher.On("Hash", testutils.TestRefreshToken).Return(testutils.TestHashedRefreshToken, nil)
				deps.tokenRepo.On("Get", mock.Anything, testutils.TestHashedRefreshToken).Return(&domain.RefreshTokenModel{UserID: testutils.TestUserID, HashedToken: testutils.TestHashedRefreshToken, ExpiresAt: time.Now().Add(24 * time.Hour)}, nil)

				deps.userRepo.On("FindRoleByUserID", mock.Anything, testutils.TestUserID).Return(testutils.TestRole, nil)

				deps.tokenManager.On("GenerateAccessToken", testutils.TestUserID, testutils.TestRole).Return(testutils.TestAccessToken, nil)
				deps.tokenManager.On("GenerateRefreshToken", testutils.TestUserID).Return(testutils.TestNewRefreshToken, expiresAt, nil)
				deps.tokenHasher.On("Hash", testutils.TestNewRefreshToken).Return(testutils.TestHashedNewRefreshToken, nil)
				deps.tokenRepo.On("Create", mock.Anything, mock.AnythingOfType("*domain.RefreshTokenModel")).Return(nil)

				deps.tokenRepo.On("Revoke", mock.Anything, testutils.TestHashedRefreshToken).Return(nil)
			},
			wantErr:     nil,
			wantAccess:  testutils.TestAccessToken,
			wantRefresh: testutils.TestNewRefreshToken,
		},
		{
			name: "validateRefreshTokenWithDB: error",
			setupMocks: func(deps *testDeps) {
				deps.tokenManager.On("ValidateRefreshToken", testutils.TestRefreshToken).Return(testutils.TestUserID, errFailed)
			},
			wantErrContains: "failed to validate refresh token",
			wantAccess:      "",
			wantRefresh:     "",
		},
		{
			name: "getUserRole: error",
			setupMocks: func(deps *testDeps) {
				deps.tokenManager.On("ValidateRefreshToken", testutils.TestRefreshToken).Return(testutils.TestUserID, nil)
				deps.tokenHasher.On("Hash", testutils.TestRefreshToken).Return(testutils.TestHashedRefreshToken, nil)
				deps.tokenRepo.On("Get", mock.Anything, testutils.TestHashedRefreshToken).Return(&domain.RefreshTokenModel{UserID: testutils.TestUserID, HashedToken: testutils.TestHashedRefreshToken, ExpiresAt: time.Now().Add(24 * time.Hour)}, nil)

				deps.userRepo.On("FindRoleByUserID", mock.Anything, testutils.TestUserID).Return("", errFailed)
			},
			wantErrContains: "failed",
			wantAccess:      "",
			wantRefresh:     "",
		},
		{
			name: "generateTokenPair: error",
			setupMocks: func(deps *testDeps) {
				deps.tokenManager.On("ValidateRefreshToken", testutils.TestRefreshToken).Return(testutils.TestUserID, nil)
				deps.tokenHasher.On("Hash", testutils.TestRefreshToken).Return(testutils.TestHashedRefreshToken, nil)
				deps.tokenRepo.On("Get", mock.Anything, testutils.TestHashedRefreshToken).Return(&domain.RefreshTokenModel{UserID: testutils.TestUserID, HashedToken: testutils.TestHashedRefreshToken, ExpiresAt: time.Now().Add(24 * time.Hour)}, nil)

				deps.userRepo.On("FindRoleByUserID", mock.Anything, testutils.TestUserID).Return(testutils.TestRole, nil)

				deps.tokenManager.On("GenerateAccessToken", testutils.TestUserID, testutils.TestRole).Return(testutils.TestAccessToken, errFailed)
			},
			wantErrContains: "failed",
			wantAccess:      "",
			wantRefresh:     "",
		},
		{
			name: "Revoke: error",
			setupMocks: func(deps *testDeps) {
				deps.tokenManager.On("ValidateRefreshToken", testutils.TestRefreshToken).Return(testutils.TestUserID, nil)
				deps.tokenHasher.On("Hash", testutils.TestRefreshToken).Return(testutils.TestHashedRefreshToken, nil)
				deps.tokenRepo.On("Get", mock.Anything, testutils.TestHashedRefreshToken).Return(&domain.RefreshTokenModel{UserID: testutils.TestUserID, HashedToken: testutils.TestHashedRefreshToken, ExpiresAt: time.Now().Add(24 * time.Hour)}, nil)

				deps.userRepo.On("FindRoleByUserID", mock.Anything, testutils.TestUserID).Return(testutils.TestRole, nil)

				deps.tokenManager.On("GenerateAccessToken", testutils.TestUserID, testutils.TestRole).Return(testutils.TestAccessToken, nil)
				deps.tokenManager.On("GenerateRefreshToken", testutils.TestUserID).Return(testutils.TestNewRefreshToken, expiresAt, nil)
				deps.tokenHasher.On("Hash", testutils.TestNewRefreshToken).Return(testutils.TestHashedNewRefreshToken, nil)
				deps.tokenRepo.On("Create", mock.Anything, mock.AnythingOfType("*domain.RefreshTokenModel")).Return(nil)

				deps.tokenRepo.On("Revoke", mock.Anything, testutils.TestHashedRefreshToken).Return(errFailed)
			},
			wantErrContains: "revoke old refresh token error",
			wantAccess:      "",
			wantRefresh:     "",
		},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			deps := setupTest(t)
			ctx := context.Background()

			tt.setupMocks(deps)

			access, refresh, err := deps.service.Refresh(ctx, testutils.TestRefreshToken)

			testutils.AssertError(t, err, tt.wantErr, tt.wantErrContains)

			assert.Equal(t, tt.wantAccess, access)
			assert.Equal(t, tt.wantRefresh, refresh)
		})
	}
}

// ===================
// ValidateToken
// ===================

func TestAuthService_ValidateToken(t *testing.T) {

	tests := []struct {
		name       string
		setupMocks func(*testDeps)

		wantErr         error
		wantErrContains string

		wantUserID string
	}{
		{
			name: "Success",
			setupMocks: func(deps *testDeps) {
				deps.tokenManager.On("ValidateAccessToken", testutils.TestAccessToken).Return(testutils.TestUserID, nil)
			},
			wantErr:    nil,
			wantUserID: testutils.TestUserID,
		},
		{
			name: "ValidateAccessToken: invalid token",
			setupMocks: func(deps *testDeps) {
				deps.tokenManager.On("ValidateAccessToken", testutils.TestAccessToken).Return("", security.ErrInvalidToken)
			},
			wantErr:    security.ErrInvalidToken,
			wantUserID: "",
		},
		{
			name: "ValidateAccessToken: expired",
			setupMocks: func(deps *testDeps) {
				deps.tokenManager.On("ValidateAccessToken", testutils.TestAccessToken).Return("", security.ErrTokenExpired)
			},
			wantErr:    security.ErrTokenExpired,
			wantUserID: "",
		},
		{
			name: "ValidateAccessToken: error",
			setupMocks: func(deps *testDeps) {
				deps.tokenManager.On("ValidateAccessToken", testutils.TestAccessToken).Return("", errFailed)
			},
			wantErrContains: "token validation error",
			wantUserID:      "",
		},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			deps := setupTest(t)
			ctx := context.Background()

			tt.setupMocks(deps)

			userID, err := deps.service.ValidateToken(ctx, testutils.TestAccessToken)

			if tt.wantErr != nil {
				assert.ErrorIs(t, err, tt.wantErr)
			}
			if tt.wantErrContains != "" {
				assert.Error(t, err)
				assert.Contains(t, err.Error(), tt.wantErrContains)
			}
			if tt.wantErr == nil && tt.wantErrContains == "" {
				assert.NoError(t, err)
			}

			assert.Equal(t, tt.wantUserID, userID)

			deps.tokenManager.AssertExpectations(t)
		})
	}
}

// ===================
// Logout
// ===================

func TestAuthService_Logout(t *testing.T) {

	tests := []struct {
		name       string
		setupMocks func(*testDeps)

		wantErr         error
		wantErrContains string
	}{
		{
			name: "Success",
			setupMocks: func(deps *testDeps) {
				deps.tokenManager.On("ValidateRefreshToken", testutils.TestRefreshToken).Return(testutils.TestUserID, nil)
				deps.tokenHasher.On("Hash", testutils.TestRefreshToken).Return(testutils.TestHashedRefreshToken, nil)
				deps.tokenRepo.On("Get", mock.Anything, testutils.TestHashedRefreshToken).Return(&domain.RefreshTokenModel{
					UserID: testutils.TestUserID, HashedToken: testutils.TestHashedRefreshToken, ExpiresAt: time.Now().Add(24 * time.Hour)}, nil)

				deps.tokenRepo.On("Revoke", mock.Anything, testutils.TestHashedRefreshToken).Return(nil)
			},
			wantErr: nil,
		},
		{
			name: "validateRefreshTokenWithDB: invalid token",
			setupMocks: func(deps *testDeps) {
				deps.tokenManager.On("ValidateRefreshToken", testutils.TestRefreshToken).Return(testutils.TestUserID, errFailed)
			},
			wantErrContains: "failed to validate refresh token",
		},
		{
			name: "Revoke: Token not found",
			setupMocks: func(deps *testDeps) {

				deps.tokenManager.On("ValidateRefreshToken", testutils.TestRefreshToken).Return(testutils.TestUserID, nil)
				deps.tokenHasher.On("Hash", testutils.TestRefreshToken).Return(testutils.TestHashedRefreshToken, nil)
				deps.tokenRepo.On("Get", mock.Anything, testutils.TestHashedRefreshToken).Return(&domain.RefreshTokenModel{
					UserID: testutils.TestUserID, HashedToken: testutils.TestHashedRefreshToken, ExpiresAt: time.Now().Add(24 * time.Hour)}, nil)

				deps.tokenRepo.On("Revoke", mock.Anything, testutils.TestHashedRefreshToken).Return(domain.ErrTokenNotFound)
			},
			wantErr: domain.ErrTokenNotFound,
		},
		{
			name: "Revoke: Invalid refresh token",
			setupMocks: func(deps *testDeps) {

				deps.tokenManager.On("ValidateRefreshToken", testutils.TestRefreshToken).Return(testutils.TestUserID, nil)
				deps.tokenHasher.On("Hash", testutils.TestRefreshToken).Return(testutils.TestHashedRefreshToken, nil)
				deps.tokenRepo.On("Get", mock.Anything, testutils.TestHashedRefreshToken).Return(&domain.RefreshTokenModel{
					UserID: testutils.TestUserID, HashedToken: testutils.TestHashedRefreshToken, ExpiresAt: time.Now().Add(24 * time.Hour)}, nil)

				deps.tokenRepo.On("Revoke", mock.Anything, testutils.TestHashedRefreshToken).Return(errFailed)
			},
			wantErrContains: "refresh token revoke error",
		},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			deps := setupTest(t)
			ctx := context.Background()

			tt.setupMocks(deps)

			err := deps.service.Logout(ctx, testutils.TestRefreshToken)

			testutils.AssertError(t, err, tt.wantErr, tt.wantErrContains)
		})
	}
}

// ===================
// LogoutAll
// ===================

func TestAuthService_LogoutAll(t *testing.T) {

	tests := []struct {
		name       string
		setupMocks func(*testDeps)

		wantErr         error
		wantErrContains string
	}{
		{
			name: "Success",
			setupMocks: func(deps *testDeps) {
				deps.tokenManager.On("ValidateRefreshToken", testutils.TestRefreshToken).Return(testutils.TestUserID, nil)
				deps.tokenHasher.On("Hash", testutils.TestRefreshToken).Return(testutils.TestHashedRefreshToken, nil)
				deps.tokenRepo.On("Get", mock.Anything, testutils.TestHashedRefreshToken).Return(&domain.RefreshTokenModel{
					UserID: testutils.TestUserID, HashedToken: testutils.TestHashedRefreshToken, ExpiresAt: time.Now().Add(24 * time.Hour)}, nil)

				deps.tokenRepo.On("RevokeAll", mock.Anything, testutils.TestUserID).Return(nil)
			},
			wantErr: nil,
		},
		{
			name: "validateRefreshTokenWithDB: error",
			setupMocks: func(deps *testDeps) {
				deps.tokenManager.On("ValidateRefreshToken", testutils.TestRefreshToken).Return("", errFailed)
			},
			wantErrContains: "failed to validate refresh token",
		},
		{
			name: "RevokeAll: error",
			setupMocks: func(deps *testDeps) {
				deps.tokenManager.On("ValidateRefreshToken", testutils.TestRefreshToken).Return(testutils.TestUserID, nil)
				deps.tokenHasher.On("Hash", testutils.TestRefreshToken).Return(testutils.TestHashedRefreshToken, nil)
				deps.tokenRepo.On("Get", mock.Anything, testutils.TestHashedRefreshToken).Return(&domain.RefreshTokenModel{
					UserID: testutils.TestUserID, HashedToken: testutils.TestHashedRefreshToken, ExpiresAt: time.Now().Add(24 * time.Hour)}, nil)

				deps.tokenRepo.On("RevokeAll", mock.Anything, testutils.TestUserID).Return(errFailed)
			},
			wantErrContains: "refresh token revoke all error",
		},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			deps := setupTest(t)
			ctx := context.Background()

			tt.setupMocks(deps)

			err := deps.service.LogoutAll(ctx, testutils.TestRefreshToken)

			testutils.AssertError(t, err, tt.wantErr, tt.wantErrContains)

		})
	}
}

// ===================
// generateTokenPair
// ===================

func TestGenerateTokenPair(t *testing.T) {
	tests := []struct {
		name       string
		setupMocks func(*testDeps)

		wantErr         error
		wantErrContains string

		wantAccess  string
		wantRefresh string
	}{
		{
			name: "Success",
			setupMocks: func(deps *testDeps) {
				deps.tokenManager.On("GenerateAccessToken", testutils.TestUserID, testutils.TestRole).Return(testutils.TestAccessToken, nil)
				deps.tokenManager.On("GenerateRefreshToken", testutils.TestUserID).Return(testutils.TestRefreshToken, time.Now().Add(time.Hour), nil)
				deps.tokenHasher.On("Hash", testutils.TestRefreshToken).Return(testutils.TestHashedRefreshToken, nil)
				deps.tokenRepo.On("Create", mock.Anything, mock.AnythingOfType("*domain.RefreshTokenModel")).Return(nil)
			},
			wantErr:     nil,
			wantAccess:  testutils.TestAccessToken,
			wantRefresh: testutils.TestRefreshToken,
		},
		{
			name: "GenerateAccessToken: generation error",
			setupMocks: func(deps *testDeps) {
				deps.tokenManager.On("GenerateAccessToken", testutils.TestUserID, testutils.TestRole).Return("", errFailed)

			},
			wantErrContains: "failed to generate access token",
			wantAccess:      "",
			wantRefresh:     "",
		},
		{
			name: "GenerateRefreshToken: generation error",
			setupMocks: func(deps *testDeps) {
				deps.tokenManager.On("GenerateAccessToken", testutils.TestUserID, testutils.TestRole).Return(testutils.TestAccessToken, nil)
				deps.tokenManager.On("GenerateRefreshToken", testutils.TestUserID).Return("", time.Now().Add(24*time.Hour), errFailed)
			},
			wantErrContains: "failed to generate refresh token",
			wantAccess:      "",
			wantRefresh:     "",
		},
		{
			name: "Hash: hashing error",
			setupMocks: func(deps *testDeps) {
				deps.tokenManager.On("GenerateAccessToken", testutils.TestUserID, testutils.TestRole).Return(testutils.TestAccessToken, nil)
				deps.tokenManager.On("GenerateRefreshToken", testutils.TestUserID).Return(testutils.TestRefreshToken, time.Now().Add(24*time.Hour), nil)
				deps.tokenHasher.On("Hash", testutils.TestRefreshToken).Return("", errFailed)
			},
			wantErrContains: "failed to hash refresh token",
			wantAccess:      "",
			wantRefresh:     "",
		},
		{
			name: "Create: DB error",
			setupMocks: func(deps *testDeps) {
				deps.tokenManager.On("GenerateAccessToken", testutils.TestUserID, testutils.TestRole).Return(testutils.TestAccessToken, nil)
				deps.tokenManager.On("GenerateRefreshToken", testutils.TestUserID).Return(testutils.TestRefreshToken, time.Now().Add(24*time.Hour), nil)
				deps.tokenHasher.On("Hash", testutils.TestRefreshToken).Return(testutils.TestHashedRefreshToken, nil)
				deps.tokenRepo.On("Create", mock.Anything, mock.AnythingOfType("*domain.RefreshTokenModel")).Return(errFailed)
			},
			wantErrContains: "failed to save refresh token to DB",
			wantAccess:      "",
			wantRefresh:     "",
		},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			deps := setupTest(t)
			ctx := context.Background()

			tt.setupMocks(deps)

			access, refresh, err := deps.service.generateTokenPair(ctx, testutils.TestUserID, testutils.TestRole)

			testutils.AssertError(t, err, tt.wantErr, tt.wantErrContains)

			assert.Equal(t, tt.wantAccess, access)
			assert.Equal(t, tt.wantRefresh, refresh)

		})
	}
}

// ===================
// getUserRole
// ===================

func TestGetUserRole(t *testing.T) {
	tests := []struct {
		name       string
		setupMocks func(*testDeps)

		wantErr         error
		wantErrContains string

		role string
	}{
		{
			name: "Success",
			setupMocks: func(deps *testDeps) {
				deps.userRepo.On("FindRoleByUserID", mock.Anything, testutils.TestUserID).Return(testutils.TestRole, nil)
			},
			wantErr: nil,
			role:    testutils.TestRole,
		},
		{
			name: "Success but FindRoleByUserID: error",
			setupMocks: func(deps *testDeps) {
				deps.userRepo.On("FindRoleByUserID", mock.Anything, testutils.TestUserID).Return(testutils.TestRole, nil)
			},
			wantErr: nil,
			role:    testutils.TestRole,
		},
		{
			name: "Success but CreateRoleByID: error",
			setupMocks: func(deps *testDeps) {
				deps.userRepo.On("FindRoleByUserID", mock.Anything, testutils.TestUserID).Return(testutils.TestRole, nil)
			},
			wantErr: nil,
			role:    testutils.TestRole,
		},
		{
			name: "FindRoleByUserID: not found",
			setupMocks: func(deps *testDeps) {
				deps.userRepo.On("FindRoleByUserID", mock.Anything, testutils.TestUserID).Return("", domain.ErrUserNotFound)
			},
			wantErr: domain.ErrUserNotFound,
			role:    "",
		},
		{
			name: "FindRoleByUserID: not found",
			setupMocks: func(deps *testDeps) {
				deps.userRepo.On("FindRoleByUserID", mock.Anything, testutils.TestUserID).Return("", errFailed)
			},
			wantErrContains: "failed to get user role",
			role:            "",
		},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			deps := setupTest(t)
			ctx := context.Background()

			tt.setupMocks(deps)

			role, err := deps.service.getUserRole(ctx, testutils.TestUserID)

			testutils.AssertError(t, err, tt.wantErr, tt.wantErrContains)

			assert.Equal(t, tt.role, role)

		})
	}

}

// ===================
// validateRefreshTokenWithDB
// ===================

func TestValidateRefreshTokenWithDB(t *testing.T) {
	tests := []struct {
		name       string
		setupMocks func(*testDeps)

		wantErr         error
		wantErrContains string

		userID      string
		hashedToken string
	}{
		{
			name: "Success",
			setupMocks: func(deps *testDeps) {
				deps.tokenManager.On("ValidateRefreshToken", testutils.TestRefreshToken).Return(testutils.TestUserID, nil)
				deps.tokenHasher.On("Hash", testutils.TestRefreshToken).Return(testutils.TestHashedRefreshToken, nil)
				deps.tokenRepo.On("Get", mock.Anything, testutils.TestHashedRefreshToken).Return(&domain.RefreshTokenModel{UserID: testutils.TestUserID, HashedToken: testutils.TestHashedRefreshToken, ExpiresAt: time.Now().Add(24 * time.Hour)}, nil)
			},
			wantErr:     nil,
			userID:      testutils.TestUserID,
			hashedToken: testutils.TestHashedRefreshToken,
		},
		{
			name: "ValidateRefreshToken: invalid token",
			setupMocks: func(deps *testDeps) {
				deps.tokenManager.On("ValidateRefreshToken", testutils.TestRefreshToken).Return(testutils.TestUserID, security.ErrInvalidToken)
			},
			wantErr:     security.ErrInvalidToken,
			userID:      "",
			hashedToken: "",
		},
		{
			name: "ValidateRefreshToken: expired",
			setupMocks: func(deps *testDeps) {
				deps.tokenManager.On("ValidateRefreshToken", testutils.TestRefreshToken).Return(testutils.TestUserID, security.ErrTokenExpired)
			},
			wantErr:     security.ErrTokenExpired,
			userID:      "",
			hashedToken: "",
		},
		{
			name: "ValidateRefreshToken: error",
			setupMocks: func(deps *testDeps) {
				deps.tokenManager.On("ValidateRefreshToken", testutils.TestRefreshToken).Return(testutils.TestUserID, errFailed)
			},
			wantErrContains: "failed to validate refresh token",
			userID:          "",
			hashedToken:     "",
		},
		{
			name: "Hash: error",
			setupMocks: func(deps *testDeps) {
				deps.tokenManager.On("ValidateRefreshToken", testutils.TestRefreshToken).Return(testutils.TestUserID, nil)
				deps.tokenHasher.On("Hash", testutils.TestRefreshToken).Return("", errFailed)
			},
			wantErrContains: "failed to hash refresh token",
			userID:          "",
			hashedToken:     "",
		},
		{
			name: "Get: token not found",
			setupMocks: func(deps *testDeps) {
				deps.tokenManager.On("ValidateRefreshToken", testutils.TestRefreshToken).Return(testutils.TestUserID, nil)
				deps.tokenHasher.On("Hash", testutils.TestRefreshToken).Return(testutils.TestHashedRefreshToken, nil)
				deps.tokenRepo.On("Get", mock.Anything, testutils.TestHashedRefreshToken).Return(&domain.RefreshTokenModel{}, domain.ErrTokenNotFound)
			},
			wantErr:     domain.ErrTokenNotFound,
			userID:      "",
			hashedToken: "",
		},
		{
			name: "Get: token not found error",
			setupMocks: func(deps *testDeps) {
				deps.tokenManager.On("ValidateRefreshToken", testutils.TestRefreshToken).Return(testutils.TestUserID, nil)
				deps.tokenHasher.On("Hash", testutils.TestRefreshToken).Return(testutils.TestHashedRefreshToken, nil)
				deps.tokenRepo.On("Get", mock.Anything, testutils.TestHashedRefreshToken).Return(&domain.RefreshTokenModel{}, errFailed)
			},
			wantErrContains: "refresh token fetch error",
			userID:          "",
			hashedToken:     "",
		},
		{
			name: "UserID dont match",
			setupMocks: func(deps *testDeps) {
				deps.tokenManager.On("ValidateRefreshToken", testutils.TestRefreshToken).Return(testutils.TestOtherUserID, nil)
				deps.tokenHasher.On("Hash", testutils.TestRefreshToken).Return(testutils.TestHashedRefreshToken, nil)
				deps.tokenRepo.On("Get", mock.Anything, testutils.TestHashedRefreshToken).Return(&domain.RefreshTokenModel{UserID: testutils.TestUserID}, nil)

			},
			wantErr:     security.ErrUserIDNotMatch,
			userID:      "",
			hashedToken: "",
		},
		{
			name: "Token revoked",
			setupMocks: func(deps *testDeps) {
				deps.tokenManager.On("ValidateRefreshToken", testutils.TestRefreshToken).Return(testutils.TestUserID, nil)
				deps.tokenHasher.On("Hash", testutils.TestRefreshToken).Return(testutils.TestHashedRefreshToken, nil)
				deps.tokenRepo.On("Get", mock.Anything, testutils.TestHashedRefreshToken).Return(&domain.RefreshTokenModel{UserID: testutils.TestUserID, RevokedAt: &time.Time{}}, nil)

			},
			wantErr:     domain.ErrTokenRevoked,
			userID:      "",
			hashedToken: "",
		},
		{
			name: "Token expired",
			setupMocks: func(deps *testDeps) {
				deps.tokenManager.On("ValidateRefreshToken", testutils.TestRefreshToken).Return(testutils.TestUserID, nil)
				deps.tokenHasher.On("Hash", testutils.TestRefreshToken).Return(testutils.TestHashedRefreshToken, nil)
				deps.tokenRepo.On("Get", mock.Anything, testutils.TestHashedRefreshToken).Return(&domain.RefreshTokenModel{UserID: testutils.TestUserID, ExpiresAt: expiresAt}, nil)

			},
			wantErr:     security.ErrTokenExpired,
			userID:      "",
			hashedToken: "",
		},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			deps := setupTest(t)
			ctx := context.Background()

			tt.setupMocks(deps)

			userID, hashedToken, err := deps.service.validateRefreshTokenWithDB(ctx, testutils.TestRefreshToken)

			testutils.AssertError(t, err, tt.wantErr, tt.wantErrContains)

			assert.Equal(t, tt.userID, userID)
			assert.Equal(t, tt.hashedToken, hashedToken)
		})
	}
}

// ===================
// testTokenPrefix
// ===================

func TestTokenPrefix(t *testing.T) {
	tests := []struct {
		name     string
		token    string
		expected string
	}{
		{
			name:     "token longer than 8 chars",
			token:    "abcdefghijklmnop",
			expected: "abcdefgh",
		},
		{
			name:     "token exactly 8 chars",
			token:    "12345678",
			expected: "12345678",
		},
		{
			name:     "token shorter than 8 chars",
			token:    "short",
			expected: "short",
		},
		{
			name:     "empty token",
			token:    "",
			expected: "",
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			result := tokenPrefix(tt.token)
			assert.Equal(t, tt.expected, result)
		})
	}
}
