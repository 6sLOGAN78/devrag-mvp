package common

import (
	"os"
	"path/filepath"
	"go.uber.org/zap"
	"go.uber.org/zap/zapcore"
	"gopkg.in/natefinch/lumberjack.v2"
)

var Logger *zap.Logger

func InitLogger() {
	// 1. File Rotation Config
	// Creates a logs directory dynamically in root
	logDir := "logs"
	os.MkdirAll(logDir, os.ModePerm)

	lumberjackLogger := &lumberjack.Logger{
		Filename:   filepath.Join(logDir, "ragflow_server_go.log"),
		MaxSize:    100, // MB
		MaxBackups: 10,
		MaxAge:     30, // days
		Compress:   true,
	}

	// 2. Formatting Config
	// Use JSON for production, Console for dev if preferred. 
	// The prompt specified "supports outputting straight to JSON (log.format=json)". We'll default to JSON here for the file output.
	encoderConfig := zap.NewProductionEncoderConfig()
	encoderConfig.TimeKey = "timestamp"
	encoderConfig.EncodeTime = zapcore.ISO8601TimeEncoder

	// Both stream and file cores
	jsonEncoder := zapcore.NewJSONEncoder(encoderConfig)
	consoleEncoder := zapcore.NewConsoleEncoder(encoderConfig)

	// File core writes to lumberjack
	fileCore := zapcore.NewCore(jsonEncoder, zapcore.AddSync(lumberjackLogger), zap.InfoLevel)
	// Stdout core writes to os.Stdout
	consoleCore := zapcore.NewCore(consoleEncoder, zapcore.AddSync(os.Stdout), zap.InfoLevel)

	// 3. Dual-Output Core
	core := zapcore.NewTee(fileCore, consoleCore)

	Logger = zap.New(core, zap.AddCaller())
	zap.ReplaceGlobals(Logger)
}
