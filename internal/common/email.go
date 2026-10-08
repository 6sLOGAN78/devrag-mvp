package common

import (
	"strings"

	"golang.org/x/text/unicode/norm"
)

// CanonicalEmail is the one email identity rule of the platform (R-129): trim surrounding white
// space, apply Unicode NFKC, then lower-case ASCII letters. Registration, login, password reset,
// invitations and the superuser seed all start from this form, and the Python engine implements the
// same function (common/security/emails.py) against the same vectors.
//
// Lower-casing is deliberately ASCII-only: the two runtimes disagree on special cases of non-ASCII
// letters (dotted capital I, final sigma), and the database collation already treats case and accent
// variants of one address as equal. Spellings the collation merges are therefore never trusted to
// pick a counter: limiters and one-time codes key on the resolved account (internal/service).
func CanonicalEmail(s string) string {
	s = norm.NFKC.String(strings.TrimSpace(s))
	return strings.Map(func(r rune) rune {
		if r >= 'A' && r <= 'Z' {
			return r + ('a' - 'A')
		}
		return r
	}, s)
}

// NewAccountEmailChars reports whether a canonical address holds only printable ASCII without
// white space. New accounts are restricted to that set (R-129) so two different strings can never
// both register while the database collation reads them as one address. Existing rows with other
// characters stay reachable: login, reset and invitations only canonicalise.
func NewAccountEmailChars(canonical string) bool {
	for i := 0; i < len(canonical); i++ {
		if c := canonical[i]; c <= ' ' || c > '~' {
			return false
		}
	}
	return true
}
