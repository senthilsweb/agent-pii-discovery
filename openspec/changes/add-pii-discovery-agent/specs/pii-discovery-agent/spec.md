# Spec — pii-discovery-agent

RFC-2119 keywords (SHALL, SHALL NOT, SHOULD, MAY) are normative.

## Requirement: Content-addressed intake
The system SHALL compute a SHA-256 checksum over the normalized file bytes at
upload time; identity SHALL be content-based, never filename-based.

## Requirement: Upload persistence
The system SHALL store every upload in S3 under
`uploads/user_login=<login>/dt=<YYYY-MM-DD>/<sha256>/<original-filename>`
before any scan begins, idempotently by checksum.

## Requirement: Cache short-circuit
The system SHALL key its result cache on `(checksum, pipeline_version)` where
`pipeline_version` derives from engine, model, prompt, and taxonomy version. A
cache hit SHALL return the stored result without creating a session and SHALL
still emit a `cache_hit` trace.

## Requirement: Engine selection
The system SHALL read `PII_ENGINE` (`presidio`, `presidio_genai`, `genai_only`)
with no default; an unset or invalid value SHALL fail at startup.

## Requirement: Single generative step
Exactly one pipeline step SHALL call a generative model: typed PII extraction
via structured output. Counts, scores, cache decisions, normalization, and
compliance verdicts SHALL be computed in deterministic code. The LLM SHALL NOT
emit any number that reaches the result.

## Requirement: Model resolution
Generative model ids SHALL resolve `MODEL_PII_EXTRACTOR → MODEL → startup
error`, with no hard-coded default. The extraction tool SHALL be
provider-agnostic (Claude, GPT-class, DeepSeek) behind one output schema.

## Requirement: Canonical normalization
All findings from all engines and models SHALL normalize into the 36-type
canonical taxonomy via the alias table. Unrecognized labels SHALL degrade to
`UNKNOWN` and SHALL NOT throw. Configuration SHALL NOT be able to introduce new
canonical types.

## Requirement: Finding attribution
Every finding SHALL carry `source_engine`, and GenAI findings SHALL carry
`source_model`, so cross-model comparison requires no re-scan.

## Requirement: Grounded excerpts
Every `value_excerpt` SHALL be a whitespace/case-normalized substring of the
source chunk it cites. Findings violating this SHALL fail evaluation (HARD).

## Requirement: Managed Agents lifecycle
The agent SHALL be created once from version-controlled YAML and referenced by
pinned `{id, version}` per session. The system SHALL NOT create agents in the
request path. The client SHALL open the event stream before sending the
kickoff and SHALL treat only `session.status_terminated` or idle with a
terminal stop reason as run completion.

## Requirement: Sandbox containment
Sessions SHALL run in an environment with `limited` (deny-by-default)
networking. Cloud credentials SHALL NOT enter the sandbox; S3 and database
access SHALL occur via host-side custom tools or vault egress substitution.

## Requirement: Result persistence
The system SHALL persist scans and findings to the operational database using
ANSI-portable DDL, with all database access behind a single driver seam so the
engine can move from DuckDB to Postgres/MySQL without schema change.

## Requirement: Trace export
The client SHALL forward every session's events to Arize AX as OpenInference
spans, including token usage from `span.model_request_end`, and SHALL set the
`model_id` resource attribute. In production, spans SHALL NOT contain document
text (`TELEMETRY_RECORD_IO=false`).

## Requirement: Decoupled live evaluation
Evaluation SHALL run only on completed traces, outside the agent runtime, via
Arize online-eval tasks. Evaluation SHALL add zero latency to the request path
and SHALL be invisible to the agent.

## Requirement: Judge governance
LLM-as-judge evaluators SHALL use a model/configuration distinct from the
extractor under test, and SHALL NOT run against live traffic until calibration
shows ≥90% agreement with human labels on the calibration set.

## Requirement: Flagging
Any HARD rubric failure on a live trace SHALL label the trace `flagged`, route
it to the review queue, and be written back to the `eval_scores` table.

## Requirement: Promotion gates
CI SHALL block promotion to `implemented` unless L1 and L2 are green, and to
`verified` unless L2 metric floors and L3 calibration pass. Telemetry or eval
infrastructure failure SHALL NOT fail a production scan.

## Requirement: Public-repo data hygiene
Real uploads, operational databases, and any export containing excerpts SHALL
be gitignored. Committed fixtures SHALL be synthetic. Published parquet
exports SHALL contain no excerpt text.
