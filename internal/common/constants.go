// Package common holds identifiers, return codes, the response envelope and the logger
// shared by every layer of the Go server (D-22: one constant per documented identifier).
package common

// Documented identifiers. These mirror common/constants.py; a unit test compares the two.
const (
	ServiceName = "ragflow_server"
	IndexPrefix = "ragflow_"
	BucketName  = "ragflow"
	NetworkName = "ragflow"
	APISourceGo = "go"

	// APISourceHeader is the response header naming the engine that answered.
	APISourceHeader = "X-API-Source"
	// APIVersion is the public API version reported by /api/v1/system/config.
	APIVersion = "v1"
	// SchemaVersionKey is the system_settings row written by the Python migration runner.
	SchemaVersionKey = "schema.version"
)

// AppVersion is the application version reported by /api/v1/system/version.
const AppVersion = "0.1.0"
