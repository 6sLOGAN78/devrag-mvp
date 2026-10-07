// Command ragflow_server is the Go engine entry point (docs/03-backend/entry-points.md).
package main

import (
	"context"
	"errors"
	"fmt"
	"net/http"
	"os"
	"os/signal"
	"syscall"
	"time"

	"go.uber.org/zap"

	"devrag/internal/dao"
	"devrag/internal/handler"
	"devrag/internal/router"
	"devrag/internal/server"
	"devrag/internal/service"
)

const (
	defaultConfPath   = "conf/service_conf.yaml"
	startupTimeout    = 5 * time.Second
	shutdownTimeout   = 10 * time.Second
	readHeaderTimeout = 5 * time.Second
)

func main() {
	os.Exit(execute(os.Args[1:], runAPI, os.Stderr))
}

func confPath() string {
	if p := os.Getenv("SERVICE_CONF"); p != "" {
		return p
	}
	return defaultConfPath
}

// runAPI serves the Go API until SIGINT or SIGTERM, then shuts down gracefully.
func runAPI() error {
	cfg, err := server.LoadConfig(confPath())
	if err != nil {
		return err
	}
	logger, closeLog, err := newLogger(cfg)
	if err != nil {
		return err
	}
	defer closeLog()

	startCtx, cancel := context.WithTimeout(context.Background(), startupTimeout)
	db, err := dao.OpenDB(startCtx, cfg.MySQL)
	cancel()
	if err != nil {
		return fmt.Errorf("database: %w", err)
	}
	defer func() { _ = db.Close() }()
	rd := dao.OpenRedis(cfg.Redis)
	defer func() { _ = rd.Close() }()

	svc := service.NewSystem(db, rd, db).WithRegisterEnabled(cfg.Auth.RegisterEnabled)
	accounts := service.NewAccount(db, service.NewLimiter(rd, "rl"), cfg)
	auth := service.NewAuth(db, cfg.Security.SecretKey, cfg.Security.TokenMaxAge).WithTokens(db)
	limiter := service.NewLimiter(rd, "rl")
	mailQueue, closeMail, err := newMailQueue(cfg, logger)
	if err != nil {
		return err
	}
	defer closeMail()
	reset := service.NewPasswordReset(db, limiter, service.NewOTP(rd, "auth", cfg.Security.SecretKey, cfg.Auth.OTPTTL), mailQueue, cfg)
	engine := router.NewEngine(cfg, logger, handler.NewSystem(svc),
		router.WithAuth(auth),
		router.WithAccount(handler.NewAccount(accounts, cfg.Security.TokenMaxAge)),
		router.WithSession(handler.NewUser(auth)),
		router.WithPasswordReset(handler.NewPasswordReset(reset)),
		router.WithTokens(handler.NewToken(service.NewToken(db, service.NewLimiter(rd, "rl"), service.DefaultTokenLimits()))),
		router.WithProfile(
			handler.NewSettings(service.NewUser(db, service.NewLimiter(rd, "rl"), cfg)),
			handler.NewTenant(service.NewTenant(db))))
	srv := &http.Server{Addr: cfg.Addr(), Handler: engine, ReadHeaderTimeout: readHeaderTimeout}

	ctx, stop := signal.NotifyContext(context.Background(), syscall.SIGINT, syscall.SIGTERM)
	defer stop()
	errCh := make(chan error, 1)
	go func() { errCh <- srv.ListenAndServe() }()
	logger.Info("go api listening", zap.String("addr", cfg.Addr()))

	select {
	case err := <-errCh:
		return err
	case <-ctx.Done():
	}
	logger.Info("shutting down")
	shutCtx, cancelShut := context.WithTimeout(context.Background(), shutdownTimeout)
	defer cancelShut()
	if err := srv.Shutdown(shutCtx); err != nil && !errors.Is(err, http.ErrServerClosed) {
		return err
	}
	return nil
}
