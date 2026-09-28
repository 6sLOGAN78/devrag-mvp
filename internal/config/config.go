package config

import (
	"fmt"
	"os"

	"gopkg.in/yaml.v3"
)

type Config struct {
	MySQL struct {
		Host     string `yaml:"host"`
		Port     string `yaml:"port"`
		User     string `yaml:"user"`
		Password string `yaml:"password"`
		DB       string `yaml:"db"`
	} `yaml:"mysql"`
	Redis struct {
		URL string `yaml:"url"`
	} `yaml:"redis"`
	Minio struct {
		Endpoint string `yaml:"endpoint"`
		User     string `yaml:"user"`
		Password string `yaml:"password"`
	} `yaml:"minio"`
}

var CONF *Config

func LoadConfig() {
	path := "conf/service_conf.yaml"
	if _, err := os.Stat(path); os.IsNotExist(err) {
		path = "../conf/service_conf.yaml"
	}
	
	data, err := os.ReadFile(path)
	if err != nil {
		panic(fmt.Sprintf("Configuration file not found. Please run generate_conf.sh first: %v", err))
	}

	var config Config
	if err := yaml.Unmarshal(data, &config); err != nil {
		panic(fmt.Sprintf("Failed to parse YAML: %v", err))
	}

	// Fail-Fast Validation
	if config.MySQL.Password == "" {
		panic("CRITICAL: mysql.password is missing in configuration! Refusing to start.")
	}

	CONF = &config
}
