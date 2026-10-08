# Phase 3: Models, Knowledge Bases and Upload - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-10-08
**Phase:** 3-Models, Knowledge Bases and Upload
**Areas discussed:** Real model source, Who manages models and datasets, Upload rules, Provider coverage and settings page

---

## Real model source

| Question | Options presented | Selected |
|----------|-------------------|----------|
| Where should real calls go? | My own API key (recommended) / Local Ollama / Both | My own API key |
| Which service is the key for? | OpenAI / Another OpenAI-compatible service / Not using a key | Another OpenAI-compatible service |
| What should live tests do with no key? | Fail the local gate, not run on CI (recommended) / Also run on GitHub CI | Fail the local gate, not run on CI |
| Spend per gate run? | Keep it tiny (recommended) / No particular limit | Keep it tiny |
| Does the service offer embeddings? | Yes, same key / Chat only / Two keys / Not sure | Yes, both on the same key |
| Which service? | OpenRouter / DeepSeek, Groq, Together or similar / Self-hosted / Will say later | OpenRouter |

**Notes:** Research must confirm OpenRouter embeddings on the same key; if not, return to the user.

## Who manages models and datasets

| Question | Options presented | Selected |
|----------|-------------------|----------|
| Who manages provider keys and defaults? | Owner and admins (recommended) / Owner only | Owner and admins |
| Default dataset visibility? | Only the creator (recommended) / The whole workspace | Only the creator |
| Who edits, deletes and uploads in a team dataset? | Members upload; creator, owner and admins edit and delete (recommended) / Any member everything / Read-only for others | Members upload; creator, owner and admins edit and delete |
| Dataset delete confirmation? | Dialog naming dataset and document count (recommended) / Type the name | Dialog naming dataset and document count |

## Upload rules

| Question | Options presented | Selected |
|----------|-------------------|----------|
| Largest single file? | 100 MB configurable (recommended) / 1 GB / 25 MB | 100 MB, configurable |
| Accepted file types now? | All documented types (recommended) / Only types Phase 4 parses first | All documented types |
| Storage limit per workspace? | Configurable limits, generous defaults (recommended) / Hard byte quota now / None | Configurable limits, generous defaults |
| Same file name in a dataset? | Keep both, auto-rename (recommended) / Reject | Keep both, auto-rename |

## Provider coverage and settings page

| Question | Options presented | Selected |
|----------|-------------------|----------|
| Providers offered now? | Required set plus OpenRouter and OpenAI-compatible (recommended) / Only OpenRouter and compatible / Every documented provider | Required set plus yours |
| Check a key when saving? | Test before saving (recommended) / Save with separate Test button | Test before saving |
| What is shown of a saved key? | Never shown again (recommended) / Reveal on demand | Never shown again |
| How are defaults chosen? | Explicit choice, required before first dataset (recommended) / Auto-pick first model | Explicit choice |

## Claude's Discretion

Encryption scheme for stored keys, default limit values and the exact extension list, index mapping details, page layouts (UI contract), choice of cheap test models.

## Deferred Ideas

Live Ollama proof and remaining providers; per-workspace byte quota; live provider tests on GitHub CI; trusted-proxy client address (B-17).
