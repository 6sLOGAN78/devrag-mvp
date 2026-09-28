package dao

import (
	"fmt"
	"log"

	"devrag/internal/config"
	"gorm.io/driver/mysql"
	"gorm.io/gorm"
)

var DB *gorm.DB

func InitDB() {
	if config.CONF == nil {
		panic("Config not loaded before initializing DB")
	}

	mysqlConf := config.CONF.MySQL
	// DSN format: user:password@tcp(host:port)/dbname?charset=utf8mb4&parseTime=True&loc=Local
	dsn := fmt.Sprintf("%s:%s@tcp(%s:%s)/%s?charset=utf8mb4&parseTime=True&loc=Local",
		mysqlConf.User,
		mysqlConf.Password,
		mysqlConf.Host,
		mysqlConf.Port,
		mysqlConf.DB,
	)

	var err error
	DB, err = gorm.Open(mysql.Open(dsn), &gorm.Config{})
	if err != nil {
		panic(fmt.Sprintf("Failed to connect to database: %v", err))
	}

	// Run Migrations
	err = DB.AutoMigrate(&User{}, &Tenant{}, &UserTenant{}, &Document{}, &Knowledgebase{})
	if err != nil {
		panic(fmt.Sprintf("Failed to run database migrations: %v", err))
	}

	log.Println("Database connection successfully established and migrations applied (Go).")
}
