//go:build integration

package service

import (
	"context"
	"testing"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"

	"devrag/internal/entity"
	"devrag/internal/server"
	"devrag/internal/testutil"
)

type tenantEnv struct {
	*userEnv
	tenant *Tenant
}

func newTenantEnv(t *testing.T, mutate func(*server.Config)) *tenantEnv {
	t.Helper()
	u := newUserEnv(t, mutate)
	return &tenantEnv{userEnv: u, tenant: NewTenant(u.db)}
}

// invite inserts a pending-invitation row directly: the invite endpoint lands in plan 02-22.
func (e *tenantEnv) invite(t *testing.T, userID, tenantID, invitedBy, role, status string) {
	t.Helper()
	ms := int64(1_700_000_000_000)
	require.NoError(t, e.raw.Create(&entity.UserTenant{
		ID: testutil.UniqueName("ut"), UserID: userID, TenantID: tenantID, InvitedBy: invitedBy, Role: role, Status: &status, CreateTime: &ms,
	}).Error)
}

func (e *tenantEnv) principal(t *testing.T, email string) Principal {
	t.Helper()
	pr, err := e.auth.ResolvePrincipal(context.Background(), e.login(t, email, testutil.FixtureCredential()).Token, []string{AuthTypeJWT})
	require.NoError(t, err)
	return pr
}

func TestTenantInfoUnconfiguredModelsAreEmptyStrings(t *testing.T) {
	e := newTenantEnv(t, nil)
	email := testutil.UniqueEmail("ti")
	p := e.register(t, email, testutil.FixtureCredential())
	info, err := e.tenant.Info(context.Background(), e.principal(t, email))
	require.NoError(t, err)
	assert.Equal(t, p.ID, info.TenantID)
	assert.Equal(t, "owner", info.Role)
	assert.NotEmpty(t, info.Name)
	assert.NotEmpty(t, info.ParserIDs)
	for _, v := range []string{info.LLMID, info.EmbdID, info.RerankID, info.ASRID, info.Img2TxtID, info.TTSID, info.OcrID} {
		assert.Empty(t, v)
	}
}

func TestTenantInfoShowsConfiguredDefaults(t *testing.T) {
	e := newTenantEnv(t, func(c *server.Config) {
		c.Models = server.ModelsConfig{DefaultChatModel: "chat-x", DefaultEmbeddingModel: "embed-x", DefaultRerankModel: "rerank-x", DefaultFactory: "OpenAI", DefaultBaseURL: "http://models.invalid/v1"}
	})
	email := testutil.UniqueEmail("tm")
	e.register(t, email, testutil.FixtureCredential())
	info, err := e.tenant.Info(context.Background(), e.principal(t, email))
	require.NoError(t, err)
	assert.Equal(t, "chat-x@OpenAI", info.LLMID)
	assert.Equal(t, "embed-x@OpenAI", info.EmbdID)
	assert.Equal(t, "rerank-x@OpenAI", info.RerankID)
}

func TestTenantInfoWithoutOwnWorkspaceIsNotFound(t *testing.T) {
	e := newTenantEnv(t, nil)
	_, err := e.tenant.Info(context.Background(), Principal{UserID: "u", TenantID: ""})
	assert.ErrorIs(t, err, ErrNoTenant)
}

func TestMembershipListShowsOwnerRowAndPendingInvite(t *testing.T) {
	e := newTenantEnv(t, nil)
	ownerEmail, inviteeEmail := testutil.UniqueEmail("own"), testutil.UniqueEmail("inv")
	owner := e.register(t, ownerEmail, testutil.FixtureCredential())
	invitee := e.register(t, inviteeEmail, testutil.FixtureCredential())
	stranger := e.register(t, testutil.UniqueEmail("str"), testutil.FixtureCredential())
	e.invite(t, invitee.ID, owner.ID, owner.ID, "invite", "1")

	list, err := e.tenant.ListMemberships(context.Background(), e.principal(t, inviteeEmail))
	require.NoError(t, err)
	require.Len(t, list, 2)
	byRole := map[string]Membership{}
	for _, m := range list {
		byRole[m.Role] = m
	}
	assert.Equal(t, invitee.ID, byRole["owner"].TenantID)
	assert.Equal(t, owner.ID, byRole["invite"].TenantID)
	assert.NotEmpty(t, byRole["invite"].TenantName)
	assert.Equal(t, owner.Nickname, byRole["invite"].OwnerNickname, "the invitee sees who owns the workspace")
	assert.Equal(t, invitee.Nickname, byRole["owner"].OwnerNickname)
	for _, m := range list {
		assert.NotEqual(t, stranger.ID, m.TenantID, "another tenant never appears")
	}
}

func TestMembershipListExcludesInactiveRowsAndOtherUsers(t *testing.T) {
	e := newTenantEnv(t, nil)
	aEmail, bEmail := testutil.UniqueEmail("a"), testutil.UniqueEmail("b")
	a := e.register(t, aEmail, testutil.FixtureCredential())
	b := e.register(t, bEmail, testutil.FixtureCredential())
	e.invite(t, a.ID, b.ID, b.ID, "normal", "0") // soft-deleted membership
	e.invite(t, b.ID, a.ID, a.ID, "invite", "1") // B's pending invite, not A's

	listA, err := e.tenant.ListMemberships(context.Background(), e.principal(t, aEmail))
	require.NoError(t, err)
	require.Len(t, listA, 1, "an inactive row is not a membership")
	assert.Equal(t, a.ID, listA[0].TenantID)

	listB, err := e.tenant.ListMemberships(context.Background(), e.principal(t, bEmail))
	require.NoError(t, err)
	require.Len(t, listB, 2)
}

func TestInviteRoleIsNotMembershipForTenantInfo(t *testing.T) {
	e := newTenantEnv(t, nil)
	ownerEmail, inviteeEmail := testutil.UniqueEmail("o2"), testutil.UniqueEmail("i2")
	owner := e.register(t, ownerEmail, testutil.FixtureCredential())
	invitee := e.register(t, inviteeEmail, testutil.FixtureCredential())
	e.invite(t, invitee.ID, owner.ID, owner.ID, "invite", "1")
	info, err := e.tenant.Info(context.Background(), e.principal(t, inviteeEmail))
	require.NoError(t, err)
	assert.Equal(t, invitee.ID, info.TenantID, "tenant info is the caller's own workspace, never the inviting one")
}
