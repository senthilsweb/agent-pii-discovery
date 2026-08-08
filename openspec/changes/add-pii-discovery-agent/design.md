# Design — add-pii-discovery-agent

Condensed from `docs/prd.md` v0.2 (the PRD is the source of truth; this file
records the decisions and their reasons).

## D1. Runtime — Claude Managed Agents

Agent = persisted, versioned config created **once** from the YAML in `agent/`
via the `ant` CLI; every run is a session pinning `{id, version}`. The client
opens the SSE event stream before sending the kickoff and breaks on
`session.status_terminated` or terminal idle. Sandbox environment uses
`limited` networking (deny-by-default egress, `allow_package_managers: true`)
because the uploaded document is untrusted input.

**Correction captured from PRD v0.1:** Managed Agents does not export OTel
natively. Tracing = session events + Console view. We therefore own a
forwarder (D5).

## D2. Orchestration — plan and route, never analyze

- `pii-orchestrator` (claude-opus-5, effort medium): sequences deterministic
  tools, fans out the GenAI scan, assembles the report from tool outputs. Legal
  trajectories are enumerated in the system prompt; trajectory correctness is a
  HARD offline eval.
- Subagents via `multiagent: {type: coordinator}`:
  - `doc-extractor` (haiku): drives extraction scripts; isolates raw untrusted
    text in its own thread.
  - `pii-genai-scanner` (switchable model): **one thread per model under
    comparison** so every trace is attributable to one model. N=1 degenerates
    to a single thread (job-matcher's N=1/N>1 rule).
  - `report-assembler` (haiku): renders prose from already-persisted JSON only.
- **One generative step**: `detect_pii_genai`, a tool wrapping a structured-
  output model call (`MODEL_PII_EXTRACTOR → MODEL → error`). The tool owns the
  provider call, so Claude/GPT/DeepSeek all route through the same schema.

  *(Amendment 2026-08-08, Phase 3 build)*: the GenAI leg runs **host-side on
  the direct path** (`pipeline/genai_detect.py`, per-chunk `messages.parse`
  with code-enforced grounding — ungrounded findings dropped, bad spans
  stripped). Rationale: a sandboxed model call needs a vault
  `environment_variable` API-key credential, and this org authenticates with
  short-lived OAuth profiles unfit for vaults. The scanner-thread-per-model
  session design remains v2, gated on provisioning a real API key. Practical
  consequence: `genai_only`/`presidio_genai` run on the direct path; the
  session path carries the deterministic leg.
- Deterministic sandbox scripts: `extract_text.py`, `chunk_text.py`,
  `presidio_scan.py`, `normalize_findings.py`, `assemble_result.py`.
- Host-side custom tools (credentials stay out of the sandbox): `s3_put`,
  `s3_get`, `cache_lookup`, `persist_result`, `create_run`.

## D3. Entity schema

The privacy-classifier canonical taxonomy is adopted wholesale: 36
`CANONICAL_ENTITY_TYPES`, alias YAML normalizing both Presidio labels and LLM
free text, unknown → `UNKNOWN` (never throw). Extensions over the monorepo
schema: per-finding `span {chunk_id, start, end}`, `normalized_value`, and
`source_model` for cross-model comparison. Compliance impact is a pure YAML
lookup over 7 regimes (GDPR, CCPA/CPRA, DPDP, PDPL-AR, HIPAA, LGPD, PIPEDA).

## D4. Storage

- S3 hive partitions: `uploads/user_login=<login>/dt=<date>/<sha256>/<name>`,
  mirrored `results/.../result.json`, dated `exports/*.parquet` (slim,
  no-excerpt — the repo is public).
- DuckDB `data/pii.duckdb` with ANSI-portable DDL (TEXT/BIGINT/DOUBLE/
  TIMESTAMP, app-generated ids, JSON-as-TEXT); all access through a `db.py`
  seam so the Postgres/MySQL move is a connection change.
- Cache key = `(checksum, pipeline_version)` where `pipeline_version` hashes
  engine + model + prompt + taxonomy version. Changing any of them *is* the
  invalidation — no TTL bookkeeping. Cache hits skip the session but still
  emit a lightweight `cache_hit` trace.

## D5. Observability + live eval — Arize AX

- Forwarder maps session events → OpenInference spans (AGENT/CHAIN/LLM/TOOL):
  `span.model_request_*` → LLM spans with token usage; `agent.tool_*` → TOOL
  spans; thread events → per-subagent traces. Runs in the client process,
  after the session, off the request path; failure degrades to one warning.
- **Arize AX requires the `model_id` resource attribute** (collector 500s
  without it — verified in the monorepo 2026-07-15). `TELEMETRY_RECORD_IO=false`
  in production: attributes carry counts/types/tokens/ids, never document text.
- Online eval tasks in Arize sample traces (judges 25%, code checks 100%) and
  score the 6-criterion rubric in `evals/rubrics.md`; HARD fails label the
  trace `flagged`; a sync job copies labels into the `eval_scores` table.
- Monitors: judge-score drift (PSI/KS vs frozen offline baseline), cost/doc,
  latency p95, flagged rate.

## D6. Eval harness (the critical spine)

L1 pytest unit tests (no network/model) → L2 offline agent evals against a
char-span-labeled synthetic corpus, asserting on artifacts not prose, with a
CI matrix over `PII_ENGINE` values → L3 judge calibration (≥90% agreement with
human labels before a judge runs live) → L4 live regression evals + monitors
in Arize. Gates: L1+L2 ⇒ `implemented`; floors + L3 ⇒ `verified`.

## D7. Security baseline

Structural injection defense (no channel from document text to any number),
sandbox egress deny-by-default, credentials host-side only, no document text in
telemetry, gitignored data, synthetic fixtures, private S3 with lifecycle
expiry. L2 injection fixtures + judge criterion R6 keep it verified.

## D8. Reuse (port, don't rebuild)

From `ai-agents`: taxonomy + alias + compliance YAMLs (verbatim), engine
switch, normalizer, telemetry env contract, S3 uploader pattern, rubrics.md
format, `run_result` artifact-assertion pattern, openspec process. TypeScript
logic ports to pydantic; YAML configs copy unchanged.
