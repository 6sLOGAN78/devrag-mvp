package main

import (
	"net/http"
	"time"

	"devrag/internal/common"
	"devrag/internal/config"
	"devrag/internal/dao"
	"devrag/internal/engine/redis"
	"devrag/internal/engine/storage"
	"go.uber.org/zap"

	"github.com/gin-gonic/gin"
)

func main() {
	// 1. Initialize Zap Logger
	common.InitLogger()
	defer common.Logger.Sync()
	zap.S().Info("Starting RAGFlow Go Engine initialization")

	// 2. Load config and Backends
	config.LoadConfig()
	dao.InitDB()
	redis.InitRedis()
	storage.InitStorage()

	// 3. Setup Gin Router (with custom Zap middleware)
	r := gin.New()
	
	// Custom Zap Logger Middleware
	r.Use(func(c *gin.Context) {
		start := time.Now()
		c.Next()
		latency := time.Since(start)
		
		status := c.Writer.Status()
		zap.L().Info("HTTP Request",
			zap.Int("status", status),
			zap.String("method", c.Request.Method),
			zap.String("path", c.Request.URL.Path),
			zap.String("client_ip", c.ClientIP()),
			zap.Duration("latency", latency),
		)
	})
	r.Use(gin.Recovery())

	r.GET("/api/health", func(c *gin.Context) {
		var result int
		err := dao.DB.Raw("SELECT 1").Scan(&result).Error

		dbStatus := gin.H{
			"status":  "ok",
			"elapsed": "0.0",
		}
		systemStatus := "ok"

		if err != nil {
			dbStatus["status"] = "nok"
			dbStatus["error"] = err.Error()
			systemStatus = "nok"
			zap.S().Error("Database health check failed", zap.Error(err))
		}

		c.JSON(http.StatusOK, gin.H{
			"status": systemStatus,
			"engine": "go",
			"db":     dbStatus,
		})
	})

	zap.S().Info("Starting Go server on :9381")
	if err := r.Run("0.0.0.0:9381"); err != nil {
		zap.S().Fatal("Server failed", zap.Error(err))
	}
}
