---
phase: 02
status: pending
created: 2026-10-08
source: 02-VERIFICATION.md (status human_needed, 5/5 success criteria verified, 0 gaps)
---

# Phase 2 — Human verification

Automated verification passed. These items need a person; none blocks later phases.

| # | Item | Requirement | How to check | Result |
|---|------|-------------|--------------|--------|
| 1 | Reset email arrives through a real SMTP server | AUTH-16 (B-20) | Set the SMTP variables in `docker/.env` to a real server, request a reset for your own address, confirm the 6-digit code arrives and works | pending |
| 2 | Chinese interface text reads correctly | UI-42 (B-18, B-20) | Switch the interface to 中文 and read the login, forgot-password, profile, API tokens and team pages | pending |
| 3 | Visual and accessibility pass in light and dark theme | UI-34..36 | Open the profile, API tokens, team and forgot-password pages in a browser at `http://127.0.0.1:8088`, in both themes, with keyboard only | pending |
