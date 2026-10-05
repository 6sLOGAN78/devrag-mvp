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

## B-03 Disk space
- Status: open
- Affects: phase-exit gate (plan 01-15), Phase 3+ downloads
- Evidence: 4.2 GB free on / as measured at revision time (an earlier estimate of 5.5 GB was wrong). After .venv, node_modules, Go module cache and the image build only about 1.5 to 2 GB is expected to remain. The three clean-room runs in plan 01-15 MAY REQUIRE THE USER TO FREE DISK, and Phase 3+ model and ONNX downloads will not fit.
- Needed from user: freeing disk is the user's action; no plan frees it.
- Workaround in repo: `PREFLIGHT_ALLOW_LOW_DISK=1` is a recorded override. Nothing is pruned or deleted automatically.

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

## B-06 CI workflow not runnable here
- Status: open
- Affects: TEST (CI)
- Evidence: no git remote, so `.github/workflows/ci.yml` cannot execute.
- Needed from user: push to a remote with Actions enabled.
- Workaround in repo: workflow authored; it calls the same `make ci` target that runs locally.

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
- Workaround in repo: boot logger, DB verify and hooks are real; missing items are logged as not built. API-13 complete with blocker.

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
