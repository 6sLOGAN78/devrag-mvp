# BLOCKERS

Convention (D-27): anything that cannot be implemented or verified in this environment is recorded here. It is never faked, stubbed or silently skipped.

Each entry has: ID `B-NN`, Title, Status (`open` | `mitigated` | `closed`), Affects (requirement IDs or phase), Evidence, Needed from user, Workaround in repo.

## B-01 `docs/apikey llm.md` unreviewed and uncommitted
- Status: open
- Affects: R-49, Phase 3+ (LLM layer)
- Evidence: file is off-limits to agents and may contain credential material; it is neither read nor relied on.
- Needed from user: review the file and say which parts, if any, are requirements.
- Workaround in repo: listed in `.gitignore`; `docs/` is never staged wholesale.

## B-02 `vm.max_map_count` is 65530
- Status: open
- Affects: DEPLOY (Elasticsearch), Phase 1 preflight
- Evidence: Elasticsearch wants 262144; changing it needs sudo, which agents do not use. Single-node ES started at 65530 with a WARN.
- Needed from user: `sudo sysctl -w vm.max_map_count=262144` if desired.
- Workaround in repo: preflight fails by default; `PREFLIGHT_ALLOW_LOW_MAP_COUNT=1` records an override.
- Update 2026-10-06 (plan 01-15): still 65530. The phase-exit gate ran with `PREFLIGHT_ALLOW_LOW_MAP_COUNT=1` on all three runs (recorded in `ragflow-logs/preflight-overrides.log`); Elasticsearch reached healthy each time.

## B-03 Disk space
- Status: open
- Affects: phase-exit gate (plan 01-15), Phase 3+ downloads
- Evidence: 4.2 GB free on / as measured at revision time (an earlier estimate of 5.5 GB was wrong). After .venv, node_modules, Go module cache and the image build only about 1.5 to 2 GB is expected to remain. The three clean-room runs in plan 01-15 MAY REQUIRE THE USER TO FREE DISK, and Phase 3+ model and ONNX downloads will not fit.
- Needed from user: freeing disk is the user's action; no plan frees it.
- Workaround in repo: `PREFLIGHT_ALLOW_LOW_DISK=1` is a recorded override. Nothing is pruned or deleted automatically.
- Update 2026-10-06 (plan 01-15): free space on / changed several times during the phase for reasons outside this project (4.2 GB, then about 23 GB, then 4.6 GB, then about 9 GB). Measured 9 GB free before the gate and 9G after each of the three clean-room runs; the disk override was NOT used. This project accounts for roughly 1.5 GB of working files plus about 1.7 GB of Docker images. Still open: free space on this host is not stable, and Phase 3+ model downloads need headroom that is not guaranteed.

## B-04 No GPU
- Status: open
- Affects: DEPLOY-06
- Evidence: host has no NVIDIA GPU; the `gpu` compose profile cannot be verified.
- Needed from user: a GPU host for verification.
- Workaround in repo: profile authored but unverified.

## B-05 Earlier compose projects present
- Status: mitigated
- Affects: Phase 1 deployment
- Evidence: stopped compose project `devrag` and project `docker` volumes from earlier attempts exist.
- Needed from user: decide whether to remove them; they are not ours to delete.
- Workaround in repo: do not remove; the new project name is `devrag-stack`.
- Update 2026-10-06 (plan 01-15): after three `down -v` cycles of `devrag-stack`, the 16 non-`devrag-stack` containers and 13 non-`devrag-stack` volumes matched a snapshot taken before the gate (diff empty); project `devrag` still has 6 containers.

## B-06 CI workflow not runnable here
- Status: closed
- Affects: TEST (CI)
- Evidence: no git remote, so `.github/workflows/ci.yml` cannot execute.
- Needed from user: push to a remote with Actions enabled.
- Workaround in repo: workflow authored; it calls the same `make ci` target that runs locally.
- Update 2026-10-07 (plan 01-23): `ci.yml` now sets up Go from `go.mod`, Node 22 and runs `npm ci`, with `contents: read` permissions. It has still never run on GitHub; status stays open.
- Closed 2026-10-07: pushed to `6sLOGAN78/devrag-mvp` (user asked for `master` to be replaced; old history kept at branch `archive/mvp-master`, commit `3fe760d`). Workflow run 37517324018 on commit `184e262` passed (job `guardrails`, 1m52s). Follow-up, not blocking: the pinned action versions target the deprecated Node 20 runtime, and `ubuntu-latest` changes to Ubuntu 26 from 2026-10-19.

## B-07 Go run modes
- Status: open
- Affects: API-12, Phase 8 and v2
- Evidence: `--admin` (Phase 8), `--ingestor` and `--syncer` (v2 mirrors per D-01) are not built.
- Needed from user: none unless scope changes.
- Workaround in repo: these modes refuse with non-zero exit naming this entry. API-12 complete with blocker.

## B-08 Python boot items
- Status: open
- Affects: API-13
- Evidence: superuser init (Phase 2), plugin load (Phase 7), background daemons (Phase 4) are absent.
- Needed from user: none.
- Workaround in repo: boot logger, DB verify (no DDL), hooks and serve are real and tested in order. The missing items are deliberately not stubbed: `register_startup_hook` is the extension point for them. API-13 complete with blocker.

## B-09 Real model source for Phase 3+
- Status: open
- Affects: R-50, D-31, Core Value verification
- Evidence: no API key is configured; host `ollama` binary exists with no models pulled.
- Needed from user: an OpenAI-compatible key, or approval to pull one small chat and one small embedding model.
- Workaround in repo: Ollama service in compose with one small chat and one small embedding model unless a key is supplied.

## B-10 TLS only verified with a self-signed certificate
- Status: open
- Affects: DEPLOY-12 (Phase 8)
- Evidence: no real certificate or domain available.
- Needed from user: real certificate for production.
- Workaround in repo: self-signed certificate under ignored `docker/nginx/certs/`.

## B-11 `cgo` Go test tier is a mechanism proof only
- Status: open
- Affects: TEST-04
- Evidence: no native parsers exist yet to exercise cgo.
- Needed from user: none.
- Workaround in repo: tier runs a minimal cgo proof; real coverage lands with native parsers.

## B-12 MySQL 8.4 LTS upgrade needs approval
- Status: open
- Affects: R-42, D-17
- Evidence: `mysql:8.0.40` has had no security patches since 2026-04-30; docs pin it.
- Needed from user: approval to move to `mysql:8.4`, after which auth-plugin behaviour with PyMySQL and go-sql-driver must be verified.
- Workaround in repo: image is parameterised as `MYSQL_IMAGE`, default is the docs pin.

## B-13 numpy-whitelist gadget regression test skipped (numpy not installed)
- Status: open
- Affects: SEC-05 (R-38), plan 01-03
- Evidence: `test/unit_test/test_unpickle.py::test_numpy_allow_list_unpickler_is_bypassable` skips because numpy is not in the user-approved Phase 1 package set, so the gadget demonstration has never run here. The gate and production-tree tests do run.
- Needed from user: none; the test activates once numpy is installed by a later plan (DeepDoc).
- Workaround in repo: `check_pickle.py` rejects all unpickling in production trees regardless.

## B-14 Phase-exit gate needs 4 GB of available RAM
- Status: open
- Affects: `scripts/clean_room.sh` / `scripts/preflight.sh` on this host
- Evidence: 2026-10-06, with the stack stopped only 2763 MB was available (other programs held about 10.7 GB of 15.7 GB) against `PREFLIGHT_MIN_RAM_MB=4096`. The user freed memory; the gate then ran with 5.2 to 6.9 GB available. The threshold was not lowered.
- Needed from user: close other workloads before running the gate on this machine.
- Workaround in repo: none applied; `PREFLIGHT_MIN_RAM_MB` exists but was left at its default.
- Update 2026-10-07 (plan 01-24): gap-closure gate ran with 6513 to 7246 MB available before start (stack stopped); threshold unchanged at 4096 MB; no user action was needed this time.

## B-15 Deferred Phase 1 review findings
- Status: open
- Affects: Phase 2 planning (health probes, Go schema verification, dev proxy, secret scanning)
- Evidence: `01-REVIEW.md` findings not fixed by gap plans 01-16..01-24. Every other warning (WR-01..05, WR-07..09, WR-11..19, WR-21, WR-22) and CR-01 was fixed and covered by tests.

| Finding | Reason deferred | Lands |
|---|---|---|
| WR-06 health routes open four fresh backend connections per request | Needs a single-flight cached probe layer on the application pool; no Phase 1 must-have fails | Start of Phase 2 |
| WR-10 Go schema verify compares type families only | Needs a full comparison against `conf/schema.json`; the claim is narrowed by R-86 meanwhile | First Go DAO consumer, Phase 2 |
| WR-20 Vite dev proxy misses Go exact paths that carry a query string | Dev server only; no Phase 1 Go exact route is called with a query string; production Nginx is correct | Phase 2, when `GET /api/v1/users?...` is first used |
| WR-23 `check_secrets` blind spots | Tightening needs false-positive triage across env examples and fixtures; no real secret is committed | Start of Phase 2, before credential handling |
| IN-01..IN-18 | Informational; out of scope for gap closure | Rolling backlog |

- Needed from user: nothing now; review when Phase 2 is planned.
- Workaround in repo: none.

## B-16 Host port 8080 taken by another project
- Status: mitigated
- Affects: dev stack and exit gate on this host
- Evidence: 2026-10-07, container `compose-gateway-1` (compose project `compose`, not ours, untouched) published 8080; preflight failed on the port before any teardown.
- Needed from user: none; the user chose to move devRag to another port.
- Workaround in repo: `SVR_WEB_HTTP_PORT=8088` in the git-ignored `docker/.env` (R-87); `clean_room.sh` now derives `E2E_BASE_URL`, `MANUAL_BASE_URL` and `LIVE_BASE_URL` from that value.
