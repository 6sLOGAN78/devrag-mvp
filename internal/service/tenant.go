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
}

// TenantInfo is the caller's own workspace with its default model ids.
type TenantInfo struct {
	TenantID, Name, Role, ParserIDs                         string
	LLMID, EmbdID, RerankID, ASRID, Img2TxtID, TTSID, OcrID string
}

// Membership is one workspace the caller belongs to or is invited to.
type Membership struct {
	TenantID, TenantName, OwnerNickname, OwnerAvatar, Role string
	JoinedAt                                               time.Time
}

// Tenant serves tenant info and the membership list.
type Tenant struct{}

// NewTenant wires the service.
func NewTenant(TenantStore) *Tenant { return &Tenant{} }

// Info is not implemented yet.
func (*Tenant) Info(context.Context, Principal) (TenantInfo, error) {
	return TenantInfo{}, errNotImplemented
}

// ListMemberships is not implemented yet.
func (*Tenant) ListMemberships(context.Context, Principal) ([]Membership, error) {
	return nil, errNotImplemented
}
