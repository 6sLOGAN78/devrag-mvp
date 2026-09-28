package redis

import (
	"context"
	"fmt"
	"log"

	"devrag/internal/config"
	goredis "github.com/redis/go-redis/v9"
)

var Client *goredis.Client

func InitRedis() {
	if config.CONF == nil {
		panic("Config not loaded before initializing Redis")
	}

	opt, err := goredis.ParseURL(config.CONF.Redis.URL)
	if err != nil {
		panic(fmt.Sprintf("Failed to parse Redis URL: %v", err))
	}

	Client = goredis.NewClient(opt)

	if err := Client.Ping(context.Background()).Err(); err != nil {
		panic(fmt.Sprintf("Failed to connect to Redis: %v", err))
	}

	log.Println("Redis connected successfully (Go).")
}
