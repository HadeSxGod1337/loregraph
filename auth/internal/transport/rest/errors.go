package rest

import (
	"errors"
	"loregraph_auth/internal/app/security"
	"loregraph_auth/internal/domain"
	"net/http"
)

func HTTPStatusFromError(err error) int {
	switch {
	case errors.Is(err, domain.ErrUserInvalidCredentials),
		errors.Is(err, security.ErrInvalidToken),
		errors.Is(err, security.ErrTokenExpired):
		return http.StatusUnauthorized
	case errors.Is(err, domain.ErrTokenRevoked),
		errors.Is(err, security.ErrUserIDNotMatch),
		errors.Is(err, domain.ErrTokenNotFound),
		errors.Is(err, domain.ErrUserLimitReached):
		return http.StatusForbidden
	default:
		return http.StatusInternalServerError
	}
}
