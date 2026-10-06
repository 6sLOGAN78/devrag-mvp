---
phase: 01-reconciliation-guardrails-and-dual-stack-foundation
verified: 2026-10-06T15:00:00Z
status: gaps_found
score: 4/5 roadmap success criteria verified
gaps:
  - truth: "DATA-03: pooled connections with retry/backoff (plan 01-06 must_have: pooled retrying DB honouring max_connections/stale_timeout)"
    status: failed
    reason: "CR-01. api/db/database.py overrides _connect() and calls pymysql.connect directly without super(), bypassing PooledDatabase checkout. Nothing is pooled, closed or capped; mysql.max_connections and stale_timeout are inert."
    artifacts:
      - path: "api/db/database.py"
        issue: "RetryingPooledMySQLDatabase._connect (lines 57-59) bypasses pool logic"
    missing:
      - "Move the database= keyword fix into a MySQLDatabase subclass below PooledDatabase in the MRO and drop the _connect override"
      - "Unit test: one physical connection across N connect/close cycles; MaxConnectionsExceeded at the cap"
  - truth: "Routes declared auth: jwt are not served publicly (WR-05)"
    status: failed
    reason: "/api/v1/system/version is declared jwt in conf/routes.yaml but served unauthenticated; no public_until_phase and no DECISIONS row (unlike /system/status, R-55)."
    missing:
      - "Add public_until_phase plus a DECISIONS row, or return 401 until Phase 2 auth middleware exists"
  - truth: "Health/deploy robustness (WR-02, WR-11, WR-12, WR-15, WR-17, WR-18)"
    status: partial
    reason: "Non-blocking for the stack, but each weakens a stated guardrail: unsafe write retry (WR-02), TLS fail-open (WR-12), clean_room zero-run false pass (WR-15), run_tests exit-5 swallowed (WR-17), CI workflow lacks setup-go/node/npm ci (WR-18). Should be fixed before relying on the gates."
human_verification:
  - test: "Push branch and confirm .github/workflows/ci.yml runs green"
    expected: "make ci and unit suites pass on a GitHub runner (WR-18 predicts failure as written)"
    why_human: "Workflow has never run (B-06)"
  - test: "Review docs/ (incl. docs/apikey llm.md) for credentials, then track docs/"
    expected: "docs/ committed without secrets"
    why_human: "Untracked pending user credential review (B-01); the authority for the decision register"
---

# Phase 1 Verification

Run by me: `make ci` 7/7 gates pass, ruff clean; `go test ./cmd/... ./internal/...` ok; `run_tests.py -m unit` 237 passed, 1 skipped (B-13). The clean-room gate (01-15) was not re-run, as instructed.

## Gaps
- **DATA-03 FAILED (BLOCKER)**: CR-01 confirmed by reading the code. The pool is a no-op. DATA-03 is marked Complete in REQUIREMENTS.md but is not delivered.
- **WR-05 (BLOCKER for SYS/API-auth intent)**: the version route is public although declared jwt.
- WR-02 (double-applied writes on retry), WR-01 (retry abandons on first failed reconnect) also affect DATA-03 quality.
- WR-12, WR-15, WR-17, WR-18: guardrail weaknesses (see frontmatter).

## Honest partials
- API-12: only `--api` and `--migrate` are real; `--admin`, `--ingestor` and `--syncer` refuse non-zero (B-07).
- API-13: superuser init, plugin load and daemons are absent (B-08); the startup hooks run on a throwaway loop (WR-07).
- SEC-05: the restricted unpickler is replaced by a CI ban on production unpickling (R-38); the numpy gadget test is skipped (B-13).
- DEPLOY-12: only self-signed TLS (B-10).

## Notes
No placeholder or fake code was found in production trees (check_placeholders passes). Other warnings (WR-03/04 redaction gaps, WR-06 health fan-out, WR-08..10, WR-13/14, WR-16, WR-19..22) are hardening items that do not defeat a must-have, but WR-03/04 weaken the SEC-04 redaction claim.
