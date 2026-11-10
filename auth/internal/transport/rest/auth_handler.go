package rest

import (
	"context"
	"encoding/json"
	"errors"
	"log/slog"
	"loregraph_auth/internal/app"
	"loregraph_auth/internal/domain"
	"net/http"
	"time"
)

type AuthHandler struct {
	authService *app.AuthService
	logger      *slog.Logger
	timeContext int

	refreshTTLDays int
}

const maxBufSize int64 = 1 << 20

func NewAuthHandler(authService *app.AuthService,
	refreshTTLDays int,
	timeContext int,
	logger *slog.Logger,
) *AuthHandler {
	return &AuthHandler{
		authService:    authService,
		logger:         logger,
		timeContext:    timeContext,
		refreshTTLDays: refreshTTLDays,
	}
}

/*
pattern: /login
method: POST
info: JSON in HTTP request body. Authenticates a user and returns access/refresh tokens.

Request body (JSON):
{
  "email":    "user@example.com",  // или "username", обязательное поле
  "password": "secret"
}

succeed:
 - status code: 200 OK
 - response body (JSON):
{
  "accessToken":  "accessToken",
  "user": {
    "email": "user@example.com"
  }
}

httpOnly cookie:
  "refreshToken": "refreshToken",

errors:
 - 400 Bad Request: тело запроса отсутствует или невалидный JSON / поля не соответствуют схеме
 - 401 Unauthorized: неверный email или пароль (аутентификация провалена)
 - 500 Internal Server Error: внутренняя ошибка сервера (БД, генерация токенов и т.п.)
*/

func (h *AuthHandler) HandleLogin(w http.ResponseWriter, r *http.Request) {
	r.Body = http.MaxBytesReader(w, r.Body, maxBufSize)

	var req LoginRequest

	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		http.Error(w, "Invalid request body", http.StatusBadRequest)
		return
	}

	if req.Email == "" || req.Password == "" {
		http.Error(w, "Email and password are required", http.StatusBadRequest)
		return
	}

	ctx, cancel := context.WithTimeout(r.Context(), time.Duration(h.timeContext)*time.Second)
	defer cancel()

	accessToken, refreshToken, userID, err := h.authService.Login(ctx, req.Email, req.Password)
	if err != nil {
		status := HTTPStatusFromError(err)
		http.Error(w, http.StatusText(status), status)
		return
	}

	resp := LoginResponse{
		AccessToken:  accessToken,
		RefreshToken: refreshToken,
		User: UserResponse{
			Email:  req.Email,
			UserID: userID,
		},
	}

	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(http.StatusOK)

	if err := json.NewEncoder(w).Encode(resp); err != nil {
		h.logger.ErrorContext(ctx, "Failed to encode response", "error", err)
	}

	h.logger.InfoContext(ctx, "User logged is successfully", "email", req.Email)
}

/*
pattern: /register
method: POST
info: JSON in HTTP request body. Register a user and returns access/refresh tokens.

Request body (JSON):
{
  "email":    "user@example.com",
  "password": "secret",
  "name": "username"
}

succeed:
 - status code: 201 Created
 - response body (JSON):
{
  "accessToken":  "accessToken",
  "user": {
    "email": "user@example.com",
    "name":  "username"
  }
}

httpOnly cookie:
  "refreshToken": "refreshToken",

errors:
 - 400 Bad Request: тело запроса отсутствует или невалидный JSON / поля не соответствуют схеме
 - 409 Conflict: юзер уже существует
 - 500 Internal Server Error: внутренняя ошибка сервера (БД, генерация токенов и т.п.)
*/

func (h *AuthHandler) HandleRegister(w http.ResponseWriter, r *http.Request) {
	r.Body = http.MaxBytesReader(w, r.Body, maxBufSize)

	var req RegisterRequest

	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		http.Error(w, "Invalid request body", http.StatusBadRequest)
		return
	}

	if req.Email == "" || req.Password == "" {
		http.Error(w, "Email and password are required", http.StatusBadRequest)
		return
	}

	ctx, cancel := context.WithTimeout(r.Context(), time.Duration(h.timeContext)*time.Second)
	defer cancel()

	accessToken, refreshToken, userID, err := h.authService.Register(ctx, req.Email, req.Password)
	if err != nil {
		if errors.Is(err, domain.ErrUserAlreadyExists) {
			http.Error(w, "User already exists", http.StatusConflict)
			return
		}
		status := HTTPStatusFromError(err)
		http.Error(w, http.StatusText(status), status)
		return
	}

	resp := RegisterResponse{
		AccessToken:  accessToken,
		RefreshToken: refreshToken,
		User: UserResponse{
			Email:  req.Email,
			UserID: userID,
		},
	}

	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(http.StatusCreated)

	if err = json.NewEncoder(w).Encode(resp); err != nil {
		h.logger.ErrorContext(ctx, "Failed to encode response", "error", err)
	}

	h.logger.InfoContext(ctx, "User register is successfully", "email", req.Email)
}

/*
pattern: /refresh
method: POST
httpOnly cookie:
		Value:    refreshToken,
		Path:     "/api/refresh"
succeed:
 - status code: 200 OK


httpOnly cookie:
		Value:    refreshToken,
		Path:     "/api/refresh"

errors:
 - 401 Unauthorized: токена нет, истек или подделан
 - 403 Forbidden: уже использован
 - 500 Internal Server Error: внутренняя ошибка сервера (БД, генерация токенов и т.п.)
*/

func (h *AuthHandler) HandleRefresh(w http.ResponseWriter, r *http.Request) {
	r.Body = http.MaxBytesReader(w, r.Body, maxBufSize)

	var req RefreshRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		http.Error(w, "Invalid request body", http.StatusBadRequest)
		return
	}
	if req.RefreshToken == "" {
		http.Error(w, "Refresh token is required", http.StatusBadRequest)
		return
	}

	ctx, cancel := context.WithTimeout(r.Context(), time.Duration(h.timeContext)*time.Second)
	defer cancel()

	newAccessToken, newRefreshToken, err := h.authService.Refresh(ctx, req.RefreshToken)
	if err != nil {
		status := HTTPStatusFromError(err)
		http.Error(w, http.StatusText(status), status)
		return
	}

	resp := struct {
		AccessToken  string `json:"accessToken"`
		RefreshToken string `json:"refreshToken"`
	}{
		AccessToken:  newAccessToken,
		RefreshToken: newRefreshToken,
	}

	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(http.StatusOK)
	if err := json.NewEncoder(w).Encode(resp); err != nil {
		h.logger.ErrorContext(ctx, "Failed to encode refresh response", "error", err)
	}
	h.logger.InfoContext(ctx, "User refreshed successfully")
}

/*
pattern: /logout
method: POST
httpOnly cookie:
  Path:     "/api/refresh",

succeed:
 - status code: 200 OK

errors:
 - 500 Internal Server Error: внутренняя ошибка сервера (БД, генерация токенов и т.п.)

info: Инвалидирует refreshToken. Если токен отсутствует или уже невалиден — возвращает 200 OK (идемпотентность).
*/

func (h *AuthHandler) HandleLogout(w http.ResponseWriter, r *http.Request) {
	h.handleLogout(w, r, h.authService.Logout)
}

/*
pattern: /logout/all
method: POST
httpOnly cookie:
  Path:     "/api/refresh",

succeed:
 - status code: 200 OK

errors:
 - 401 Unauthorized: токена нет, истек или подделан
 - 403 Forbidden: уже использован
 - 500 Internal Server Error: внутренняя ошибка сервера (БД, генерация токенов и т.п.)
*/

func (h *AuthHandler) HandleLogoutAll(w http.ResponseWriter, r *http.Request) {
	h.handleLogout(w, r, h.authService.LogoutAll)
}

func (h *AuthHandler) handleLogout(w http.ResponseWriter, r *http.Request, logoutFn func(context.Context, string) error) {
	r.Body = http.MaxBytesReader(w, r.Body, maxBufSize)

	var req RefreshRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		http.Error(w, "Invalid request body", http.StatusBadRequest)
		return
	}

	if req.RefreshToken == "" {
		http.Error(w, "Refresh token is required", http.StatusBadRequest)
		return
	}

	ctx, cancel := context.WithTimeout(r.Context(), time.Duration(h.timeContext)*time.Second)
	defer cancel()

	if err := logoutFn(ctx, req.RefreshToken); err != nil {
		if errors.Is(err, domain.ErrTokenNotFound) {
			h.logger.WarnContext(ctx, "User already logged out")
			w.WriteHeader(http.StatusOK)
			return
		}

		status := HTTPStatusFromError(err)
		http.Error(w, http.StatusText(status), status)
		return
	}

	w.WriteHeader(http.StatusOK)
	h.logger.InfoContext(ctx, "User logged out successfully")
}
