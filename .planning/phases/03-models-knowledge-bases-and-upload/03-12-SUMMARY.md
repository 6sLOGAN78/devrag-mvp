---
phase: 03-models-knowledge-bases-and-upload
plan: 12
subsystem: api
tags: [providers, handlers, executors, error-mapping, masking, cross-tenant, leak-sweep, secretbox]

requires:
  - phase: 03-models-knowledge-bases-and-upload
    provides: "03-04 registry rows, tenant_scope, permission rows; 03-05 fake provider; 03-09 credential and model services; 03-10 provider service; 03-11 LLMBundle"
provides:
  - api/utils/blocking.py (DB_EXECUTOR, PROVIDER_EXECUTOR, DOCSTORE_EXECUTOR, STORAGE_EXECUTOR, run_blocking)
  - api/apps/service_errors.py (service_error_response, not_found_response)
  - api/apps/handler_support.py (acting_scope, forbid_unless, credentials_visible)
  - api/apps/restful_apis/provider_api.py (provider_bp, six handlers)
  - test/helpers/fake_provider.py stack mode (fake_provider_stack, running_stack_fake_provider)
affects: [03-13 models routes, 03-14 dataset routes, 03-16 upload, 03-19, Models page]

tech-stack:
  added: []
  patterns:
    - "Handlers resolve scope (404), then permission (403), then existence (404); a caller who may not write learns nothing about what exists"
    - "Blocking work goes through run_blocking(<named executor>, fn, timeout=...); settings are read on the loop, never inside the worker thread"
    - "credentials_visible(scope) is the one decision for address and last4: subject in {owner, admin}, never the role"
    - "Request models use extra=forbid; the cross-tenant matrix builders pass only the accepted smuggled field (tenant_id) and the flow test asserts the 400 for unknown fields"

key-files:
  created:
    - api/utils/blocking.py
    - api/apps/service_errors.py
    - api/apps/handler_support.py
    - api/apps/restful_apis/provider_api.py
    - test/unit_test/test_service_errors.py
    - test/unit_test/test_handler_support.py
    - test/testcases/test_provider_flow.py
    - .planning/phases/03-models-knowledge-bases-and-upload/deferred-items.md
  modified:
    - api/apps/__init__.py
    - api/utils/reasons.py
    - common/security/secretbox.py
    - conf/routes.yaml
    - api/apps/route_policy_gen.py
    - internal/common/route_policy_gen.go
    - test/helpers/fake_provider.py
    - test/testcases/_matrix_fixtures.py
    - test/testcases/test_cross_tenant_matrix.py
    - test/testcases/test_response_leaks.py
    - test/unit_test/test_secretbox.py
    - test/unit_test/test_route_policy.py
    - test/unit_test/test_probes.py
    - web/openapi/openapi.json
    - web/src/interfaces/openapi.d.ts

key-decisions:
  - "The GET /providers/{provider}/instances/{instance} row is tightened from auth api to jwt: it shows last4 and the address, its permission is update_llm_keys (no token subject has it), so a token could only ever get 403 there; as a jwt row a token gets the gate's 401 and the cross-tenant matrix keeps its rule (jwt row, API token, 401)"
  - "POST /providers/{provider}/instances decides add-or-create from the body: credentials (key, base_url or api_version) for an existing instance are 400 instance_exists; credentials for a new instance run the full save; models only run add_models; no credentials and no instance is the one 404"
  - "PUT with an unknown provider name is 400 provider_unknown (a body value, the supported list is public); every path-addressed route answers the one 404 for an unknown or unconfigured provider"
  - "DELETE answers {deleted: true}; the instance detail answers the instance view (name, configured, models as composite ids, last4, base_url, api_version)"
  - "An empty or malformed tenant_id is not 'absent': any value that is not 32 lowercase hex characters is the single not-found answer (re.fullmatch, so a trailing newline does not slip through)"
  - "run_blocking waits on the future with asyncio.wait, so a TimeoutError raised inside the worker is never mistaken for a missed deadline; a missed deadline maps to provider_timeout for the provider pool and the new reason operation_timeout for the others"
  - "Reasons operation_timeout and instance_exists were added to api/utils/reasons.py (the one place a reason is spelled)"

patterns-established:
  - "Later route plans call acting_scope(tenant_id) -> forbid_unless(scope, area, action) -> run_blocking(...) -> service_error_response(exc), in that order, and pass include_credentials=credentials_visible(scope)"
  - "A new registry row flips to implemented together with a BUILDERS or NO_ID_CHECKS entry and a sweep exerciser; the guards fail otherwise"
  - "Tests that need the dockerised app to reach a fake third party use running_stack_fake_provider (0.0.0.0, two ephemeral ports, one recorder, host.docker.internal) and register fake keys built from parts"

requirements-completed: [LLM-16, LLM-23, LLM-24, LLM-25, LLM-26, LLM-27, SEC-02, SEC-03, TEN-13]

duration: ~1h30m
completed: 2026-10-09
---

# Phase 3 Plan 12: Provider routes, executors, error mapping and isolation coverage Summary

**The six provider routes are served by Python behind the gate: owners and admins save, rotate, re-address and delete credentials after a real test call per model, everyone else sees masked views, a foreign workspace is the single 404, and a rejected provider is always HTTP 400. All of it is proven through Nginx on the rebuilt stack against the recording fake provider, in the cross-tenant matrix and in the leak sweep.**

## Accomplishments

- `api/utils/blocking.py`: four named, bounded `ThreadPoolExecutor`s (`db` 16, `provider` 8, `docstore` 8, `storage` 8) and `run_blocking` with an explicit deadline; the comment records why the loop's default executor is never used and that a timed-out worker cannot be cancelled.
- `api/apps/service_errors.py`: one table from `Kind` to envelope code and HTTP status (INVALID 400, CONFLICT 409, RATE_LIMITED 429, UNAVAILABLE 503, TIMEOUT 504, BAD_GATEWAY 502, PAYLOAD_TOO_LARGE 413); NOT_FOUND is always `{"code":404,"message":"not found","data":null}`; `Retry-After` is whole seconds of at least 1 whenever `retry_after` is set (0.0 included); no mapping produces 401.
- `api/apps/handler_support.py`: `acting_scope` (strict 32-hex check, then `tenant_scope.resolve_scope` in the db executor), `forbid_unless`, `credentials_visible`.
- `api/apps/restful_apis/provider_api.py`: GET and PUT `/providers`, DELETE `/providers/{provider}`, GET `/providers/{provider}/models`, POST `/providers/{provider}/instances`, GET `/providers/{provider}/instances/{instance}`; request models carry `extra="forbid"`; keys are `SecretStr` until the service has used them; response models document the shapes for the OpenAPI export (regenerated, with the TypeScript types).
- Registry: six provider rows are `implemented: true` (`implemented: true` count 29 to 35, no provider row left `false`).
- Test fake provider: stack mode binds 0.0.0.0 on two ephemeral ports sharing one recorder (`Recorded.port` says which listener was hit), reachable by the app as `host.docker.internal`.
- Matrix: `World` gained `fake` and `provider_url`, `snapshot_providers()` (in `snapshot()` under `providers`), `resource_of(row)`, four `BUILDERS` entries and `NO_ID_CHECKS` for `GET` and `PUT /api/v1/providers`. Sweep: `sweep_provider_rows` exercises all six rows on success and error paths; the sentinel keys and every sealed envelope read from MySQL are registered with no allowed rows.

## Task Commits

| Task | Commit | Result |
|------|--------|--------|
| 1 Failing tests and stack-mode fake provider | `7deebb5` | red runs recorded below |
| (fix found in Task 2) secretbox padding | `8095c62` | regression test for lengths 0..69 |
| 2 Executors, error mapping, workspace resolution, blueprint | `de3921b` | unit, layering and enumeration green |
| 3 Registry flip, matrix builders, sweep exercisers | `60b32ae` | e2e green on the rebuilt stack |

## Verification (real output)

Red runs (before implementation):

- `uv run pytest test/unit_test/test_service_errors.py -q` -> `ERROR collecting ...` with `ImportError while importing test module` at `from api.apps.service_errors import ...` (`ModuleNotFoundError`); `test_handler_support.py` -> `ImportError: cannot import name 'handler_support' from 'api.apps'`.
- `uv run pytest -m e2e test/testcases/test_provider_flow.py -q -x` on the old stack -> `1 failed`: `AssertionError: {"code": 404, "message": "not found", "data": null}` at the first PUT (no provider route yet).

Green runs:

- `uv run pytest test/unit_test/test_service_errors.py test/unit_test/test_handler_support.py -q` -> `66 passed`.
- `uv run pytest test/unit_test scripts/ci/tests -m unit -q` -> `1707 passed, 1 skipped`.
- `uv run python scripts/gen_routes.py --check` and `uv run python scripts/export_openapi.py --check` -> exit 0. `GOTOOLCHAIN=local go test ./internal/common/ -count=1` -> `ok`.
- Stack rebuilt once: `PREFLIGHT_PORTS= PREFLIGHT_ALLOW_LOW_MAP_COUNT=1 make up` then `scripts/wait_stack.sh` -> `stack ready` (app, es01, minio, mysql, mailpit, redis healthy; init exited).
- `LIVE_BASE_URL=http://127.0.0.1:8088 uv run pytest -m e2e test/testcases/test_provider_flow.py -q` -> `11 passed in 6.01s`.
- `uv run pytest -m e2e test/testcases/test_cross_tenant_matrix.py test/testcases/test_response_leaks.py test/testcases/test_route_enumeration.py -q` -> `85 passed, 12 deselected`. Final combined run with the flow: `96 passed, 12 deselected in 15.40s`.
- Wider live run (`test/testcases` and `test/integration`, `(e2e or integration) and not serial`, SPA browser file excluded, the two log-masking tests deselected): `483 passed, 30 deselected in 244.03s`.
- `uv run ruff check api common test/testcases test/helpers` and `uv run ruff check --select S,ASYNC,FIX001,FIX002 --ignore S603,S607 .` -> `All checks passed!`. `check_secrets` -> `secrets OK`.

Not run: mutation checks against the stack (that would need a second image build); `credentials_visible` and the permission check are covered by unit tests that name the token-inherits-owner case, and by the flow and matrix assertions that the owner's list holds the credential keys while a member's and a token's do not.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Sealed envelopes with base64 padding could never be opened (plan 03-01 module)**
- **Found during:** Task 2, driving the handlers against the real database (`POST ... instances` answered `key_unreadable` right after a successful PUT).
- **Issue:** `secretbox.seal` kept the `=` padding but `open_` accepts only the documented alphabet `[A-Za-z0-9_-]`. An envelope opens only when `28 + len(key)` bytes need no padding, that is when `len(key) % 3 == 2`. All earlier tests used keys of such lengths by chance; any other key (for example a real OpenRouter key) would have been stored and never readable.
- **Fix:** `seal` strips the padding (`open_` already restores it); regression test for every length 0..69.
- **Files modified:** `common/security/secretbox.py`, `test/unit_test/test_secretbox.py`. **Commit:** `8095c62`.

**2. [Rule 1 - Bug] Settings read inside the worker thread**
- The first handler version evaluated `current_app` inside the executor lambda (`RuntimeError: Not within an app context`, a 500). Settings are now read on the loop and passed in. Found by the in-process run against the real database before the image build; no test shipped broken.

**3. [Rule 3 - Blocking] Registry row tightened and pinned tests updated**
- `GET /providers/{provider}/instances/{instance}` went from `auth: api` to `auth: jwt` (tighten-only is allowed by the generator). The matrix expects 404 for an API token on an `api` row and 401 on a `jwt` row, and the instance detail's permission (`update_llm_keys`) excludes every token subject, so `jwt` is the consistent contract. Updated `test_route_policy.py` (the pinned "unimplemented" test is now two tests) and `test_probes.py` (`/api/v1/providers` is now served by the provider blueprint). Not in the plan's file list.

**4. [Rule 3 - Blocking] Matrix builders pass only the accepted smuggled field**
- The matrix smuggles `user_id`, `id` and `owner_id` into request bodies. The provider models refuse unknown fields (400, by design), which differs from the 404 baseline. The provider builders therefore forward only `tenant_id`; the 400 for unknown fields is asserted separately in the flow test and in the sweep ("unknown field" row).

**5. [Rule 3 - Blocking] `make up` preflight and ports**
- The preflight refuses to start while the ports are in use, including by this checkout's own running stack. Used the script's documented `PREFLIGHT_PORTS=` (empty) override together with `PREFLIGHT_ALLOW_LOW_MAP_COUNT=1`, after confirming with `docker ps` that the listeners are the stack's own containers. No file changed.

### Other notes

- Extra tests beyond the plan's list: `test/unit_test/test_handler_support.py` (executors, `run_blocking`, `credentials_visible`, `forbid_unless`, `acting_scope` parts that need no database).
- Added reasons `operation_timeout` and `instance_exists` to `api/utils/reasons.py`.
- A test bug (an empty `models` list silently replaced by the default through `or`) was fixed in the flow test after its first run on the rebuilt stack (10 of 11 passed, the 11th failed only for that reason).
- The plan text "Do not commit (the orchestrator commits)" was overridden by the sequential-executor instruction; each task was committed.

## Deferred Issues (pre-existing, not touched by this plan)

See `.planning/phases/03-models-knowledge-bases-and-upload/deferred-items.md`: `check_no_sleep` (`test_llm_shared.py:163`), `check_placeholders` (five `raise NotImplementedError` in `rag/llm`), `ruff` E501 in `test/unit_test/test_settings.py:258`, and two tests in `test_log_token_masking.py` that no longer find the Python access-log lines because the logger truncates long paths. `scripts/ci/run_all.py` reports 5/7 gates because of the first two.

## Notes for the next plans

- **Pattern for routes 03-13, 03-14, 03-16..18:** `scope = await acting_scope(tenant_id)` (None means `not_found_response()`), `forbid_unless(scope, area, action)`, `await run_blocking(<executor>, fn, ..., timeout=...)`, `except ServiceError as exc: return service_error_response(exc)`, and `include_credentials=credentials_visible(scope)` for any provider view. Read `current_app.extensions["ragflow_settings"]` on the loop before entering a worker.
- Id-addressed routes derive the workspace from the resource and use `tenant_scope.scope_for_tenant` (also inside `run_blocking(DB_EXECUTOR, ...)`).
- Every request model should carry `ConfigDict(extra="forbid")`; give the matrix builder `extra_fields={"tenant_id"}` (or the route's accepted fields) so the smuggled-body cases compare like with like.
- The provider-test limit is 10 per 300 s per workspace. The sweep world uses 6 on A and the matrix world 1 on A and 1 on B; anything that adds more saves to those worlds must use its own account.
- Retry-After: `service_error_response` sets it whenever `retry_after is not None`, including `0.0` (sent as `1`).
- The `Models` page can read the instance detail (`last4`, `base_url`, `api_version`) for the "Change key" and "Change address" dialogs; both end in the same `PUT /providers` and the dialog must resend the stored address with a new key.
- A keyed provider's address change without a key is `400 key_required_for_new_address`; keyless Ollama moves freely.
- Stack state at the end: rebuilt once with this plan's code, healthy, web port 8088; free disk 20 GB.

## Known Stubs

None.

## Threat Flags

None. T-03-12-01 to -08 are covered: API token on PUT, DELETE, POST and instance detail gets the gate's 401 (flow and matrix); a member gets 403 and an API-token list carries no `last4`, `base_url` or `api_version` (flow, matrix, unit); one 404 body for a foreign workspace, an unknown or unconfigured provider (matrix, flow); sentinel and sealed keys absent from every sweep response and header; a provider 401 is a 400 `provider_refused` with the session still valid (flow); the provider executor and the 50 s cap; `extra="forbid"` refusals in flow and sweep; the fake provider listens only for the lifetime of a test.

## Self-Check: PASSED

- Files present: api/utils/blocking.py, api/apps/service_errors.py, api/apps/handler_support.py, api/apps/restful_apis/provider_api.py, test/unit_test/test_service_errors.py, test/unit_test/test_handler_support.py, test/testcases/test_provider_flow.py.
- Commits present: 7deebb5, 8095c62, de3921b, 60b32ae.
