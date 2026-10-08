//go:build integration

package service

import (
	"context"
	"math"
	"testing"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"

	"devrag/internal/testutil"
)

// WR-06: page and page_size are bounded, so (page-1)*page_size can never overflow into a negative SQL
// offset (a database error that used to surface as 503). Out-of-range is a ValidationError (HTTP 400).
func TestMemberListRejectsOutOfRangePages(t *testing.T) {
	e := newMembersEnv(t, 100)
	email := testutil.UniqueEmail("pg")
	owner := e.register(t, email, testutil.FixtureCredential())
	p := e.principal(t, email)
	ctx := context.Background()
	for _, tc := range []struct{ page, size int }{
		{math.MaxInt, 100}, {math.MaxInt, 1}, {MaxListPage + 1, 1}, {1 << 40, 100}, {0, 10}, {-1, 10}, {1, 0}, {1, MaxMemberPageSize + 1},
	} {
		_, err := e.tenant.ListMembers(ctx, p, owner.ID, tc.page, tc.size)
		var ve *ValidationError
		assert.ErrorAs(t, err, &ve, "page %d size %d must be a validation error, not a store failure", tc.page, tc.size)
	}
	got, err := e.tenant.ListMembers(ctx, p, owner.ID, MaxListPage, MaxMemberPageSize)
	require.NoError(t, err, "the largest allowed page is a normal, empty page")
	assert.Empty(t, got)
}

func TestTokenListRejectsOutOfRangePages(t *testing.T) {
	e := newTokenEnv(t, nil)
	p := e.owner(t)
	ctx := context.Background()
	for _, tc := range []struct{ page, size int }{
		{math.MaxInt, 100}, {math.MaxInt, 1}, {MaxListPage + 1, 1}, {1 << 40, 100}, {0, 10}, {1, MaxTokenPageSize + 1},
	} {
		_, err := e.tok.List(ctx, p, tc.page, tc.size)
		var ve *ValidationError
		assert.ErrorAs(t, err, &ve, "page %d size %d", tc.page, tc.size)
	}
	got, err := e.tok.List(ctx, p, MaxListPage, MaxTokenPageSize)
	require.NoError(t, err)
	assert.Empty(t, got)
}
