---
phase: 1
slug: reconciliation-guardrails-and-dual-stack-foundation
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-10-05
---

# Phase 1 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> Source: `01-RESEARCH.md` § Validation Architecture. Versions there were checked against registries for existence only; nothing has been installed or run yet.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | Python: pytest + pytest-asyncio + pytest-xdist + httpx via `run_tests.py`. Go: stdlib `testing` + `httptest`, build-tag tiers (`integration`, `e2e`, `manual`, `cgo`). Frontend: vitest + jsdom + @testing-library/react. CI gates: Python scripts under `scripts/ci/` with fixture self-tests |
| **Config file** | none — Wave 0 installs (`pyproject.toml`, `go.mod`, `web/vitest.config.ts`, `scripts/ci/tests/`) |
| **Quick run command** | `uv run python run_tests.py -m unit && go test -race ./internal/... && (cd web && npm run test -- --run)` |
| **Full suite command** | `scripts/wait_stack.sh && uv run python run_tests.py -m "integration or e2e" && go test -tags=integration,e2e ./... && (cd web && npm run test:live)` |
| **Estimated runtime** | quick: under 60 seconds (estimate); full: a few minutes with the stack already up (estimate, to be measured in Wave 0) |

---

## Sampling Rate

- **After every task commit:** Run the quick run command (no stack needed)
- **After every plan wave:** Bring the stack up once, run the full suite command
- **Before `/gsd:verify-work`:** `scripts/clean_room.sh` (down -v, up, full suite, measured memory recorded) green three times in a row
- **Max feedback latency:** 60 seconds for the quick tier

Readiness rule: tests wait on `scripts/wait_stack.sh` and the one `wait_until` helper per language. No fixed sleeps in test trees; `scripts/ci/check_no_sleep.py` enforces it.

---

## Per-Task Verification Map

Task IDs are assigned by the planner; this map is keyed by success criterion and requirement until plans exist. The planner must attach each row to a task.

| Ref | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|-----|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| SC-1a | decision register (PROJECT.md constraint) | — | N/A | unit | `uv run python scripts/ci/check_decisions.py` | ❌ W0 | ⬜ pending |
| SC-1b | SEC-04 | T-1-secrets | `docs/apikey llm.md`, `.env*` ignored; `.env.example` tracked | unit | `uv run pytest test/unit_test/test_gitignore.py` | ❌ W0 | ⬜ pending |
| SC-1c | SEC-05, TEST-10 | T-1-pickle | gate exits non-zero on untrusted pickle and on placeholder in production tree | unit | `uv run pytest scripts/ci/tests` | ❌ W0 | ⬜ pending |
| SC-2a | DEPLOY-02 | — | N/A | unit | `uv run pytest test/unit_test/test_preflight.py` | ❌ W0 | ⬜ pending |
| SC-2b | DEPLOY-02..04, DEPLOY-13..16 | — | only documented ports published | integration | `scripts/clean_room.sh` | ❌ W0 | ⬜ pending |
| SC-3 | DATA-01, DATA-02, DATA-05, DATA-06 | — | N/A | integration | `uv run python run_tests.py -m integration -t test_schema` + `go test -tags=integration ./internal/dao/...` | ❌ W0 | ⬜ pending |
| — | DATA-03, DATA-04, DATA-08 | — | rollback on failure; lock released on same connection | integration (serial) | `uv run python run_tests.py -m "integration and serial"` | ❌ W0 | ⬜ pending |
| SC-4a..4e | SYS-01..07, API-01..05, API-09..11 | T-1-cors | CORS never wildcard with credentials; error envelope leaks no stack trace | e2e | `uv run python run_tests.py -m e2e -t test_routing` + `go test -tags=e2e ./...` | ❌ W0 | ⬜ pending |
| — | API-06 | — | N/A | unit | `uv run pytest test/unit_test/test_layering.py` | ❌ W0 | ⬜ pending |
| — | API-07, SEC-10 | T-1-injection | SQLi/command probe strings return 400 and never reach SQL | unit | `uv run ruff check --select S && uv run pytest test/unit_test/test_validation.py` | ❌ W0 | ⬜ pending |
| — | API-08 | — | N/A | e2e + frontend | `uv run python run_tests.py -m e2e -t test_openapi` + `npm run gen:api && npm run typecheck` | ❌ W0 | ⬜ pending |
| — | API-12, API-13 | — | unbuilt modes exit non-zero, never stubbed | unit + integration | `go test ./cmd/...` | ❌ W0 | ⬜ pending |
| — | DEPLOY-11, DEPLOY-12 | T-1-secrets | compose fails fast when a secret is unset | unit + integration | `uv run pytest test/unit_test/test_env_catalog.py test/integration/test_nginx.py` | ❌ W0 | ⬜ pending |
| SC-5a | UI-01 | — | N/A | unit + integration | `(cd web && npm run test -- --run && npm run build)` | ❌ W0 | ⬜ pending |
| SC-5b | UI-03 | T-1-token | 401 purges the stored token | unit + live | `(cd web && npm run test -- --run && npm run test:live)` | ❌ W0 | ⬜ pending |
| SC-5c | TEST-01..04 | — | N/A | all | full suite command | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `pyproject.toml` — pytest config, markers (`unit`, `integration`, `e2e`, `serial`), ruff security rules, `uv.lock`
- [ ] `run_tests.py` — runner with the documented flags
- [ ] `test/helpers/wait.py`, `internal/testutil/wait.go`, `web/src/test/wait-until.ts` — the only places a poll delay may live
- [ ] `scripts/ci/` — gates (placeholder/fake, pickle, no-sleep, decisions, generated-files-clean) each with known-bad and known-good fixtures
- [ ] `scripts/wait_stack.sh`, `scripts/preflight.sh`, `scripts/clean_room.sh`
- [ ] One real test file per Go tier tag; `web/vitest.config.ts` with a `live` project
- [ ] Framework installs: `uv sync`, `go mod tidy`, `npm ci`

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| `.github/workflows/ci.yml` runs on a hosted runner | TEST-10 | No git remote and no local Actions runner on this host | Push to a remote and confirm the workflow runs `make ci`; until then recorded in `.planning/BLOCKERS.md` as "authored, unverified here" |
| `vm.max_map_count` raised to 262144 | DEPLOY-02 | Needs sudo on the host | `sudo sysctl -w vm.max_map_count=262144`, then re-run `scripts/preflight.sh` |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 60s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
