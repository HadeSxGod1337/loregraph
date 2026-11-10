package main

import (
	"context"
	"errors"
	"fmt"
	"log"
	"log/slog"
	"loregraph_auth/internal/app"
	"loregraph_auth/internal/app/security"
	"loregraph_auth/internal/config"
	myLogger "loregraph_auth/internal/logger"
	"loregraph_auth/internal/repo"
	"loregraph_auth/internal/transport/rest"
	"net/http"
	"os"
	"os/signal"
	"syscall"
	"time"

	"github.com/gorilla/mux"
)

func main() {
	ctx := context.Background()

	cfg, err := config.Load()
	if err != nil {
		log.Fatalf("failed to load config: %v", err)
	}
	if err := runAuth(ctx, cfg); err != nil {
		log.Fatalf("application error: %v", err)
	}
}

func runAuth(ctx context.Context, cfg *config.Config) error {
	logger := myLogger.New(cfg.Logger, "auth")

	userRepo := repo.NewUserRepo(cfg.Auth.UserRepo)
	refreshRepo := repo.NewRefreshTokenRepo(cfg.Auth.RefreshTokenRepo)
	tokenManager := security.NewJWTManager(cfg.Auth.JWT)
	passwordHasher := security.NewArgon2Hasher(cfg.Auth.Argon2)
	tokenHasher := security.NewTokenHasher(cfg.Auth.SHA256)

	authService := app.NewAuthService(
		userRepo,
		refreshRepo,
		cfg.Auth.UserRepo.MaxUsers,
		passwordHasher,
		tokenHasher,
		tokenManager,
		logger,
	)

	authHandler := rest.NewAuthHandler(authService, cfg.Auth.Handler.RefreshTTLDays, cfg.Auth.Handler.TimeContextInSecond, logger)
	publicKeyHandler := rest.NewPublicKeyHandler(cfg.Auth.JWT.PublicKey)
	userAdminHandler := rest.NewUserAdminHandler(authService, logger)

	router := setupRouter(authHandler, publicKeyHandler, userAdminHandler, logger)

	srv := &http.Server{
		Addr:         ":" + cfg.Auth.Server.Port,
		Handler:      router,
		ReadTimeout:  15 * time.Second,
		WriteTimeout: 15 * time.Second,
		IdleTimeout:  60 * time.Second,
	}

	go func() {
		logger.Info("server started", "port", cfg.Auth.Server.Port)
		if err := srv.ListenAndServe(); err != nil && !errors.Is(err, http.ErrServerClosed) {
			logger.Error("server error", "error", err)
		}
	}()

	quit := make(chan os.Signal, 1)
	signal.Notify(quit, syscall.SIGINT, syscall.SIGTERM)
	<-quit

	logger.Info("shutting down...")

	ctxShutdown, cancel := context.WithTimeout(context.Background(), 30*time.Second)
	defer cancel()

	if err := srv.Shutdown(ctxShutdown); err != nil {
		return fmt.Errorf("shutdown error: %w", err)
	}

	logger.Info("server stopped")
	return nil
}

func setupRouter(
	handler *rest.AuthHandler,
	publicKeyHandler *rest.PublicKeyHandler,
	userAdminHandler *rest.UserAdminHandler,
	logger *slog.Logger,
) http.Handler {
	r := mux.NewRouter()

	r.Path("/login").Methods("POST").HandlerFunc(handler.HandleLogin)
	r.Path("/register").Methods("POST").HandlerFunc(handler.HandleRegister)
	r.Path("/refresh").Methods("POST").HandlerFunc(handler.HandleRefresh)
	r.Path("/logout").Methods("POST").HandlerFunc(handler.HandleLogout)
	r.Path("/logout/all").Methods("POST").HandlerFunc(handler.HandleLogoutAll)

	// Read by the Loregraph backend at startup. Verifiable-only material —
	// see PublicKeyHandler.
	r.Path("/public-key").Methods("GET").HandlerFunc(publicKeyHandler.Handle)

	// Owner-only user administration. Both handlers check the access token
	// themselves: the router has no notion of roles, and the bearer token
	// is the only credential these endpoints accept (no cookies, no query
	// strings — a role change must not be triggerable by a link).
	r.Path("/users").Methods("GET").HandlerFunc(userAdminHandler.HandleListUsers)
	r.Path("/users/{id}/role").Methods("PUT").HandlerFunc(userAdminHandler.HandleChangeRole)
	r.Path("/users/{id}").Methods("DELETE").HandlerFunc(userAdminHandler.HandleDeleteUser)

	allowedOrigins := []string{
		"http://localhost:5173",
		"http://127.0.0.1:5173",
		"http://localhost:8000",
		"http://127.0.0.1:8000",
		"http://192.168.0.21:8000",
	}
	// Wrap the router itself rather than using r.Use(): gorilla/mux only runs
	// Use() middleware for requests that match a registered route, and an
	// OPTIONS preflight does not match a POST-only route. Wrapping the whole
	// router guarantees the CORS headers are written before the router can
	// answer 405 to the preflight.
	return rest.CORS(allowedOrigins)(rest.LoggingMiddleware(logger)(r))
}
