//go:build manual

package testutil

import (
	"context"
	"encoding/json"
	"net/http"
	"os"
	"testing"
	"time"
)

// TestManualLanguageEndpoint asks a running stack which engine answers /api/v1/language.
// Run: MANUAL_BASE_URL=http://127.0.0.1:8080 go test -tags=manual ./internal/testutil
func TestManualLanguageEndpoint(t *testing.T) {
	base := os.Getenv("MANUAL_BASE_URL")
	if base == "" {
		base = "http://127.0.0.1:8080"
	}
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, base+"/api/v1/language", nil)
	if err != nil {
		t.Fatal(err)
	}
	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		t.Fatalf("stack not reachable at %s: %v", base, err)
	}
	defer resp.Body.Close()
	var body struct {
		Code int `json:"code"`
		Data struct {
			Engine string `json:"engine"`
		} `json:"data"`
	}
	if err := json.NewDecoder(resp.Body).Decode(&body); err != nil {
		t.Fatalf("response is not an envelope: %v", err)
	}
	t.Logf("status=%d x-api-source=%q engine=%q", resp.StatusCode, resp.Header.Get("X-API-Source"), body.Data.Engine)
	if resp.StatusCode != http.StatusOK || body.Code != 0 {
		t.Fatalf("unexpected answer: status %d code %d", resp.StatusCode, body.Code)
	}
}
