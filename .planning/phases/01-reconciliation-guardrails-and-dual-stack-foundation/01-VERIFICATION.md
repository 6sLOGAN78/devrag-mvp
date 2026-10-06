---
phase: 01-reconciliation-guardrails-and-dual-stack-foundation
verified: 2026-10-07T00:35:00+05:30
status: passed
score: 5/5 roadmap success criteria verified
re_verification: true
previous_status: gaps_found
previous_score: 4/5
gaps_closed:
  - truth: "DATA-03: pooled connections with retry/backoff"
    closed: true
    evidence: "api/db/database.py: RetryingPooledMySQLDatabase(PooledDatabase, _PyMySQLDatabase) — the driver keyword fix sits below PooledDatabase in the MRO, no _connect override. test/unit_test/test_db_pool.py passes (reuse of one physical connection, cap, reconnect budget, writes not replayed); 11 of its 17 tests failed against the pre-fix code. Live test_db_core.py pool, cap and KILL tests are in the integration selection that passed in three gate runs."
  - truth: "Routes declared auth: jwt are not served publicly (WR-05)"
    closed: true
    evidence: "conf/routes.yaml marks /api/v1/system/version public_until_phase: 2 with DECISIONS R-84; test_route_auth_markers.py (static + mutation) and the Go behavioural test fail for an unmarked route; the live ingress test passed in the gate."
  - truth: "Guardrail robustness (WR-02, WR-11, WR-12, WR-15, WR-17, WR-18)"
    closed: true
    evidence: "clean_room.sh --runs 0 and --runs abc exit 2 (run by the orchestrator); test_container_scripts.py covers TLS fail-closed and log-dir chown; test_run_tests.py covers pytest exit 5; ci.yml has setup-go, setup-node, npm ci. 69 tests across these files pass."
human_verification:
  - test: "Push the branch and confirm .github/workflows/ci.yml runs green"
    expected: "make ci and the unit suites pass on a GitHub runner"
    why_human: "No git remote and no local Actions runner; the workflow has never run (B-06)"
  - test: "Review docs/ (including docs/apikey llm.md) for credentials, then track docs/"
    expected: "docs/ committed without secrets"
    why_human: "docs/ is the authority for the decision register and is still untracked pending the user's credential review (B-01); agents were blocked from reading that file"
---

# Phase 1 Re-Verification

Produced from the verifier agent's result (it returned its findings as text and did not write this file) plus checks run by the orchestrator, which are marked as such.

## Checks run

- Verifier: `make ci` 7/7 gates, ruff clean; `run_tests.py -m unit` 349 passed, 1 skipped (B-13); Go tests ok; read `ragflow-logs/clean_room_gate.log` — `clean-room: 3 run(s) passed`, EXIT 0.
- Orchestrator: the 69 tests in `test_db_pool.py`, `test_container_scripts.py`, `test_run_tests.py`, `test_clean_room_guard.py`, `test_route_auth_markers.py` pass; `clean_room.sh --runs 0` and `--runs abc` both exit 2. The verifier said it had not individually re-checked WR-11, WR-12, WR-17, WR-02 or run a pool-cap test; these orchestrator runs cover them.

## Success criteria

| SC | Result | Evidence |
|---|---|---|
| 1 Decision register, blockers, gitignore, CI gates | verified | `check_decisions.py`: 87 rows; 7/7 gates; `docs/apikey llm.md` ignored |
| 2 Preflight and clean bring-up within budget | verified | three clean-room runs, healthy in 35 to 40 s, 1905.6 MiB of 3891 MiB |
| 3 One schema owner, Go verify passes | verified | integration and Go tiers in the gate; R-86 records that Go compares type families only |
| 4 Both engines through Nginx, one envelope | verified | 60 e2e + 3 serial tests per run; status and `X-Api-Source` checked on port 8088 |
| 5 SPA shell, HTTP client, three harnesses green | verified | frontend 59 unit + 9 live per run; headless-Chrome test in the e2e tier |

## Remaining gaps

None that defeat a success criterion, requirement or plan must-have.

## Non-blocking findings (from the re-review; fix before or at the start of Phase 2)

- **CR-02** — `common/log_utils.py` redaction regex is quadratic on long word runs, and `api/apps/middleware.py` logs the unauthenticated `request.path` through it. Verifier timing: 8,000 characters took 1.55 s; 100,000 characters ran past 200 s. Through Nginx the request line is capped at about 8k (default buffers; not confirmed against this config), so about 1.5 s of event-loop time per request; direct hits on the Python port are unbounded. This is a real unauthenticated CPU denial-of-service. It does not defeat SEC-04 (redaction correctness) but should be fixed first in Phase 2.
- **WR-16 (partial)** — `clean_room.sh` uses `COMPOSE_PROJECT_NAME` from the environment while `preflight.sh` also reads `docker/.env`. `init_env.sh` never writes that variable and `clean_room.sh` refuses any project other than `devrag-stack`, so a `down -v` on a foreign project is not realistic; the two scripts should still resolve the name the same way.
- **WR-19 (partial)** — `render_conf.py` does not reject U+0085/U+2028/U+2029 in values.
- **WR-04 (partial) / WR-24** — redaction still misses `redis://:pw@host`, `Authorization: ApiKey ...`, later cookies and escaped quotes.
- **WR-25** — the route-marker tests do not exercise prefix or catch-all routes.
- **WR-26** — the pool's idle ping has no read timeout (not reproduced).

## Honest partials (BLOCKERS entries, unchanged)

API-12 (B-07), API-13 (B-08), SEC-05 via R-38 with the numpy test skipped (B-13), TLS self-signed only (B-10), deferred review findings (B-15).

## Not verified

- The CI workflow on a hosted runner (B-06).
- Port 8080 after the gap fixes; this gate ran on 8088 (R-87, B-16).
- Nginx request-line limits for CR-02.

## Human verification resolved (2026-10-07)

1. **GitHub Actions:** the workflow passed on `6sLOGAN78/devrag-mvp` (run 37517324018, commit `184e262`). A later run failed on commit `8a72a38` (the one that added `docs/`) because `test_repo_hygiene.py` still asserted that nothing under `docs/` was tracked; that stale guard was replaced and the run on `fd94011` passed.
2. **docs/ review:** the user reported `docs/` clean and released `docs/apikey llm.md`; an independent scan of all 228 files found no credentials. `docs/` is committed and pushed (B-01 closed, R-49).

Status changed from `human_needed` to `passed` on that basis. The non-blocking findings above remain open.
