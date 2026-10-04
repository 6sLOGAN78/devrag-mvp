# Phase 1: Reconciliation, Guardrails and Dual-Stack Foundation - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-10-05
**Phase:** 1-Reconciliation, Guardrails and Dual-Stack Foundation
**Mode:** `--auto` (no questions were put to the user in this step; the recommended option was taken for every question)
**Areas discussed:** Scope, Ports and routing, Schema ownership, API contract, Stack versions, Naming and layout, Guardrails, Host budget and tests

---

## Scope (asked interactively during /gsd-new-project, not in this step)

| Question | Options | Selected |
|----------|---------|----------|
| Go parity | Go for its own routes only / Full dual implementation / Python only | Go for its own routes only |
| `docs/apis.md` billing content | Ignore it / Build billing too / Defer to v2 | Build billing too |
| Doc stores in v1 | ES + Infinity / Elasticsearch only / All listed engines | ES + Infinity |

**User's choice:** as in the Selected column. These are the only user-confirmed decisions.

---

## Ports and routing

| Option | Description | Selected |
|--------|-------------|----------|
| `18-deployment` port map (Python 9380, Go 9384) | Only physically possible variant; three files agree | ✓ |
| Both on 9380 | Overview diagrams; cannot both bind | |
| Go 9380 / Python 9381 | `apis.md` | |

[auto] Ports — Q: "Which port scheme?" → Selected: "`18-deployment` map" (recommended default)

| Option | Description | Selected |
|--------|-------------|----------|
| Derive route table from endpoint catalogue, Python catch-all | Docs win over reference | ✓ |
| Reference hybrid table | Sends chat completions to Go | |
| Python-only proxy mode | Reference default; contradicts dual-stack docs | |

[auto] Route ownership — Q: "Where does the proxy table come from?" → Selected: "endpoint catalogue" (recommended default)

| Option | Description | Selected |
|--------|-------------|----------|
| No Go-to-Python proxying | Servers never call each other | ✓ |
| Go reverse-proxies unmatched paths | STACK researcher's proposal | |

[auto] Go→Python — Q: "May Go forward to Python?" → Selected: "No" (recommended default; researchers disagreed)

## Schema ownership

| Option | Description | Selected |
|--------|-------------|----------|
| Peewee owns DDL/migrations; GORM verifies only | One writer | ✓ |
| GORM AutoMigrate | Go owns schema | |
| `docker/init.sql` | Static SQL | |

[auto] Schema — Q: "Who creates the schema?" → Selected: "Peewee, one-shot init" (recommended default)

## API contract

| Option | Description | Selected |
|--------|-------------|----------|
| `{code, message, data}` | Docs split evenly; reference breaks the tie | ✓ |
| `{retcode, retmsg, data}` | `04-api/api-overview.md` | |

[auto] Envelope — Q: "Which envelope keys?" → Selected: "`code/message/data`" (recommended default). **Note:** this goes against the doc that nominally owns the API contract; flagged for user review.

## Stack versions

[auto] Python — Q: "3.10 (docs) or 3.13 (reference)?" → Selected: "3.13" (recommended default; deviation from docs, flagged)
[auto] MySQL — Q: "8.0.40 (docs, EOL) or 8.4 LTS?" → Selected: "parameterised, default 8.0.40" (recommended default)
[auto] Redis role — Q: "Redis 7 or Valkey 8?" → Selected: "Valkey 8" (recommended default)
[auto] Frontend — Q: "Vite/UmiJS, shadcn/AntD?" → Selected: "Vite + shadcn only" (recommended default)

## Naming and layout

[auto] Identifiers — Q: "Keep `ragflow_*` names or rename to `devrag_*`?" → Selected: "Keep as documented, one constant each" (recommended default)
[auto] Topology — Q: "Single app container or split?" → Selected: "Single app container; executor split in Phase 4" (recommended default)

## Guardrails

[auto] Pickle — Q: "Docs' numpy whitelist or no pickle across trust boundaries?" → Selected: "No pickle" (recommended default; deliberate deviation from docs for security)
[auto] Fakes — Q: "How to stop placeholder implementations?" → Selected: "CI gate + BLOCKERS.md convention" (recommended default)

## Host budget and tests

[auto] Model source — Q: "Ollama in compose or user-supplied key?" → Selected: "Ollama, small models" (recommended default)
[auto] Test timing — Q: "Fixed waits or readiness polling?" → Selected: "Readiness polling" (recommended default)

---

## Claude's Discretion

Migration tooling, CI runner, lint/format tools, logging configuration, preflight script internals, SPA shell design.

## Deferred Ideas

MySQL 8.4 upgrade; `devrag_*` renaming; NATS (ING-20, DEPLOY-09); splitting Phase 8; `[P]`-flagged thin-spec features.
