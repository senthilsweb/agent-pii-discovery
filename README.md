# agent-pii-discovery

A sensitive-data (PII) discovery agent built to learn **live evaluation** —
evals that run on production traces, not just in CI.

Upload a document → it is scanned two ways — a deterministic path (Microsoft
Presidio + regex) and a GenAI path with a **switchable model** (Claude,
GPT-class, DeepSeek) — and both outputs normalize into one canonical entity
schema, so results are directly comparable across models. Every run is traced;
LLM-as-judge evaluators score real traffic after the fact, with drift and cost
monitors on top.

| | |
|---|---|
| Runtime | **Claude Managed Agents** — Anthropic hosts the agent loop + per-session sandbox; the agent config is version-controlled YAML in `agent/` |
| Orchestration | Coordinator (`pii-orchestrator`) + subagents: `doc-extractor`, `pii-genai-scanner` (one thread per compared model), `report-assembler` |
| Detection | `PII_ENGINE` = `presidio` \| `presidio_genai` \| `genai_only`; exactly **one generative step** in the pipeline |
| Storage | Uploads in S3, hive-partitioned `user_login=<login>/dt=<date>/<sha256>/`; results in DuckDB (ANSI-portable schema → Postgres/MySQL in production) |
| Observability | Session events → OpenInference/OTel spans → **Arize AX**; online eval tasks (judge rubric R1–R6) + drift/cost monitors |
| Evals | Four-layer harness: unit tests → offline agent evals on a char-span-labeled corpus → judge calibration → live regression evals. Rubrics written before the code: [`evals/rubrics.md`](evals/rubrics.md) |

## Status

**Phase 0 — spec.** Nothing runs yet. The PRD, openspec change folder, agent
control-plane YAML, and eval rubrics are in place; implementation follows the
phase gates in [`openspec/changes/add-pii-discovery-agent/tasks.md`](openspec/changes/add-pii-discovery-agent/tasks.md).

## Read in this order

1. [`docs/prd.md`](docs/prd.md) — requirements, architecture, KPIs (v0.2)
2. [`openspec/changes/add-pii-discovery-agent/`](openspec/changes/add-pii-discovery-agent/) — proposal → design → spec → tasks
3. [`evals/rubrics.md`](evals/rubrics.md) — what "correct" means, defined first
4. [`AGENTS.md`](AGENTS.md) — repo conventions and layout

## Privacy note

This repo is public and the subject matter is PII. Real uploads, operational
databases, and any export containing document excerpts are **gitignored**;
committed fixtures are synthetic; the published parquet export carries counts
and types, never excerpt text; production traces carry no document text
(`TELEMETRY_RECORD_IO=false`).
