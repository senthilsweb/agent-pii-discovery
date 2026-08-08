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
| `OBJECT_STORE_BUCKET` | yes | S3 bucket. Unset = uploads are a no-op (dev). |
| `OBJECT_STORE_REGION` | no | Default `us-east-1`. |
| `OBJECT_STORE_ACCESS_KEY_ID` / `OBJECT_STORE_SECRET_ACCESS_KEY` | yes | Held by the client only; never enter the sandbox. |
| `OBJECT_STORE_ENDPOINT` | no | MinIO/localstack endpoint for local dev. |
| `PII_DB_PATH` | no | DuckDB file path (default `data/pii.duckdb`). Production swaps this for a Postgres/MySQL DSN behind the same seam. |

## Observability

| Variable | Required | Meaning |
|---|---|---|
| `ARIZE_SPACE_ID` / `ARIZE_API_KEY` | yes for live eval | Arize AX ingest. Missing = forwarder degrades to one logged warning, scans unaffected. |
| `OTEL_EXPORTER_OTLP_ENDPOINT` / `OTEL_EXPORTER_OTLP_HEADERS` | no | Generic OTLP fan-out target. |
| `PHOENIX_COLLECTOR_ENDPOINT` | no | Dev-only local Phoenix second export. |
| `TELEMETRY_RECORD_IO` | no | `false` in production — prompts/completions (document text) never leave for the trace backend. |

!!! warning "Arize AX requires `model_id`"
    Spans sent to `otlp.arize.com` must carry a `model_id` resource attribute
    — the collector returns 500 without it. The forwarder sets
    `Resource({service.name, model_id})` unconditionally; do not remove it.
    Recorded in [ADR 0001](https://github.com/senthilsweb/agent-pii-discovery/blob/main/openspec/adr/0001-claude-managed-agents-and-arize.md).

## Cache semantics

There is no cache TTL to configure. The cache key is
`(checksum, pipeline_version)`, and `pipeline_version` hashes the engine, the
extraction model, the detection prompt, and the taxonomy version — changing
any of them *is* the invalidation.

Next: [Evals](evals.md)
