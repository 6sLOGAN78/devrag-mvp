package main

import (
	"log"
	"net/http"

	"devrag/internal/config"
	"devrag/internal/dao"
	"devrag/internal/engine/redis"
	"devrag/internal/engine/storage"
	"devrag/internal/middleware"

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

	// Setup Protected Routes
	protected := r.Group("/api")
	protected.Use(middleware.AuthMiddleware())
	{
		protected.GET("/me", func(c *gin.Context) {
			// Extract context injected by the middleware
			userID, _ := c.Get("user_id")
			tenantID, _ := c.Get("tenant_id")

			c.JSON(http.StatusOK, gin.H{
				"status": "ok",
				"data": gin.H{
					"user_id":   userID,
					"tenant_id": tenantID,
					"message":   "You are securely authenticated and scoped to your tenant (Go Engine).",
				},
			})
		})

		// ---------------- KB APIs ----------------
		protected.POST("/knowledge-base", func(c *gin.Context) {
			tenantID := c.MustGet("tenant_id").(string)
			userID := c.MustGet("user_id").(string)

			var req struct {
				Name        string `json:"name"`
				Description string `json:"description"`
			}
			if err := c.ShouldBindJSON(&req); err != nil || req.Name == "" {
				c.JSON(http.StatusBadRequest, gin.H{"status": "error", "message": "Missing name"})
				return
			}

			// Generate UUID (simplified for MVP: use string manipulation or a library. Using hardcoded mock for time/simplicity isn't good, we'll use a random string)
			import_crypto_rand := true
			_ = import_crypto_rand // bypass import check, just use UUID library or pseudo UUID
			
			// Actually we need google/uuid. I will use a simple query to DB to use UUID() or just generate a fast 32 hex
			
			// A simpler approach for the MVP:
			var newUUID string
			dao.DB.Raw("SELECT REPLACE(UUID(), '-', '')").Scan(&newUUID)
			kbID := newUUID

			kb := dao.Knowledgebase{
				ID:          kbID,
				TenantID:    tenantID,
				Name:        req.Name,
				Description: req.Description,
				CreatedBy:   userID,
				EmbdID:      "default-embd",
				Permission:  "me",
				ParserID:    "naive",
			}

			if err := dao.DB.Create(&kb).Error; err != nil {
				c.JSON(http.StatusInternalServerError, gin.H{"status": "error", "message": err.Error()})
				return
			}

			c.JSON(http.StatusOK, gin.H{"status": "ok", "data": gin.H{"id": kb.ID, "name": kb.Name}})
		})

		protected.GET("/knowledge-base", func(c *gin.Context) {
			tenantID := c.MustGet("tenant_id").(string)
			var kbs []dao.Knowledgebase
			if err := dao.DB.Where("tenant_id = ?", tenantID).Find(&kbs).Error; err != nil {
				c.JSON(http.StatusInternalServerError, gin.H{"status": "error", "message": err.Error()})
				return
			}

			// Map to JSON output
			var output []map[string]interface{}
			for _, kb := range kbs {
				output = append(output, map[string]interface{}{
					"id":          kb.ID,
					"name":        kb.Name,
					"description": kb.Description,
					"created_by":  kb.CreatedBy,
					"created_at":  kb.CreateTime,
				})
			}
			if output == nil {
				output = make([]map[string]interface{}, 0)
			}

			c.JSON(http.StatusOK, gin.H{"status": "ok", "data": output})
		})

		protected.DELETE("/knowledge-base/:id", func(c *gin.Context) {
			tenantID := c.MustGet("tenant_id").(string)
			kbID := c.Param("id")

			result := dao.DB.Where("id = ? AND tenant_id = ?", kbID, tenantID).Delete(&dao.Knowledgebase{})
			if result.Error != nil {
				c.JSON(http.StatusInternalServerError, gin.H{"status": "error", "message": result.Error.Error()})
				return
			}
			if result.RowsAffected == 0 {
				c.JSON(http.StatusNotFound, gin.H{"status": "error", "message": "KB not found or unauthorized"})
				return
			}

			c.JSON(http.StatusOK, gin.H{"status": "ok", "message": "KB deleted successfully"})
		})
	}

	log.Println("Starting Go server on :9381")
	r.Run("0.0.0.0:9381")
}
