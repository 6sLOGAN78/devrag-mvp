---
phase: 01-reconciliation-guardrails-and-dual-stack-foundation
plan: 23
subsystem: config-ci
tags: [render_conf, yaml, ci, github-actions]
requires: []
provides:
  - render_conf context-aware escaping, control-character rejection, post-render YAML validation
  - CI workflow with Go, Node 22, npm ci, read-only token
affects: [deploy, ci]
key-files:
  modified:
    - scripts/render_conf.py
    - test/unit_test/test_render_conf.py
    - .github/workflows/ci.yml
  created:
    - test/unit_test/test_ci_workflow.py
key-decisions:
  - "Quoted-ness decided by odd count of single quotes earlier on the template line; quoted escapes ' to '', unquoted rejects quotes"
  - "Output written to an O_EXCL 0600 temp file in the target dir then os.replace (no partial file, never wider than 0600)"
requirements-completed: [DEPLOY-11, SEC-04, TEST-01]
completed: 2026-10-06
---

# Phase 1 Plan 23: render_conf escaping and CI workflow Summary

Closes WR-19, IN-16 and WR-18. Operator secrets with quotes, backslashes, `#`, `:` or `${` now round-trip through the rendered YAML; control characters (newline etc.) are rejected naming only the variable; the rendered text is `yaml.safe_load`-checked before anything is written.

## Tasks and commits

| Task | Commit |
|------|--------|
| 1 render_conf (WR-19, IN-16) | 96d86df |
| 2 ci.yml + static test (WR-18) | 1bb7997 |

## Tests written first

- Task 1: the new test module failed at collection pre-fix (`InvalidValue` absent), so RED was an import error, not per-test behavior failures. After the fix: 25 passed (render_conf).
- Task 2: pre-fix 5 of 9 failed (permissions, setup-go, setup-node, npm ci, step order); after the fix 9 passed.
- No test weakened, skipped or xfailed. `-t render_conf` and `-t ci_workflow` were confirmed to select tests (25 and 9).

## Verification (as observed)

- `make ci`: 7/7 gates passed, ruff clean.
- `uv run python run_tests.py -m unit`: 345 passed, 1 skipped, 136 deselected.

## CI workflow: what was and was not verified

Verified locally: YAML parses; permissions are `contents: read`; setup-go uses `go-version-file: go.mod`; setup-node is 22 with npm cache on `web/package-lock.json`; `npm ci` runs in `web`; step order; actions pinned by major tag; no `secrets.`; every `make` target the workflow calls exists. No `GOTOOLCHAIN` env needed (the script only compares versions).
NOT verified: the workflow has never been run on GitHub Actions (no remote, no runner). Authored, never run. B-06 stays OPEN; the first real run is a human verification item.

## Deviations from Plan

- Output file is created via an `O_EXCL` 0600 temp file plus `os.replace` rather than `os.open` directly on the target, to guarantee no partial output file on write failure. 0600 at creation and no `chmod` hold.
- Unquoted-position rejection covers `'` and `"`; other characters (e.g. `:`) in numeric slots are caught by the post-render YAML check or left valid.

## Known Stubs

None.

## Self-Check: PASSED
