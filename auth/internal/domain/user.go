package domain

import (
	"context"
	"errors"
	"net/mail"
	"strings"
	"time"
	"unicode/utf8"
	"uuid"
)

// Roles. Three, not two: master runs the game, owner runs the service.
// A master can edit lore, launch the agent and invite players; only an owner
// can change anyone's role. A deployment with a single human wears both hats.
//
// Kept as constants instead of raw strings so a future grep for
// `RoleOwner` finds every place the concept appears — the previous use of
// bare "master" strings across the codebase made it easy to miss a check.
const (
	RoleUser   = "user"
	RoleMaster = "master"
	RoleOwner  = "owner"
)

type User struct {
	ID             string
	Email          string
	HashedPassword string
	Role           string
	CreatedAt      time.Time
}

func NewUser(email, hashedPassword string) *User {
	user := &User{
		ID:             uuid.New().String(),
		Email:          email,
		HashedPassword: hashedPassword,
		Role:           RoleUser,
		CreatedAt:      time.Now(),
	}
	return user
}

type UserRepo interface {
	Create(ctx context.Context, user *User) (err error)
	FindByEmail(ctx context.Context, email string) (user *User, err error)
	FindByID(ctx context.Context, id string) (user *User, err error)
	// ListAll returns every user, in a stable order (by CreatedAt, oldest
	// first) so the admin list does not shuffle between refreshes.
	ListAll(ctx context.Context) ([]*User, error)
	FindRoleByUserID(ctx context.Context, userID string) (role string, err error)
	Update(ctx context.Context, user *User) (err error)
	CreateRoleByID(ctx context.Context, userID, role string) error
	// DeleteByID removes the user and returns the row that was removed, so
	// the caller can log who was deleted without a second lookup.
	DeleteByID(ctx context.Context, id string) (*User, error)
	Count(ctx context.Context) (int, error)
}

var (
	ErrUserNotFound           = errors.New("user not found")
	ErrUserInvalidCredentials = errors.New("invalid credentials")
	ErrUserAlreadyExists      = errors.New("user already exists")
	ErrUserLimitReached       = errors.New("user limit reached")
	// ErrForbidden is "authenticated but not allowed": distinct from
	// ErrUserInvalidCredentials, which is "not authenticated at all".
	ErrForbidden = errors.New("forbidden")
	// ErrInvalidRole rejects a role outside the known set. Rejecting
	// unknown roles (rather than storing them verbatim) keeps the role
	// column from accumulating typos that silently disable access checks.
	ErrInvalidRole = errors.New("invalid role")
	// ErrCannotChangeOwnRole : an owner editing their own role could demote
	// themselves past the point of undoing it through the UI, and there is
	// no guarantee another owner exists. Forbidden unconditionally.
	ErrCannotChangeOwnRole = errors.New("cannot change own role")
)

// IsValidRole guards the role enum at every boundary that accepts a role
// from outside (currently only the admin role-change endpoint).
func IsValidRole(role string) bool {
	switch role {
	case RoleUser, RoleMaster, RoleOwner:
		return true
	default:
		return false
	}
}

func IsValidEmail(email string) bool {
	_, err := mail.ParseAddress(email)
	return err == nil
}

func IsValidPassword(password string) bool {
	password = strings.TrimSpace(password)
	count := utf8.RuneCountInString(password)
	return count >= 8 && count <= 32
}
