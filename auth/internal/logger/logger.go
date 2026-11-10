package logger

import (
	"log/slog"
	"loregraph_auth/internal/config"
	"os"
)

type Logger struct {
	Level  string // debug, info, warn, error
	Format string // text/json
}

func New(cfg config.LoggerConfig, serviceName string) *slog.Logger {
	var level slog.Level
	switch cfg.Level {
	case "debug":
		level = slog.LevelDebug
	case "warn":
		level = slog.LevelWarn
	case "error":
		level = slog.LevelError
	default:
		level = slog.LevelInfo
	}

	handlerOpts := &slog.HandlerOptions{Level: level}
	var handler slog.Handler
	if cfg.Format == "json" {
		handler = slog.NewJSONHandler(os.Stdout, handlerOpts)
	} else {
		handler = slog.NewTextHandler(os.Stdout, handlerOpts)
	}

	handler = handler.WithAttrs([]slog.Attr{slog.String("service", serviceName)})
	return slog.New(handler)
}
