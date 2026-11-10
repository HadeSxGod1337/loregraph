package rest

import (
	"encoding/json"
	"errors"
	"log/slog"
	"net/http"
	"strings"
	"time"

	"loregraph_auth/internal/app"
	"loregraph_auth/internal/domain"

	"github.com/gorilla/mux"
)

// UserAdminHandler serves the owner-only user management endpoints.
//
// Kept separate from AuthHandler because they answer different questions:
// AuthHandler is "who are you" (login, register, refresh, logout), this one
// is "who else is here and what may they do". Mixing them would put an
// owner-only route next to a public one, and the next person adding a
// handler would have to read carefully to tell which is which.
type UserAdminHandler struct {
	authService *app.AuthService
	logger      *slog.Logger
}

func NewUserAdminHandler(authService *app.AuthService, logger *slog.Logger) *UserAdminHandler {
	return &UserAdminHandler{
		authService: authService,
		logger:      logger,
	}
}

// UserSummary is a User stripped of everything the owner does not need to
// see. HashedPassword in particular must never leave the process — a leaked
// Argon2 hash plus a weak password is a wider blast radius than the account
// itself. Defined as its own type rather than `json:"-"` on domain.User so
// accidental future fields are opt-in, not opt-out.
type UserSummary struct {
	ID        string    `json:"id"`
	Email     string    `json:"email"`
	Role      string    `json:"role"`
	CreatedAt time.Time `json:"createdAt"`
}

func toSummary(u *domain.User) UserSummary {
	return UserSummary{
		ID:        u.ID,
		Email:     u.Email,
		Role:      u.Role,
		CreatedAt: u.CreatedAt,
	}
}

type ChangeRoleRequest struct {
	Role string `json:"role"`
}

/*
pattern: /users
method: GET
headers: Authorization: Bearer <accessToken>
info: Returns every account, oldest first. Owner-only.

succeed:
  - status code: 200 OK
  - response body (JSON): {"users":[{"id":...,"email":...,"role":...,"createdAt":...}, ...]}

errors:
  - 401 Unauthorized: нет токена, истёк или подделан
  - 403 Forbidden:    токен валиден, но роль не owner
  - 500 Internal Server Error
*/

func (h *UserAdminHandler) HandleListUsers(w http.ResponseWriter, r *http.Request) {
	actorID, ok := h.requireAccessToken(w, r)
	if !ok {
		return
	}

	users, err := h.authService.ListUsers(r.Context(), actorID)
	if err != nil {
		h.writeServiceError(w, r, err)
		return
	}

	summaries := make([]UserSummary, 0, len(users))
	for _, u := range users {
		summaries = append(summaries, toSummary(u))
	}

	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(http.StatusOK)
	if err := json.NewEncoder(w).Encode(map[string]any{"users": summaries}); err != nil {
		h.logger.ErrorContext(r.Context(), "Failed to encode users response", "error", err)
	}
}

/*
pattern: /users/{id}/role
method: PUT
headers: Authorization: Bearer <accessToken>
info: Changes a user's role. Owner-only, and never on one's own account.

Request body (JSON):

	{
	  "role": "user" | "master" | "owner"
	}

succeed:
  - status code: 200 OK

errors:
  - 400 Bad Request: тело невалидно или роль неизвестна
  - 401 Unauthorized: нет токена, истёк или подделан
  - 403 Forbidden:    вызывающий не owner, либо пытается изменить себя
  - 404 Not Found:    пользователь с таким id не найден
  - 500 Internal Server Error
*/

func (h *UserAdminHandler) HandleChangeRole(w http.ResponseWriter, r *http.Request) {
	actorID, ok := h.requireAccessToken(w, r)
	if !ok {
		return
	}

	targetID := mux.Vars(r)["id"]
	if targetID == "" {
		http.Error(w, "Missing user id", http.StatusBadRequest)
		return
	}

	r.Body = http.MaxBytesReader(w, r.Body, maxBufSize)
	var req ChangeRoleRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		http.Error(w, "Invalid request body", http.StatusBadRequest)
		return
	}
	if req.Role == "" {
		http.Error(w, "Role is required", http.StatusBadRequest)
		return
	}

	if err := h.authService.ChangeRole(r.Context(), actorID, targetID, req.Role); err != nil {
		h.writeServiceError(w, r, err)
		return
	}

	w.WriteHeader(http.StatusOK)
}

/*
pattern: /users/{id}
method: DELETE
headers: Authorization: Bearer <accessToken>
info: Removes an account. Owner-only, and never the caller's own account.

succeed:
  - status code: 200 OK

errors:
  - 401 Unauthorized: нет токена, истёк или подделан
  - 403 Forbidden:    вызывающий не owner, либо пытается удалить себя
  - 404 Not Found:    пользователь с таким id не найден
  - 500 Internal Server Error
*/

func (h *UserAdminHandler) HandleDeleteUser(w http.ResponseWriter, r *http.Request) {
	actorID, ok := h.requireAccessToken(w, r)
	if !ok {
		return
	}

	targetID := mux.Vars(r)["id"]
	if targetID == "" {
		http.Error(w, "Missing user id", http.StatusBadRequest)
		return
	}

	if err := h.authService.DeleteUser(r.Context(), actorID, targetID); err != nil {
		h.writeServiceError(w, r, err)
		return
	}

	w.WriteHeader(http.StatusOK)
}

// requireAccessToken extracts the bearer token, validates it, and returns
// the caller's user id. On any failure it writes the response itself
// (401) and returns ok=false, so the caller can just `return` — the same
// pattern requireMaster uses on the Python side.
func (h *UserAdminHandler) requireAccessToken(w http.ResponseWriter, r *http.Request) (string, bool) {
	header := r.Header.Get("Authorization")
	const prefix = "Bearer "
	if !strings.HasPrefix(header, prefix) {
		http.Error(w, "Missing or malformed Authorization header", http.StatusUnauthorized)
		return "", false
	}
	token := strings.TrimSpace(strings.TrimPrefix(header, prefix))
	if token == "" {
		http.Error(w, "Empty access token", http.StatusUnauthorized)
		return "", false
	}

	userID, err := h.authService.ValidateToken(r.Context(), token)
	if err != nil {
		// Deliberately not distinguishing expired from invalid from "user
		// no longer exists": all three mean "log in again", and telling the
		// caller which one invites enumeration of valid accounts.
		http.Error(w, "Invalid access token", http.StatusUnauthorized)
		return "", false
	}
	return userID, true
}

// writeServiceError maps service-level errors to HTTP. Kept here, next to
// the handlers that produce them, rather than expanding the shared
// HTTPStatusFromError — the shared mapper deals with the login/register
// surface, and its cases (already-exists, limit-reached) do not apply to
// admin actions.
func (h *UserAdminHandler) writeServiceError(w http.ResponseWriter, r *http.Request, err error) {
	switch {
	case errors.Is(err, domain.ErrForbidden):
		http.Error(w, "Forbidden", http.StatusForbidden)
	case errors.Is(err, domain.ErrCannotChangeOwnRole):
		http.Error(w, "Cannot change own role", http.StatusForbidden)
	case errors.Is(err, domain.ErrInvalidRole):
		http.Error(w, "Unknown role", http.StatusBadRequest)
	case errors.Is(err, domain.ErrUserNotFound):
		http.Error(w, "User not found", http.StatusNotFound)
	default:
		h.logger.ErrorContext(r.Context(), "Unhandled admin error", "error", err)
		http.Error(w, "Internal server error", http.StatusInternalServerError)
	}
}
