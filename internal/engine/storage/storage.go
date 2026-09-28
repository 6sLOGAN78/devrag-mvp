package storage

import (
	"context"
	"fmt"
	"log"

	"devrag/internal/config"
	"github.com/minio/minio-go/v7"
	"github.com/minio/minio-go/v7/pkg/credentials"
)

var Client *minio.Client

func InitStorage() {
	if config.CONF == nil {
		panic("Config not loaded before initializing Storage")
	}

	minioConf := config.CONF.Minio

	var err error
	Client, err = minio.New(minioConf.Endpoint, &minio.Options{
		Creds:  credentials.NewStaticV4(minioConf.User, minioConf.Password, ""),
		Secure: false, // CRITICAL for local MinIO
	})
	if err != nil {
		panic(fmt.Sprintf("Failed to initialize MinIO client: %v", err))
	}

	// Test authentication by listing buckets
	_, err = Client.ListBuckets(context.Background())
	if err != nil {
		panic(fmt.Sprintf("Failed to authenticate with MinIO: %v", err))
	}

	log.Println("MinIO connected successfully and authenticated (Go).")
}
