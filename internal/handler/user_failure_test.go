package handler_test

import (
	"context"
	"errors"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/gin-gonic/gin"
	"github.com/stretchr/testify/assert"

	"devrag/internal/common"
	"devrag/internal/entity"
	"devrag/internal/handler"
	"devrag/internal/service"
)

type downStore struct{}

var errDown = errors.New("driver: bad connection")

func (downStore) FindUserByAccessToken(context.Context, string) (*entity.User, error) {
	return nil, errDown
}
func (downStore) FindUserByID(context.Context, string) (*entity.User, error) { return nil, errDown }
func (downStore) FindOwnMembership(context.Context, string) (*entity.UserTenant, error) {
	return nil, errDown
}
func (downStore) FindTenant(context.Context, string) (*entity.Tenant, error) { return nil, errDown }
func (downStore) SetAccessToken(context.Context, string, string) error       { return errDown }

type fixedResolver struct{}

func (fixedResolver) ResolvePrincipal(context.Context, string, []string) (service.Principal, error) {
	return service.Principal{UserID: "u1", TenantID: "u1", Role: "owner", AuthType: "jwt"}, nil
}

// IN-08 (R-114): a dependency failure behind the session routes is the 503 envelope, never a 500, and carries
// no driver text.
func TestSessionRoutesAnswer503WhenTheStoreIsDown(t *testing.T) {
	gin.SetMode(gin.TestMode)
	e := gin.New()
	e.Use(handler.AuthGate(fixedResolver{}, nil))
	u := handler.NewUser(service.NewAuth(downStore{}, "unit-test-secret-key-0000000000000000", common.AccessTokenMaxAge))
	e.GET("/v1/user/info", u.Info)
	e.POST("/api/v1/auth/logout", u.Logout)
	for _, tc := range []struct{ method, path string }{{http.MethodGet, "/v1/user/info"}, {http.MethodPost, "/api/v1/auth/logout"}} {
		req := httptest.NewRequest(tc.method, tc.path, nil)
		req.Header.Set("Authorization", "Bearer fake-credential")
		w := httptest.NewRecorder()
		e.ServeHTTP(w, req)
		assert.Equal(t, http.StatusServiceUnavailable, w.Code, tc.path)
		assert.JSONEq(t, `{"code":503,"message":"service unavailable","data":null}`, w.Body.String(), tc.path)
	}
}
