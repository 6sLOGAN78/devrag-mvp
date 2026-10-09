---
phase: 03-models-knowledge-bases-and-upload
plan: 19
subsystem: verification
tags: [isolation, roles, visibility, api-tokens, leak-sweep, key-shape, envelope, log-masking, registry-driven]

requires:
  - phase: 03-models-knowledge-bases-and-upload
    provides: "03-12 to 03-18 provider, model, dataset, upload and document routes; 03-02 log redaction and Nginx masking; matrix and sweep fixtures"
provides:
  - "test_phase3_isolation.py: registry-driven table over all 17 Phase 3 rows for owner, admin, normal, strangers and API tokens, plus visibility, token non-elevation and member-removal proofs"
  - "KEY_SHAPE and ENVELOPE checks in scan_response, applied to every body and header of every row"
  - "a key-shaped sentinel in the leak sweep and a container-log scan for it, its 12-character fragments, the provider-echoed key and the stored envelope"
  - "a log test for key-shaped URL path segments in the Nginx and application request logs"
affects: [03-20, 03-27, Phase 3 verification]

key-files:
  created:
    - test/testcases/test_phase3_isolation.py
  modified:
    - test/testcases/_matrix_fixtures.py
    - test/testcases/_leak_sweep.py
    - test/testcases/test_response_leaks.py
    - test/testcases/test_log_token_masking.py

key-decisions:
  - "Rows whose registry roles include normal but whose object-level rule refuses a member for A's resource (PUT dataset, DELETE datasets, DELETE documents) are listed in NORMAL_IS_REFUSED_ON_A_RESOURCE; the table expects 403 there and separate tests prove a member manages its own datasets and documents."
  - "The Python request log records a matched route by its template (/api/v1/providers/<provider>/models), so the log test proves masking in the application log on an unmatched path and the template form on a matched one; Nginx masks both."
  - "The stack was not rebuilt: no product code changed."

requirements-completed: [TEN-13, SEC-02, SEC-03, SEC-06, LLM-16, LLM-24, KB-01]

completed: 2026-10-09
---

# Phase 3 Plan 19: Role, visibility and leak proofs Summary

**Every Phase 3 route is now replayed against every kind of caller from the registry: owner, admin and normal members get the status the row promises, strangers and other workspaces' tokens get the one not-found answer, tokens are refused on key-writing rows, `me` datasets are invisible to everyone but their creator, and a key-shaped sentinel appears in no response, header or container log line.**

## Commits

| Task | Commit | Description |
|------|--------|-------------|
| 1 | `e338b81`, `c73c694` | isolation table, world extension (normal member's private dataset), line-length fix |
| 2 | `dfb750c` | KEY_SHAPE and ENVELOPE scanner, sentinel log scan, path masking proof |

## What was built

- **Isolation table (`test_phase3_isolation.py`, 14 tests, 3 of them unit).** `INVOKERS` maps all 17 implemented rows under providers, models, datasets and documents to a request builder; `test_every_phase3_row_has_an_invoker` (unit) fails with the row key when a row or an override table entry has no match, and a second unit test proves the guard against a synthetic row. Rows that delete or change data prepare a disposable resource per call (`PREPARE`), so order does not matter. Every refused call is followed by a full `World.snapshot()` comparison and, for rows that call the provider, a check that the fake provider received nothing.
  - Roles: owner (own session), admin and normal (session with `tenant_id`) get 2xx or 403 per the row's `roles`.
  - Strangers (B, pending invitee, registered spare): the 404 triple; A's real dataset id gives a byte-identical answer to a random id.
  - Tokens: A's token 401 on the five `auth: jwt` rows and served on the `auth: api` rows with no credential fields; B's token 401 or 404.
  - Visibility: team dataset visible to members, `me` dataset only to its creator (the new normal-member-created `me` dataset is hidden from the owner and admin; the owner's is hidden from members); GET, PUT, DELETE, upload, list and delete documents all give the one 404 for owner, admin, other member and admin with `tenant_id`; the creator manages its dataset end to end.
  - Token non-elevation: A's API token gets 403 on a member's team dataset (PUT, DELETE) and on another member's document, while A's session is elevated.
  - A member reaches another workspace only through `tenant_id` or a resource id; another session of a normal member and an admin list providers and models, only the admin writes; after the owner removes a member through the real team API every route including the workspace selector gives 404.
- **Scanner.** `KEY_SHAPE` and `ENVELOPE` in `_leak_sweep.py`, reported by row and label, never the match; unit self-tests prove flagged shapes (also in headers) and that `used_tokens`, short `sk-` and `v1:` text are not flagged.
- **Sweep and logs.** The sentinel is `sk-or-v1-` plus 24 characters, built from parts; the stored envelope is read from MySQL right after the sentinel save; the provider-echoed key (`fake-secret-echo`) is registered as a secret and provoked in its own workspace; one test reads the `app` container output since the sweep start and asserts counts of zero for the sentinel, every 12-character window of it, the echoed key and each envelope.
- **Path masking.** A key-shaped segment (both shapes) is `.../marker-sk-***` in Nginx, `***` in the application log for an unmatched path, and the route template for a matched path; none of the key, its tail or the reversed tail appears in any engine's lines.

## Test results

- `test_phase3_isolation.py`: `64 passed` e2e (plus 3 unit).
- Combined e2e on the running stack (`LIVE_BASE_URL=http://127.0.0.1:8088`): isolation, cross-tenant matrix, response leaks, log token masking, request log: `123 passed, 21 deselected in 87.60s`.
- Unit tier: `1780 passed, 1 skipped, 875 deselected`, 0 failed (the skip is not from this plan). `uv run ruff check .`: all checks passed. `uv run python scripts/ci/run_all.py`: `7/7 gates passed`.

## Product defects found

None. All proofs passed against the product as built. Four test-side corrections were made while writing: an API token of a normal member is pinned to the member's own workspace (404 for A's dataset, not 403), so the elevation test uses A's own token; a dataset creator may remove any document in their dataset, so the elevation test uses another member's document in a dataset A did not create; the Python log shows a matched route's template, not the raw path; and one over-long line.

## Deviations from Plan

- **[Decision] Stack not rebuilt.** The plan's verify command contains `make up`; no product code changed in this plan and the running stack already ran all committed code (rebuilt at the end of 03-18).
- **[Decision] The echo provocation uses its own workspace** (`leakecho`) so the provider-test budget of workspace A in the sweep is not spent.
- **[Decision] Normal-member override list** (see key decisions).

## Known Stubs

None.

## Threat Flags

None. T-03-19-01 and -02 by the table and visibility tests; -03 by the removal test; -04 and -05 by the sentinel sweep, key-shape and envelope scanner and container log scan; -06 by the path masking test.

## Self-Check: PASSED

Commits `e338b81`, `c73c694` and `dfb750c` exist on `master`; the verification runs above were green.
