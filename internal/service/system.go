// Package service holds business logic. It depends on the dao layer for data access.
package service

import (
	"context"
	"errors"
	"sync"
	"time"

	"devrag/internal/common"
	"devrag/internal/dao"
)

// ProbeTimeout caps every dependency probe (SYS-01).
const ProbeTimeout = 2 * time.Second

// ErrUnavailable means a dependency needed to answer is down or the schema is uninitialised.
var ErrUnavailable = errors.New("dependency unavailable")

// Pinger checks one dependency. The dao types satisfy it.
type Pinger interface {
	Ping(ctx context.Context) error
}

// SettingsReader reads system_settings. dao.DB satisfies it.
type SettingsReader interface {
	GetSetting(ctx context.Context, name string) (string, error)
}

// ProbeResult is the public result of one probe: status and elapsed time only.
type ProbeResult struct {
	Status    string `json:"status"`
	ElapsedMS int64  `json:"elapsed_ms"`
}

// Checks lists the probed dependencies.
type Checks struct {
	Database ProbeResult `json:"database"`
	Redis    ProbeResult `json:"redis"`
}

// HealthData is the /health payload.
type HealthData struct {
	Status string `json:"status"`
	Engine string `json:"engine"`
	Checks Checks `json:"checks"`
}

// ConfigData is the public, non-secret /api/v1/system/config payload.
type ConfigData struct {
	Engine     string `json:"engine"`
	APIVersion string `json:"api_version"`
	Service    string `json:"service"`
}

// VersionData is the /api/v1/system/version payload.
type VersionData struct {
	Version       string `json:"version"`
	SchemaVersion string `json:"schema_version"`
}

// LanguageData is the /api/v1/language payload.
type LanguageData struct {
	Engine string `json:"engine"`
}

// System implements the system endpoints.
type System struct {
	db       Pinger
	redis    Pinger
	settings SettingsReader
	timeout  time.Duration
}

// NewSystem wires the service to its dependencies.
func NewSystem(db Pinger, redis Pinger, settings SettingsReader) *System {
	return &System{db: db, redis: redis, settings: settings, timeout: ProbeTimeout}
}

func (s *System) probe(ctx context.Context, p Pinger) ProbeResult {
	started := time.Now()
	ctx, cancel := context.WithTimeout(ctx, s.timeout)
	defer cancel()
	status := "ok"
	if err := p.Ping(ctx); err != nil {
		status = "down"
	}
	return ProbeResult{Status: status, ElapsedMS: time.Since(started).Milliseconds()}
}

// Health runs both probes concurrently, each capped at ProbeTimeout. healthy is true only
// when every probe is ok.
func (s *System) Health(ctx context.Context) (data HealthData, healthy bool) {
	var wg sync.WaitGroup
	wg.Add(2)
	go func() { defer wg.Done(); data.Checks.Database = s.probe(ctx, s.db) }()
	go func() { defer wg.Done(); data.Checks.Redis = s.probe(ctx, s.redis) }()
	wg.Wait()
	healthy = data.Checks.Database.Status == "ok" && data.Checks.Redis.Status == "ok"
	data.Engine = common.APISourceGo
	data.Status = "down"
	if healthy {
		data.Status = "ok"
	}
	return data, healthy
}

// Version reports the application version and the schema version stored by the migration runner.
func (s *System) Version(ctx context.Context) (VersionData, error) {
	ctx, cancel := context.WithTimeout(ctx, ProbeTimeout)
	defer cancel()
	v, err := s.settings.GetSetting(ctx, common.SchemaVersionKey)
	if err != nil {
		if errors.Is(err, dao.ErrSettingNotFound) {
			return VersionData{}, errors.Join(ErrUnavailable, err)
		}
		return VersionData{}, ErrUnavailable
	}
	return VersionData{Version: common.AppVersion, SchemaVersion: v}, nil
}

// Config returns the public configuration summary.
func (s *System) Config() ConfigData {
	return ConfigData{Engine: common.APISourceGo, APIVersion: common.APIVersion, Service: common.ServiceName}
}

// Language returns the answering engine.
func (s *System) Language() LanguageData { return LanguageData{Engine: common.APISourceGo} }
