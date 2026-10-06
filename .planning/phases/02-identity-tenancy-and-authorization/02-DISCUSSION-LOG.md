# Phase 2: Identity, Tenancy and Authorization - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-10-07
**Phase:** 2-Identity, Tenancy and Authorization
**Areas discussed:** Sign-up and login rules, Password reset delivery, Sessions and tokens, Team invites and roles

The user selected all four areas and answered every question in person. In every case the user picked the option presented first and marked recommended.

---

## Sign-up and login rules

| Question | Options | Selected |
|----------|---------|----------|
| Who can create an account? | Open, with a switch / Always open / Invite or admin only | Open, with a switch |
| Password rules | Minimum 8 characters / 8+ with letter and number / No rule | Minimum 8 characters |
| First superuser at install | Yes, from env vars / Yes, RAGFlow's default credential / Not in Phase 2 | Yes, from env vars |
| Failed-login message | One generic message / Specific messages | One generic message |

## Password reset delivery

| Question | Options | Selected |
|----------|---------|----------|
| How the code reaches the user | SMTP with dev mailbox / SMTP only / Server log only | SMTP, with dev mailbox |
| Code strictness | 6 digits, 10 min, 5 tries / 6 digits, 5 min, 3 tries / You decide | 6 digits, 10 min, 5 tries |
| Reset for unknown email | Same response, no email / Say it isn't registered | Same response, no email |
| Existing logins after reset or change | Sign out everywhere / Keep current sessions | Sign out everywhere |

## Sessions and tokens

| Question | Options | Selected |
|----------|---------|----------|
| Token format | RAGFlow's format as documented / Same model, HMAC-SHA256 / Standard JWT | RAGFlow's format, as documented |
| Second device | Share the token / New login replaces old / Independent sessions | Share the token, as documented |
| Login length | 30 days / 7 days / No expiry | 30 days |
| API token storage | As documented for now / Hash now, show once | As documented for now |

**Notes:** the token-format question was only askable because `docs/apikey llm.md` was released by the user earlier the same day; it documents the itsdangerous-compatible format that the other docs call "JWT".

## Team invites and roles

| Question | Options | Selected |
|----------|---------|----------|
| Who may invite | Owner only / Owner and admin | Owner only |
| Invite people without an account | Existing accounts only / Also invite by email | Existing accounts only |
| Reply to an invitation | Accept or decline / Accept only | Accept or decline |
| Removing members | Owner removes, member leaves / Owner removes only / Not in Phase 2 | Owner removes, member leaves |

---

## Closing gate

Asked whether to settle the remaining smaller points (client token storage, rate-limit numbers, avatar handling, status/version routes) or write the context. **User's choice:** Write the context.

## Claude's Discretion

Password hashing scheme and parameters; client token storage default; rate-limit numbers; avatar handling; mail-catcher image; i18n wiring and first locales; theme persistence; empty home dashboard content.

## Deferred Ideas

Hash-plus-prefix API keys (Phase 8); invite-by-email for people without accounts; independent per-device sessions; OAuth/SSO and the admin service (Phase 8); password composition rules.
