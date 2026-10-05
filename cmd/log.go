package main

import (
	"go.uber.org/zap"

	"devrag/internal/common"
	"devrag/internal/server"
)

func newLogger(cfg server.Config) (*zap.Logger, func(), error) {
	return common.NewLogger(cfg.Log)
}
