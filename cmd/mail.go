package main

import (
	"runtime"

	"go.uber.org/zap"

	"devrag/internal/server"
	"devrag/internal/service"
)

const mailQueueSize = 64

// newMailQueue builds the asynchronous SMTP sender for reset codes. Without a configured host the
// server still starts, warns once, and no mail is delivered. A misconfigured relay (for example
// credentials over a plaintext connection) stops start-up.
func newMailQueue(cfg server.Config, logger *zap.Logger) (service.MailQueue, func(), error) {
	if cfg.Mail.Host == "" {
		logger.Warn("smtp host is not configured: password reset codes cannot be delivered")
		return service.DiscardMail{}, func() {}, nil
	}
	mailer, err := service.NewSMTPMailer(cfg.Mail)
	if err != nil {
		return nil, nil, err
	}
	pool := service.NewMailPool(mailer, max(2, runtime.NumCPU()), mailQueueSize, logger)
	return pool, pool.Close, nil
}
