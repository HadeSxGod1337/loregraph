package rest

import (
	"bytes"
	"encoding/json"
	"errors"
	"log/slog"
	"loregraph_auth/internal/app"
	"loregraph_auth/internal/app/security"
	"loregraph_auth/internal/domain"
	"loregraph_auth/internal/mocks"
	"loregraph_auth/internal/testutils"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/mock"
)

const (
	testTTLDays             = 30
	testTimeContextInSecond = 5
)

type testDeps struct {
	userRepo     *mocks.MockUserRepo
	tokenRepo    *mocks.MockTokenRepo
	passHasher   *mocks.MockHasher
	tokenHasher  *mocks.MockHasher
	tokenManager *mocks.MockTokenManager
	service      *app.AuthService

	handler *AuthHandler
}

func setupTest(t *testing.T) *testDeps {
	mockUserRepo := new(mocks.MockUserRepo)
	mockTokenRepo := new(mocks.MockTokenRepo)
	maxUsers := 10
	mockPassHasher := new(mocks.MockHasher)
	mockTokenHasher := new(mocks.MockHasher)
	mockTokenManager := new(mocks.MockTokenManager)
	logger := slog.Default()

	svc := app.NewAuthService(
		mockUserRepo,
		mockTokenRepo,
		maxUsers,
		mockPassHasher,
		mockTokenHasher,
		mockTokenManager,
		logger,
	)
	hlr := NewAuthHandler(svc, testTTLDays, testTimeContextInSecond, logger)

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
		handler:      hlr,
	}
}

// marshalBody превращает requestBody в []byte.
// Строка передаётся как есть (для кейса "invalid json"),
// остальное сериализуется через json.Marshal.
func marshalBody(t *testing.T, body interface{}) []byte {
	t.Helper()
	if s, ok := body.(string); ok {
		return []byte(s)
	}
	b, err := json.Marshal(body)
	if err != nil {
		t.Fatalf("failed to marshal request body: %v", err)
	}
	return b
}

// ============================================================
// Login
// ============================================================

func TestAuthHandler_HandleLogin(t *testing.T) {
	tests := []struct {
		name           string
		requestBody    interface{}
		setupMocks     func(*testDeps)
		expectedStatus int
		expectedBody   map[string]interface{}
	}{
		{
			name: "Success",
			requestBody: LoginRequest{
				Email:    testutils.TestEmail,
				Password: testutils.TestPassword,
			},
			setupMocks: func(deps *testDeps) {
				deps.userRepo.On("FindByEmail", mock.Anything, testutils.TestEmail).Return(&domain.User{
					ID:             testutils.TestUserID,
					Email:          testutils.TestEmail,
					HashedPassword: testutils.TestHashedPassword,
					Role:           testutils.TestRole,
				}, nil)
				deps.passHasher.On("Verify", testutils.TestPassword, testutils.TestHashedPassword).Return(true, nil)
				deps.tokenManager.On("GenerateAccessToken", testutils.TestUserID, testutils.TestRole).Return(testutils.TestAccessToken, nil)
				deps.tokenManager.On("GenerateRefreshToken", testutils.TestUserID).Return(testutils.TestRefreshToken, time.Now().Add(time.Hour), nil)
				deps.tokenHasher.On("Hash", testutils.TestRefreshToken).Return(testutils.TestHashedRefreshToken, nil)
				deps.tokenRepo.On("Create", mock.Anything, mock.AnythingOfType("*domain.RefreshTokenModel")).Return(nil)
			},
			expectedStatus: http.StatusOK,
			expectedBody: map[string]interface{}{
				"accessToken":  testutils.TestAccessToken,
				"refreshToken": testutils.TestRefreshToken,
				"user": map[string]interface{}{
					"userId": testutils.TestUserID,
					"email":  testutils.TestEmail,
				},
			},
		},
		{
			name:           "Invalid JSON body",
			requestBody:    "invalid json",
			setupMocks:     func(deps *testDeps) {},
			expectedStatus: http.StatusBadRequest,
			expectedBody:   nil,
		},
		{
			name: "Missing email or password",
			requestBody: LoginRequest{
				Email:    "",
				Password: "",
			},
			setupMocks:     func(deps *testDeps) {},
			expectedStatus: http.StatusBadRequest,
			expectedBody:   nil,
		},
		{
			name: "User not found",
			requestBody: LoginRequest{
				Email:    testutils.TestEmail,
				Password: testutils.TestPassword,
			},
			setupMocks: func(deps *testDeps) {
				deps.userRepo.On("FindByEmail", mock.Anything, testutils.TestEmail).Return(nil, domain.ErrUserNotFound)
			},
			expectedStatus: http.StatusUnauthorized,
			expectedBody:   nil,
		},
		{
			name: "Wrong password",
			requestBody: LoginRequest{
				Email:    testutils.TestEmail,
				Password: "wrongPass",
			},
			setupMocks: func(deps *testDeps) {
				deps.userRepo.On("FindByEmail", mock.Anything, testutils.TestEmail).Return(&domain.User{}, domain.ErrUserInvalidCredentials)
			},
			expectedStatus: http.StatusUnauthorized,
			expectedBody:   nil,
		},
		{
			name: "Internal server error (DB error)",
			requestBody: LoginRequest{
				Email:    testutils.TestEmail,
				Password: testutils.TestPassword,
			},
			setupMocks: func(deps *testDeps) {
				deps.userRepo.On("FindByEmail", mock.Anything, testutils.TestEmail).Return(nil, errors.New("db connection lost"))
			},
			expectedStatus: http.StatusInternalServerError,
			expectedBody:   nil,
		},
		{
			name: "Internal server error (token generation error)",
			requestBody: LoginRequest{
				Email:    testutils.TestEmail,
				Password: testutils.TestPassword,
			},
			setupMocks: func(deps *testDeps) {
				deps.userRepo.On("FindByEmail", mock.Anything, testutils.TestEmail).Return(&domain.User{
					ID:             testutils.TestUserID,
					Email:          testutils.TestEmail,
					HashedPassword: testutils.TestHashedPassword,
					Role:           testutils.TestRole,
				}, nil)
				deps.passHasher.On("Verify", testutils.TestPassword, testutils.TestHashedPassword).Return(true, nil)
				deps.tokenManager.On("GenerateAccessToken", testutils.TestUserID, testutils.TestRole).Return("", errors.New("jwt signing failed"))
			},
			expectedStatus: http.StatusInternalServerError,
			expectedBody:   nil,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			deps := setupTest(t)
			tt.setupMocks(deps)

			bodyBytes := marshalBody(t, tt.requestBody)
			req := httptest.NewRequest("POST", "/login", bytes.NewReader(bodyBytes))
			req.Header.Set("Content-Type", "application/json")

			w := httptest.NewRecorder()
			deps.handler.HandleLogin(w, req)

			assert.Equal(t, tt.expectedStatus, w.Code)

			if tt.expectedBody != nil {
				var resp map[string]interface{}
				err := json.NewDecoder(w.Body).Decode(&resp)
				assert.NoError(t, err)
				assert.Equal(t, tt.expectedBody, resp)
			}

			// cookie больше не ставим — проверяем, что их нет вообще
			assert.Empty(t, w.Result().Cookies())
		})
	}
}

// ============================================================
// Register
// ============================================================

func TestAuthHandler_HandleRegister(t *testing.T) {
	tests := []struct {
		name           string
		requestBody    interface{}
		setupMocks     func(*testDeps)
		expectedStatus int
		expectedBody   map[string]interface{}
	}{
		{
			name: "Success",
			requestBody: RegisterRequest{
				Email:    testutils.TestEmail,
				Password: testutils.TestPassword,
			},
			setupMocks: func(deps *testDeps) {
				deps.userRepo.On("FindByEmail", mock.Anything, testutils.TestEmail).
					Return(nil, domain.ErrUserNotFound)
				deps.passHasher.On("Hash", testutils.TestPassword).
					Return(testutils.TestHashedPassword, nil)
				deps.userRepo.On("Create", mock.Anything, mock.MatchedBy(func(u *domain.User) bool {
					u.ID = testutils.TestUserID
					return u.Email == testutils.TestEmail &&
						u.HashedPassword == testutils.TestHashedPassword
				})).Return(nil)
				deps.tokenManager.On("GenerateAccessToken", mock.Anything, testutils.TestRole).
					Return(testutils.TestAccessToken, nil)
				deps.tokenManager.On("GenerateRefreshToken", mock.Anything).
					Return(testutils.TestRefreshToken, time.Now().Add(time.Hour), nil)
				deps.tokenHasher.On("Hash", testutils.TestRefreshToken).
					Return(testutils.TestHashedRefreshToken, nil)
				deps.tokenRepo.On("Create", mock.Anything, mock.AnythingOfType("*domain.RefreshTokenModel")).
					Return(nil)
			},
			expectedStatus: http.StatusCreated,
			expectedBody: map[string]interface{}{
				"accessToken":  testutils.TestAccessToken,
				"refreshToken": testutils.TestRefreshToken,
				"user": map[string]interface{}{
					"userId": testutils.TestUserID,
					"email":  testutils.TestEmail,
				},
			},
		},
		{
			name:           "Invalid JSON body",
			requestBody:    "not a json at all",
			setupMocks:     func(deps *testDeps) {},
			expectedStatus: http.StatusBadRequest,
		},
		{
			name: "Missing email or password",
			requestBody: RegisterRequest{
				Email:    "",
				Password: "",
			},
			setupMocks:     func(deps *testDeps) {},
			expectedStatus: http.StatusBadRequest,
		},
		{
			name: "User already exists",
			requestBody: RegisterRequest{
				Email:    testutils.TestEmail,
				Password: testutils.TestPassword,
			},
			setupMocks: func(deps *testDeps) {
				deps.userRepo.On("FindByEmail", mock.Anything, testutils.TestEmail).
					Return(&domain.User{Email: testutils.TestEmail}, nil)
			},
			expectedStatus: http.StatusConflict,
		},
		{
			name: "DB FindByEmail error",
			requestBody: RegisterRequest{
				Email:    testutils.TestEmail,
				Password: testutils.TestPassword,
			},
			setupMocks: func(deps *testDeps) {
				deps.userRepo.On("FindByEmail", mock.Anything, testutils.TestEmail).
					Return(nil, errors.New("db is down"))
			},
			expectedStatus: http.StatusInternalServerError,
		},
		{
			name: "Password hashing error",
			requestBody: RegisterRequest{
				Email:    testutils.TestEmail,
				Password: testutils.TestPassword,
			},
			setupMocks: func(deps *testDeps) {
				deps.userRepo.On("FindByEmail", mock.Anything, testutils.TestEmail).
					Return(nil, domain.ErrUserNotFound)
				deps.passHasher.On("Hash", testutils.TestPassword).
					Return("", errors.New("hash broken"))
			},
			expectedStatus: http.StatusInternalServerError,
		},
		{
			name: "DB Create error",
			requestBody: RegisterRequest{
				Email:    testutils.TestEmail,
				Password: testutils.TestPassword,
			},
			setupMocks: func(deps *testDeps) {
				deps.userRepo.On("FindByEmail", mock.Anything, testutils.TestEmail).
					Return(nil, domain.ErrUserNotFound)
				deps.passHasher.On("Hash", testutils.TestPassword).
					Return(testutils.TestHashedPassword, nil)
				deps.userRepo.On("Create", mock.Anything, mock.AnythingOfType("*domain.User")).
					Return(errors.New("insert failed"))
			},
			expectedStatus: http.StatusInternalServerError,
		},
		{
			name: "Token generation error",
			requestBody: RegisterRequest{
				Email:    testutils.TestEmail,
				Password: testutils.TestPassword,
			},
			setupMocks: func(deps *testDeps) {
				deps.userRepo.On("FindByEmail", mock.Anything, testutils.TestEmail).
					Return(nil, domain.ErrUserNotFound)
				deps.passHasher.On("Hash", testutils.TestPassword).
					Return(testutils.TestHashedPassword, nil)
				deps.userRepo.On("Create", mock.Anything, mock.MatchedBy(func(u *domain.User) bool {
					u.ID = testutils.TestUserID
					return true
				})).Return(nil)
				deps.tokenManager.On("GenerateAccessToken", mock.Anything, testutils.TestRole).
					Return("", errors.New("jwt signing failed"))
			},
			expectedStatus: http.StatusInternalServerError,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			deps := setupTest(t)
			tt.setupMocks(deps)

			bodyBytes := marshalBody(t, tt.requestBody)
			req := httptest.NewRequest("POST", "/register", bytes.NewReader(bodyBytes))
			req.Header.Set("Content-Type", "application/json")

			w := httptest.NewRecorder()
			deps.handler.HandleRegister(w, req)

			assert.Equal(t, tt.expectedStatus, w.Code)

			if tt.expectedBody != nil {
				var resp map[string]interface{}
				err := json.NewDecoder(w.Body).Decode(&resp)
				assert.NoError(t, err)
				assert.Equal(t, tt.expectedBody, resp)
			}

			assert.Empty(t, w.Result().Cookies())
		})
	}
}

// ============================================================
// Refresh
// ============================================================

func TestAuthHandler_HandleRefresh(t *testing.T) {
	tests := []struct {
		name           string
		requestBody    interface{}
		setupMocks     func(*testDeps)
		expectedStatus int
		expectedBody   map[string]interface{}
	}{
		{
			name: "Success",
			requestBody: RefreshRequest{
				RefreshToken: testutils.TestRefreshToken,
			},
			setupMocks: func(deps *testDeps) {
				deps.tokenManager.On("ValidateRefreshToken", testutils.TestRefreshToken).
					Return(testutils.TestUserID, nil)
				deps.tokenHasher.On("Hash", testutils.TestRefreshToken).
					Return(testutils.TestHashedRefreshToken, nil)
				deps.tokenRepo.On("Get", mock.Anything, testutils.TestHashedRefreshToken).
					Return(&domain.RefreshTokenModel{
						UserID:      testutils.TestUserID,
						HashedToken: testutils.TestHashedRefreshToken,
						ExpiresAt:   time.Now().Add(24 * time.Hour),
					}, nil)

				deps.userRepo.On("FindRoleByUserID", mock.Anything, testutils.TestUserID).
					Return(testutils.TestRole, nil)

				deps.tokenManager.On("GenerateAccessToken", testutils.TestUserID, testutils.TestRole).
					Return(testutils.TestAccessToken, nil)
				deps.tokenManager.On("GenerateRefreshToken", testutils.TestUserID).
					Return(testutils.TestNewRefreshToken, time.Now().Add(24*time.Hour), nil)
				deps.tokenHasher.On("Hash", testutils.TestNewRefreshToken).
					Return(testutils.TestHashedNewRefreshToken, nil)
				deps.tokenRepo.On("Create", mock.Anything, mock.AnythingOfType("*domain.RefreshTokenModel")).
					Return(nil)
				deps.tokenRepo.On("Revoke", mock.Anything, testutils.TestHashedRefreshToken).
					Return(nil)
			},
			expectedStatus: http.StatusOK,
			expectedBody: map[string]interface{}{
				"accessToken":  testutils.TestAccessToken,
				"refreshToken": testutils.TestNewRefreshToken,
			},
		},
		{
			name:           "Missing refresh token in body",
			requestBody:    RefreshRequest{RefreshToken: ""},
			setupMocks:     func(deps *testDeps) {},
			expectedStatus: http.StatusBadRequest,
			expectedBody:   nil,
		},
		{
			name:           "Invalid JSON body",
			requestBody:    "not json",
			setupMocks:     func(deps *testDeps) {},
			expectedStatus: http.StatusBadRequest,
			expectedBody:   nil,
		},
		{
			name: "Invalid token",
			requestBody: RefreshRequest{
				RefreshToken: testutils.TestRefreshToken,
			},
			setupMocks: func(deps *testDeps) {
				deps.tokenManager.On("ValidateRefreshToken", testutils.TestRefreshToken).
					Return("", security.ErrInvalidToken)
			},
			expectedStatus: http.StatusUnauthorized,
			expectedBody:   nil,
		},
		{
			name: "Expired token",
			requestBody: RefreshRequest{
				RefreshToken: testutils.TestRefreshToken,
			},
			setupMocks: func(deps *testDeps) {
				deps.tokenManager.On("ValidateRefreshToken", testutils.TestRefreshToken).
					Return("", security.ErrTokenExpired)
			},
			expectedStatus: http.StatusUnauthorized,
			expectedBody:   nil,
		},
		{
			name: "Token revoked",
			requestBody: RefreshRequest{
				RefreshToken: testutils.TestRefreshToken,
			},
			setupMocks: func(deps *testDeps) {
				deps.tokenManager.On("ValidateRefreshToken", testutils.TestRefreshToken).
					Return(testutils.TestUserID, nil)
				deps.tokenHasher.On("Hash", testutils.TestRefreshToken).
					Return(testutils.TestHashedRefreshToken, nil)
				revoked := time.Now().Add(-time.Hour)
				deps.tokenRepo.On("Get", mock.Anything, testutils.TestHashedRefreshToken).
					Return(&domain.RefreshTokenModel{
						UserID:      testutils.TestUserID,
						HashedToken: testutils.TestHashedRefreshToken,
						ExpiresAt:   time.Now().Add(time.Hour),
						RevokedAt:   &revoked,
					}, nil)
			},
			expectedStatus: http.StatusForbidden,
			expectedBody:   nil,
		},
		{
			name: "Token not found in storage",
			requestBody: RefreshRequest{
				RefreshToken: testutils.TestRefreshToken,
			},
			setupMocks: func(deps *testDeps) {
				deps.tokenManager.On("ValidateRefreshToken", testutils.TestRefreshToken).Return(testutils.TestUserID, nil)
				deps.tokenHasher.On("Hash", testutils.TestRefreshToken).Return(testutils.TestHashedRefreshToken, nil)
				deps.tokenRepo.On("Get", mock.Anything, testutils.TestHashedRefreshToken).Return(&domain.RefreshTokenModel{}, domain.ErrTokenNotFound)
			},
			expectedStatus: http.StatusForbidden,
			expectedBody:   nil,
		},
		{
			name: "Internal error on token generation",
			requestBody: RefreshRequest{
				RefreshToken: testutils.TestRefreshToken,
			},
			setupMocks: func(deps *testDeps) {
				deps.tokenManager.On("ValidateRefreshToken", testutils.TestRefreshToken).
					Return(testutils.TestUserID, nil)
				deps.tokenHasher.On("Hash", testutils.TestRefreshToken).
					Return(testutils.TestHashedRefreshToken, nil)
				deps.tokenRepo.On("Get", mock.Anything, testutils.TestHashedRefreshToken).
					Return(&domain.RefreshTokenModel{
						UserID:      testutils.TestUserID,
						HashedToken: testutils.TestHashedRefreshToken,
						ExpiresAt:   time.Now().Add(time.Hour),
					}, nil)
				deps.userRepo.On("FindRoleByUserID", mock.Anything, testutils.TestUserID).
					Return(testutils.TestRole, nil)
				deps.tokenManager.On("GenerateAccessToken", testutils.TestUserID, testutils.TestRole).
					Return("", errors.New("jwt broken"))
			},
			expectedStatus: http.StatusInternalServerError,
			expectedBody:   nil,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			deps := setupTest(t)
			tt.setupMocks(deps)

			bodyBytes := marshalBody(t, tt.requestBody)
			req := httptest.NewRequest("POST", "/refresh", bytes.NewReader(bodyBytes))
			req.Header.Set("Content-Type", "application/json")

			w := httptest.NewRecorder()
			deps.handler.HandleRefresh(w, req)

			assert.Equal(t, tt.expectedStatus, w.Code)

			if tt.expectedBody != nil {
				var resp map[string]interface{}
				err := json.NewDecoder(w.Body).Decode(&resp)
				assert.NoError(t, err)
				assert.Equal(t, tt.expectedBody, resp)
			}

			assert.Empty(t, w.Result().Cookies())
		})
	}
}

// ============================================================
// Logout
// ============================================================

func TestAuthHandler_HandleLogout(t *testing.T) {
	tests := []struct {
		name           string
		requestBody    interface{}
		setupMocks     func(*testDeps)
		expectedStatus int
	}{
		{
			name: "Success",
			requestBody: RefreshRequest{
				RefreshToken: testutils.TestRefreshToken,
			},
			setupMocks: func(deps *testDeps) {
				deps.tokenManager.On("ValidateRefreshToken", testutils.TestRefreshToken).
					Return(testutils.TestUserID, nil)
				deps.tokenHasher.On("Hash", testutils.TestRefreshToken).
					Return(testutils.TestHashedRefreshToken, nil)
				deps.tokenRepo.On("Get", mock.Anything, testutils.TestHashedRefreshToken).
					Return(&domain.RefreshTokenModel{
						UserID:      testutils.TestUserID,
						HashedToken: testutils.TestHashedRefreshToken,
						ExpiresAt:   time.Now().Add(time.Hour),
					}, nil)
				deps.tokenRepo.On("Revoke", mock.Anything, testutils.TestHashedRefreshToken).
					Return(nil)
			},
			expectedStatus: http.StatusOK,
		},
		{
			name:           "Missing refresh token in body",
			requestBody:    RefreshRequest{RefreshToken: ""},
			setupMocks:     func(deps *testDeps) {},
			expectedStatus: http.StatusBadRequest,
		},
		{
			name:           "Invalid JSON body",
			requestBody:    "not json",
			setupMocks:     func(deps *testDeps) {},
			expectedStatus: http.StatusBadRequest,
		},
		{
			name: "Token not found -> 200 OK (idempotent)",
			requestBody: RefreshRequest{
				RefreshToken: testutils.TestRefreshToken,
			},
			setupMocks: func(deps *testDeps) {
				deps.tokenManager.On("ValidateRefreshToken", testutils.TestRefreshToken).
					Return(testutils.TestUserID, nil)
				deps.tokenHasher.On("Hash", testutils.TestRefreshToken).
					Return(testutils.TestHashedRefreshToken, nil)
				deps.tokenRepo.On("Get", mock.Anything, testutils.TestHashedRefreshToken).
					Return(&domain.RefreshTokenModel{
						UserID:      testutils.TestUserID,
						HashedToken: testutils.TestHashedRefreshToken,
						ExpiresAt:   time.Now().Add(time.Hour),
					}, nil)
				deps.tokenRepo.On("Revoke", mock.Anything, testutils.TestHashedRefreshToken).
					Return(domain.ErrTokenNotFound)
			},
			expectedStatus: http.StatusOK,
		},
		{
			name: "Invalid token",
			requestBody: RefreshRequest{
				RefreshToken: testutils.TestRefreshToken,
			},
			setupMocks: func(deps *testDeps) {
				deps.tokenManager.On("ValidateRefreshToken", testutils.TestRefreshToken).
					Return("", security.ErrInvalidToken)
			},
			expectedStatus: http.StatusUnauthorized,
		},
		{
			name: "Revoke internal error",
			requestBody: RefreshRequest{
				RefreshToken: testutils.TestRefreshToken,
			},
			setupMocks: func(deps *testDeps) {
				deps.tokenManager.On("ValidateRefreshToken", testutils.TestRefreshToken).
					Return(testutils.TestUserID, nil)
				deps.tokenHasher.On("Hash", testutils.TestRefreshToken).
					Return(testutils.TestHashedRefreshToken, nil)
				deps.tokenRepo.On("Get", mock.Anything, testutils.TestHashedRefreshToken).
					Return(&domain.RefreshTokenModel{
						UserID:      testutils.TestUserID,
						HashedToken: testutils.TestHashedRefreshToken,
						ExpiresAt:   time.Now().Add(time.Hour),
					}, nil)
				deps.tokenRepo.On("Revoke", mock.Anything, testutils.TestHashedRefreshToken).
					Return(errors.New("storage exploded"))
			},
			expectedStatus: http.StatusInternalServerError,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			deps := setupTest(t)
			tt.setupMocks(deps)

			bodyBytes := marshalBody(t, tt.requestBody)
			req := httptest.NewRequest("POST", "/logout", bytes.NewReader(bodyBytes))
			req.Header.Set("Content-Type", "application/json")

			w := httptest.NewRecorder()
			deps.handler.HandleLogout(w, req)

			assert.Equal(t, tt.expectedStatus, w.Code)
			// cookie больше не ставим, в том числе не чистим
			assert.Empty(t, w.Result().Cookies())
		})
	}
}

// ============================================================
// LogoutAll
// ============================================================

func TestAuthHandler_HandleLogoutAll(t *testing.T) {
	tests := []struct {
		name           string
		requestBody    interface{}
		setupMocks     func(*testDeps)
		expectedStatus int
	}{
		{
			name: "Success",
			requestBody: RefreshRequest{
				RefreshToken: testutils.TestRefreshToken,
			},
			setupMocks: func(deps *testDeps) {
				deps.tokenManager.On("ValidateRefreshToken", testutils.TestRefreshToken).
					Return(testutils.TestUserID, nil)
				deps.tokenHasher.On("Hash", testutils.TestRefreshToken).
					Return(testutils.TestHashedRefreshToken, nil)
				deps.tokenRepo.On("Get", mock.Anything, testutils.TestHashedRefreshToken).
					Return(&domain.RefreshTokenModel{
						UserID:      testutils.TestUserID,
						HashedToken: testutils.TestHashedRefreshToken,
						ExpiresAt:   time.Now().Add(time.Hour),
					}, nil)
				deps.tokenRepo.On("RevokeAll", mock.Anything, testutils.TestUserID).
					Return(nil)
			},
			expectedStatus: http.StatusOK,
		},
		{
			name:           "Missing refresh token in body",
			requestBody:    RefreshRequest{RefreshToken: ""},
			setupMocks:     func(deps *testDeps) {},
			expectedStatus: http.StatusBadRequest,
		},
		{
			name:           "Invalid JSON body",
			requestBody:    "not json",
			setupMocks:     func(deps *testDeps) {},
			expectedStatus: http.StatusBadRequest,
		},
		{
			name: "Invalid token",
			requestBody: RefreshRequest{
				RefreshToken: testutils.TestRefreshToken,
			},
			setupMocks: func(deps *testDeps) {
				deps.tokenManager.On("ValidateRefreshToken", testutils.TestRefreshToken).
					Return("", security.ErrInvalidToken)
			},
			expectedStatus: http.StatusUnauthorized,
		},
		{
			name: "Revoked token -> 403",
			requestBody: RefreshRequest{
				RefreshToken: testutils.TestRefreshToken,
			},
			setupMocks: func(deps *testDeps) {
				deps.tokenManager.On("ValidateRefreshToken", testutils.TestRefreshToken).
					Return(testutils.TestUserID, nil)
				deps.tokenHasher.On("Hash", testutils.TestRefreshToken).
					Return(testutils.TestHashedRefreshToken, nil)
				revoked := time.Now().Add(-time.Minute)
				deps.tokenRepo.On("Get", mock.Anything, testutils.TestHashedRefreshToken).
					Return(&domain.RefreshTokenModel{
						UserID:      testutils.TestUserID,
						HashedToken: testutils.TestHashedRefreshToken,
						ExpiresAt:   time.Now().Add(time.Hour),
						RevokedAt:   &revoked,
					}, nil)
			},
			expectedStatus: http.StatusForbidden,
		},
		{
			name: "RevokeAll internal error",
			requestBody: RefreshRequest{
				RefreshToken: testutils.TestRefreshToken,
			},
			setupMocks: func(deps *testDeps) {
				deps.tokenManager.On("ValidateRefreshToken", testutils.TestRefreshToken).
					Return(testutils.TestUserID, nil)
				deps.tokenHasher.On("Hash", testutils.TestRefreshToken).
					Return(testutils.TestHashedRefreshToken, nil)
				deps.tokenRepo.On("Get", mock.Anything, testutils.TestHashedRefreshToken).
					Return(&domain.RefreshTokenModel{
						UserID:      testutils.TestUserID,
						HashedToken: testutils.TestHashedRefreshToken,
						ExpiresAt:   time.Now().Add(time.Hour),
					}, nil)
				deps.tokenRepo.On("RevokeAll", mock.Anything, testutils.TestUserID).
					Return(errors.New("storage exploded"))
			},
			expectedStatus: http.StatusInternalServerError,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			deps := setupTest(t)
			tt.setupMocks(deps)

			bodyBytes := marshalBody(t, tt.requestBody)
			req := httptest.NewRequest("POST", "/logout/all", bytes.NewReader(bodyBytes))
			req.Header.Set("Content-Type", "application/json")

			w := httptest.NewRecorder()
			deps.handler.HandleLogoutAll(w, req)

			assert.Equal(t, tt.expectedStatus, w.Code)
			assert.Empty(t, w.Result().Cookies())
		})
	}
}
