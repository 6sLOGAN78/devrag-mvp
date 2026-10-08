---
phase: 03-models-knowledge-bases-and-upload
plan: 02
subsystem: security
tags: [redaction, logging, nginx, ssrf, url-guard, provider-keys]

requires:
  - phase: 03-models-knowledge-bases-and-upload
    provides: "03-01 common/net package marker, llm.allow_private_base_urls setting"
  - phase: 02-accounts-and-tenancy
    provides: shared log redaction vectors, Python/Go redactors, Nginx loggable_uri map
provides:
  - provider key shapes (sk-or-v1-..., sk-...) masked in Python logs, Go logs and the Nginx access log from one shared vector file
  - common/net/url_guard.py (validate_base_url, assert_unchanged, ValidatedUrl, UnsafeBaseUrl, INTERNAL_SERVICE_HOSTS)
affects: [03-03, provider API, provider test endpoint, model drivers, live tests]

tech-stack:
  added: []
  patterns:
    - "Shape-based redaction stage after key/value and userinfo stages; bounded in Python, RE2 in Go, PCRE map entry in Nginx"
    - "URL guard judges resolved addresses with an injected resolver; error messages carry a fixed reason only"

key-files:
  created:
    - common/net/url_guard.py
    - test/unit_test/test_url_guard.py
  modified:
    - test/fixtures/log_redaction_vectors.json
    - test/unit_test/test_log_redaction.py
    - test/unit_test/test_nginx_log_format.py
    - common/log_utils.py
    - internal/common/logger.go
    - internal/common/logger_test.go
    - docker/nginx/nginx.conf

key-decisions:
  - "Nginx entry keeps the path before a key shape and drops the key and everything after it (so a second credential later in the URI cannot survive); it is the first map entry because nginx takes the first matching regex"
  - "No word boundary before sk-: a key glued to other text (key_sk-...) is still masked, at the cost of masking a hyphenated slug such as task-force-leader-name-longer-than-20 chars"
  - "Python quantifiers are {16,512} / {20,512} as the plan says; a key longer than 512 characters would keep its tail, accepted as unrealistic"
  - "A host whose last label is all digits or 0x-hex is parsed as a legacy IPv4 spelling and rejected as host if it does not parse, never sent to DNS"
  - "Metadata addresses outside link-local (AWS fd00:ec2::254, Alibaba 100.100.100.200, Oracle 192.0.0.192) are always denied; unspecified, multicast and reserved ranges are always denied; IPv4-compatible, NAT64 and 6to4 IPv6 forms are judged by the embedded IPv4 address"
  - "Residual DNS-rebinding window between assert_unchanged and the SDK connect is accepted (T-03-02-02); to be recorded in DECISIONS by plan 03-28"

patterns-established:
  - "Shared vectors may carry an optional uri field; the Nginx test evaluates the map entries in file order against it"

requirements-completed: []

duration: ~35min
completed: 2026-10-08
---

# Phase 3 Plan 02: Key-shape redaction and outbound base-URL guard Summary

**Provider key shapes are masked identically in Python, Go and Nginx logs from one vector file, and `validate_base_url` refuses unsafe provider addresses (all IP spellings judged after resolution) with reasons that never echo the URL.**

## Accomplishments

- Red run recorded for Task 1: Python `8 failed, 51 passed` (sdk_message_openrouter, sdk_message_openai, key_in_url_path, key_in_url_path_openai, key_in_json_value, key_after_bearer_text, plus the two Nginx uri cases); Go `TestSharedRedactionVectors` failed on the same six ids.
- Vector file grew from 24 to 30 entries (6 masking, 2 keep). The original 24 pass unchanged.
- Python `redact_text` has a third, bounded stage; Go `RedactString` applies `keyShapePattern` first; the Nginx `$loggable_uri` map has a first entry for key shapes. The hostile 100 KB timing test passes with three new key-shape lines.
- Nginx: `nginx -t` succeeded in the `nginx:1.25-alpine` image, and a live container returning `$loggable_uri` produced `/v1/x/sk-***`, `/proxy/sk-***`, `/api/v1/task-force-leader-name` (untouched) and `/api/v1/system/tokens/***` (existing entry still works).
- Task 3 red run: `ModuleNotFoundError: No module named 'common.net.url_guard'`. After implementation 133 tests pass in `test_url_guard.py`, covering every spelling in the plan (decimal, hex, hex-dotted, octal, short form, IPv4-mapped, IPv4-compatible, NAT64, 6to4, AWS IPv6 metadata), userinfo, fragment, scheme, internal service names (case-insensitive, trailing dot), caller deny hosts, multi-record hosts, unresolvable hosts, private ranges both ways, no-DNS for IP literals and localhost, messages free of the URL, and `assert_unchanged` rebinding cases.

## Verification (real output)

- `uv run pytest test/unit_test/test_log_redaction.py test/unit_test/test_nginx_log_format.py test/unit_test/test_url_guard.py test/unit_test/test_request_log_template.py test/unit_test/test_request_log_truncation.py test/unit_test/test_layering.py -q` -> `211 passed`
- `GOTOOLCHAIN=local go test ./internal/common/ -run 'Sensitive|Masked|Redact|Logger|Structured|JSONTagged|Hostile|Truncate' -count=1` -> `ok devrag/internal/common`
- `uv run ruff check common/net/url_guard.py test/unit_test/test_url_guard.py` -> `All checks passed!`
- `uv run python scripts/ci/check_secrets.py` -> `secrets OK`
- `uv run pytest -m unit --collect-only -q test/unit_test/test_url_guard.py` -> `133 tests collected`
- `grep import requests|httpx|urlopen common/net/url_guard.py` -> no output

## Task Commits

1. Task 1 (red vectors and tests): `eafb976`
2. Task 2 (redaction in three places): `1d7482e`
3. Task 3 red tests: `cdbd528`
4. Task 3 implementation: `2ddc07d`

## Deviations from Plan

- **[Rule 1 - plan wording] Nginx replacement.** The plan says to map the whole URI to the placeholder used by the `ragflow-` entry. That entry keeps the text before and after the token. A before/after form would leave a second key in the same URI, so the new entry keeps the prefix and drops everything from the key onward (`${before_key}sk-***`). Equivalent safety, strictly more complete.
- **[Rule 2] Extra denials.** Beyond the plan: always deny unspecified, multicast and reserved addresses, extra cloud metadata addresses, and IPv6 forms embedding IPv4; reject control characters, whitespace, backslashes and non-ASCII hosts; reject numeric-looking hosts that do not parse as IPv4.
- **Acceptance wording.** `grep -n "sk-or-v1"` returns one hit in `common/log_utils.py` and two in `logger.go` (comment and pattern); in `nginx.conf` the hit is the comment because the rule spells the alternation as `sk-(?:or-v1-...`. Behaviour is verified by tests and the live container instead.
- The default resolver cannot enforce the planned 3 second guard without a thread (`getaddrinfo` has no timeout). It is documented in the module docstring that callers run it in a bounded executor.
- SEC-02 and LLM-16 are not marked complete: this plan delivers log redaction and the URL guard; masking in API responses and encrypted storage arrive with the provider API plans.

## Known Stubs

None.

## Threat Flags

None beyond the plan's threat model (T-03-02-01, -03, -04 mitigated and tested; T-03-02-02 accepted as documented).

## Notes for next plans

- Call `validate_base_url(url, allow_private=settings.llm.allow_private_base_urls, deny_hosts=..., resolve=...)` at provider save, and `assert_unchanged` immediately before each outbound call. Run it inside the bounded executor (the default resolver blocks). Map `UnsafeBaseUrl.reason` to a validation error; never echo the submitted URL.
- In dev the compose sets `allow_private_base_urls` true, so loopback and private targets pass there; link-local, metadata and the project's service hostnames stay denied everywhere.
- Plan 03-28 should record the accepted rebinding window and the 512-character bound in DECISIONS.

## Self-Check: PASSED

Files verified present (`common/net/url_guard.py`, `test/unit_test/test_url_guard.py`) and commits `eafb976`, `1d7482e`, `cdbd528`, `2ddc07d` exist in `git log`.
