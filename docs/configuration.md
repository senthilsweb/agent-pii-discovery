# Configuration

At the end you will know every environment variable the system reads, which
are required, and where secrets live.

Configuration is entirely environment-driven — no config file, no hard-coded
defaults for anything that selects a model or an engine. Secrets live in the
environment (locally via `.env`, never committed; `.env.example` is the
committed twin documenting the shape). This table is the contract the
Phase 1–3 components implement; the columns state which phase reads each
variable.

## Engine and models

| Variable | Required | Meaning |
|---|---|---|
| `PII_ENGINE` | yes | `presidio` \| `presidio_genai` \| `genai_only`. No default — unset fails at startup. Reserved names fail fast. |
| `MODEL_PII_EXTRACTOR` | yes for GenAI paths | Model id for the one generative step. Falls back to `MODEL`, then startup error. |
| `MODEL` | fallback | Generic model fallback for any role without a specific override. |
| `PII_SYSTEM_PROMPT` | no | Inline override of the detection prompt (highest env precedence). |
| `PII_SYSTEM_PROMPT_FILE` | no | Path override of the detection prompt. Default: `agent/skills/detection_prompt.md`. |
| `PII_DETECTION_CONCURRENCY` | no | Parallel chunk extractions per scanner (default 5). |

## Managed Agents control plane

| Variable | Required | Meaning |
|---|---|---|
| `ANTHROPIC_API_KEY` | yes | Session creation and orchestrator model. |
| `PII_AGENT_ID` / `PII_AGENT_VERSION` | yes | The applied `pii-orchestrator` agent, pinned per run. |
| `PII_ENVIRONMENT_ID` | yes | The applied sandbox environment. |

## Storage

| Variable | Required | Meaning |
|---|---|---|
| `OBJECT_STORE_BUCKET` | yes | S3 bucket. Unset = uploads are a no-op (dev). Currently the shared `ai-agents` bucket — this project owns the `uploads/`/`results/`/`exports/` prefixes only ([ADR 0003](https://github.com/senthilsweb/agent-pii-discovery/blob/main/openspec/adr/0003-minio-object-storage.md)). |
| `OBJECT_STORE_REGION` | no | Default `us-east-1`. |
| `OBJECT_STORE_ACCESS_KEY_ID` / `OBJECT_STORE_SECRET_ACCESS_KEY` | yes | Held by the client only; never enter the sandbox. |
| `OBJECT_STORE_ENDPOINT` | no | S3-compatible endpoint. Self-hosted MinIO in this deployment (ADR 0003) — AWS S3 needs no override. |
| `OBJECT_STORE_FORCE_PATH_STYLE` | no | `true` for MinIO and most self-hosted S3-compatible stores — they reject virtual-hosted-style requests. Leave unset for AWS S3. |
| `PII_DB_PATH` | no | DuckDB file path (default `data/pii.duckdb`). Production swaps this for a Postgres/MySQL DSN (data source name — the connection string; see [Glossary](glossary.md)) behind the same seam. |

## Observability

| Variable | Required | Meaning |
|---|---|---|
| `ARIZE_SPACE_ID` / `ARIZE_API_KEY` | yes for live eval | Arize AX ingest and the judge-verdict push. Missing = forwarder/push degrade to one logged warning, scans unaffected. |
| `ARIZE_PROJECT_NAME` | no | Default `agent-pii-discovery`. Must match the project traces land in. |
| `OTEL_EXPORTER_OTLP_ENDPOINT` / `OTEL_EXPORTER_OTLP_HEADERS` | no | Generic OTLP (OpenTelemetry Protocol) fan-out target. |
| `PHOENIX_COLLECTOR_ENDPOINT` | no | Dev-only local Phoenix second export. |
| `TELEMETRY_RECORD_IO` | no | `false` in production — prompts/completions (document text) never leave for the trace backend. |
| `MODEL_JUDGE` | yes for LLM judges | Judge model for R2/R3/R5/R6, falls back to `MODEL`. Must differ from the extractor under test — see [Evals](evals.md). |
| `PII_JUDGE_SAMPLE_RATE` | no | Default `0.25` (PRD §10.4). Fraction of `processed` scans that get the four LLM judges; `1.0` forces every scan, `0.0` runs only the free R1/R4 code checks. Sampling is deterministic per `scan_id`, not random per run. |

!!! warning "Arize AX requires `model_id`"
    Spans sent to `otlp.arize.com` must carry a `model_id` resource attribute
    — the collector returns 500 without it. The forwarder sets
    `Resource({service.name, model_id})` unconditionally; do not remove it.
    Recorded in [ADR 0001](https://github.com/senthilsweb/agent-pii-discovery/blob/main/openspec/adr/0001-claude-managed-agents-and-arize.md).

## Cache semantics

There is no cache TTL (time to live — a fixed expiry duration; see
[Glossary](glossary.md)) to configure. The cache key is
`(checksum, pipeline_version)`, and `pipeline_version` hashes the engine, the
extraction model, the detection prompt, and the taxonomy version — changing
any of them *is* the invalidation.

Next: [Evals](evals.md)
