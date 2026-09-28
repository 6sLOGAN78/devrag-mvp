package main

import (
	"log"
	"net/http"

	"devrag/internal/config"
	"devrag/internal/dao"
	"devrag/internal/engine/redis"
	"devrag/internal/engine/storage"

	"github.com/gin-gonic/gin"
)

func main() {
	// 1. Load config and Backends
	config.LoadConfig()
	dao.InitDB()
	redis.InitRedis()
	storage.InitStorage()

	// 2. Setup Gin Router
	r := gin.Default()

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
		}

		c.JSON(http.StatusOK, gin.H{
			"status": systemStatus,
			"engine": "go",
			"db":     dbStatus,
		})
	})

	log.Println("Starting Go server on :9381")
	r.Run("0.0.0.0:9381")
}
