package service

import (
	"crypto/sha256"
	"encoding/hex"

	"devrag/internal/entity"
)

// accountSubject is the identity every per-account limiter and one-time code is keyed on (R-129).
// A resolved account is identified by its user id, so every spelling the database collation reads as
// the same address shares one counter and one code budget. An address with no account is identified
// by its canonical spelling (common.CanonicalEmail), which is all there is to count against.
func accountSubject(user *entity.User, canonical string) string {
	if user != nil {
		return "acct:" + user.ID
	}
	return "addr:" + canonical
}

// emailKey is the Redis key part of a subject: a digest, never the address itself.
func emailKey(subject string) string {
	sum := sha256.Sum256([]byte(subject))
	return hex.EncodeToString(sum[:16])
}

// MaxListPage bounds the 1-based page number of every paged list (WR-06). With the page sizes at most 100, the
// SQL offset (page-1)*size stays below 10,000,000, so the product cannot overflow into a negative OFFSET.
const MaxListPage = 100_000
