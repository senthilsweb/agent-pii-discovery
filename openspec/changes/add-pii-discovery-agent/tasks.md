# Tasks — add-pii-discovery-agent

## Sign-off

| Field | Value |
|---|---|
| Status | proposed |
| Approved by | — |
| Approved date | — |

## Build tasks

### Phase 0 — Spec (this change folder)
- [x] PRD v0.2 (`docs/prd.md`)
- [x] proposal / design / spec / tasks
- [x] `evals/rubrics.md` written at Inception (before any code)
- [x] Agent + environment YAML drafted (`agent/`)
- [ ] Labeled fixture corpus assembled (~30 synthetic docs with char-span labels)
- [ ] Owner review → status `approved`

### Phase 1 — Core deterministic app (no GenAI, no agent)
- [ ] `pipeline/`: checksum, extract (text layer → OCR fallback), chunk, presidio_scan, normalize, assemble
- [ ] Port taxonomy/alias/compliance YAMLs + pydantic schemas
- [ ] S3 uploader with `user_login`/`dt`/`sha256` partitioning
- [ ] DuckDB schema + `db.py` seam + cache lookup on `(checksum, pipeline_version)`
- [ ] Gate: L1 unit tests green in CI

### Phase 2 — Claude Managed Agent
- [ ] Apply environment + agent YAML; store ids (never create in request path)
- [ ] Host-side custom tools: s3_put/s3_get/cache_lookup/persist_result/create_run
- [ ] Session client (stream-first, terminal-idle gate, custom-tool round-trips)
- [ ] Subagent roster wired (doc-extractor / pii-genai-scanner / report-assembler)
- [ ] Gate: L2 trajectory + schema evals green

### Phase 3 — GenAI path + model switching
- [ ] `detect_pii_genai` tool (structured output, provider-agnostic, `MODEL_PII_EXTRACTOR`)
- [ ] `PII_ENGINE` switch + CI engine matrix
- [ ] Per-model scanner fan-out; normalization merge with `source_model`
- [ ] Gate: L2 P/R/F1 floors per model (rubrics §0); cross-model agreement reported

### Phase 4 — Observability
- [ ] Session-event → OpenInference forwarder (`model_id` resource attr set)
- [ ] Arize AX project + KPI dashboards; optional local Phoenix fan-out
- [ ] Gate: every L2 run visible as a correct trace (spans/tokens/costs spot-checked)

### Phase 5 — Live eval
- [ ] Judge evaluators for rubric R1–R6; calibration set
- [ ] Arize online-eval tasks (25% judge / 100% code checks) + drift & cost monitors
- [ ] Flagged-review queue + `eval_scores` sync job
- [ ] Gate: L3 ≥90% agreement; one week of live scores on real traffic

### Phase 6 — Cheat-sheet card
- [ ] Reshape PRD into the 3–4 page A4 card (intent / design / operations)
