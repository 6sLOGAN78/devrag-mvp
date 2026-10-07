package service

import (
	"context"
	"errors"
	"time"

	"devrag/internal/dao"
	"devrag/internal/entity"
)

// ErrNoTenant means the caller has no workspace of their own.
var ErrNoTenant = errors.New("no workspace")

// TenantStore is the persistence surface of tenant info and membership listing. dao.DB satisfies it.
type TenantStore interface {
	FindTenant(ctx context.Context, id string) (*entity.Tenant, error)
	ListMemberships(ctx context.Context, userID string) ([]dao.MembershipRow, error)
	FindMemberRole(ctx context.Context, tenantID, userID string) (string, error)
	ListTenantMembers(ctx context.Context, tenantID string, includePending bool, limit, offset int) ([]dao.MemberRow, error)
	FindActiveUserByEmail(ctx context.Context, email string) (*entity.User, error)
	CreateInvite(ctx context.Context, inviterID string, row entity.UserTenant) error
	AcceptInvite(ctx context.Context, tenantID, userID string, now time.Time) (bool, error)
	DeclineInvite(ctx context.Context, tenantID, userID string) (bool, error)
}

// TenantInfo is the caller's own workspace with its default model ids; unconfigured ids are empty.
type TenantInfo struct {
	TenantID, Name, Role, ParserIDs                         string
	LLMID, EmbdID, RerankID, ASRID, Img2TxtID, TTSID, OcrID string
}

// Membership is one workspace the caller belongs to or is invited to (Role "invite").
type Membership struct {
	TenantID, TenantName, OwnerNickname, OwnerAvatar, Role string
	JoinedAt                                               time.Time
}

// Tenant serves tenant info, the membership list and team membership (members, invitations).
type Tenant struct {
	store   TenantStore
	limiter *Limiter
	limits  InviteLimits
	now     func() time.Time
	newID   func() string
}

// NewTenant wires the service. Invitations additionally need WithInvites: without a limiter they fail
// closed.
func NewTenant(store TenantStore) *Tenant {
	return &Tenant{store: store, now: time.Now, newID: randomID}
}

// Info returns the caller's own workspace, resolved from the principal (never from the request).
func (t *Tenant) Info(ctx context.Context, p Principal) (TenantInfo, error) {
	if p.TenantID == "" {
		return TenantInfo{}, ErrNoTenant
	}
	row, err := t.store.FindTenant(ctx, p.TenantID)
	if errors.Is(err, dao.ErrNotFound) {
		return TenantInfo{}, ErrNoTenant
	}
	if err != nil {
		return TenantInfo{}, err
	}
	return TenantInfo{
		TenantID: row.ID, Name: deref(row.Name), Role: p.Role, ParserIDs: row.ParserIds,
		LLMID: row.LLMID, EmbdID: row.EmbdID, RerankID: row.RerankID, ASRID: row.AsrID, Img2TxtID: row.Img2txtID,
		TTSID: deref(row.TtsID), OcrID: deref(row.OcrID),
	}, nil
}

// ListMemberships returns every membership row of the caller, pending invitations included. Only
// rows whose user_id is the caller's are read, so no other tenant's data can appear.
func (t *Tenant) ListMemberships(ctx context.Context, p Principal) ([]Membership, error) {
	rows, err := t.store.ListMemberships(ctx, p.UserID)
	if err != nil {
		return nil, err
	}
	out := make([]Membership, 0, len(rows))
	for _, r := range rows {
		m := Membership{
			TenantID: r.TenantID, TenantName: deref(r.TenantName), OwnerNickname: deref(r.OwnerNickname),
			OwnerAvatar: deref(r.OwnerAvatar), Role: r.Role,
		}
		if r.CreateTime != nil {
			m.JoinedAt = time.UnixMilli(*r.CreateTime).UTC()
		}
		out = append(out, m)
	}
	return out, nil
}
