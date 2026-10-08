package service

import (
	"context"
	"errors"
	"testing"
	"time"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"

	"devrag/internal/common"
	"devrag/internal/dao"
	"devrag/internal/entity"
	"devrag/internal/server"
)

// memCounter is a unit-tier Counter that never limits.
type memCounter struct{}

func (memCounter) Incr(context.Context, string, time.Duration) (int64, time.Duration, error) {
	return 1, time.Minute, nil
}
func (memCounter) Count(context.Context, string) (int64, time.Duration, error) { return 0, 0, nil }
func (memCounter) Delete(context.Context, string) error                        { return nil }

// failingAccountStore reports one configurable failure from each lookup the login path makes.
type failingAccountStore struct {
	user          *entity.User
	findUserErr   error
	membershipErr error
	tenantErr     error
	findByIDErr   error
	swapErr       error
}

func (f *failingAccountStore) CreateAccount(context.Context, dao.NewAccount) error { return nil }
func (f *failingAccountStore) FindUserByEmail(context.Context, string) (*entity.User, error) {
	return f.user, f.findUserErr
}
func (f *failingAccountStore) FindUserByID(context.Context, string) (*entity.User, error) {
	return f.user, f.findByIDErr
}
func (f *failingAccountStore) SwapAccessToken(context.Context, string, *string, string) (bool, error) {
	return true, f.swapErr
}
func (f *failingAccountStore) TouchLastLogin(context.Context, string, time.Time) error { return nil }
func (f *failingAccountStore) FindOwnMembership(context.Context, string) (*entity.UserTenant, error) {
	return &entity.UserTenant{TenantID: "t1", Role: "owner"}, f.membershipErr
}
func (f *failingAccountStore) FindTenant(context.Context, string) (*entity.Tenant, error) {
	return &entity.Tenant{ID: "t1"}, f.tenantErr
}

func accountWith(t *testing.T, st *failingAccountStore) *Account {
	t.Helper()
	hash, err := common.HashPassword("fake-store-pass-01")
	require.NoError(t, err)
	active, inner := "1", "0123456789abcdef0123456789abcdef"
	st.user = &entity.User{ID: "u1", Email: "u1@example.test", Password: &hash, Status: &active, AccessToken: &inner}
	cfg := server.Config{}
	cfg.Security.SecretKey = "unit-test-secret-key-0000000000000000"
	cfg.RateLimit = server.DefaultRateLimit()
	cfg.RateLimit.LoginPerIP = 100
	return NewAccount(st, NewLimiter(memCounter{}, "u"), cfg)
}

func loginInput() LoginInput {
	return LoginInput{Email: "u1@example.test", Password: "fake-store-pass-01", ClientIP: "198.51.100.1"}
}

// IN-08 (R-114): a store failure during login is ErrUnavailable (503), never an unclassified 500, and a user
// without a workspace is ErrNoTenant (404) rather than a leaked dao.ErrNotFound.
func TestLoginStoreFailuresAreUnavailable(t *testing.T) {
	boom := errors.New("driver: bad connection")
	for name, st := range map[string]*failingAccountStore{
		"user lookup": {findUserErr: boom},
		"membership":  {membershipErr: boom},
		"tenant":      {tenantErr: boom},
	} {
		_, err := accountWith(t, st).Login(context.Background(), loginInput())
		assert.ErrorIs(t, err, ErrUnavailable, name)
		assert.NotContains(t, err.Error(), "bad connection", name+": driver text must not travel with the error")
	}
}

func TestLoginWithoutAWorkspaceIsErrNoTenant(t *testing.T) {
	_, err := accountWith(t, &failingAccountStore{membershipErr: dao.ErrNotFound}).Login(context.Background(), loginInput())
	assert.ErrorIs(t, err, ErrNoTenant)
	_, err = accountWith(t, &failingAccountStore{tenantErr: dao.ErrNotFound}).Login(context.Background(), loginInput())
	assert.ErrorIs(t, err, ErrNoTenant)
}
