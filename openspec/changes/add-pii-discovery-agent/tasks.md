# Tasks — add-pii-discovery-agent

## Sign-off

| Field | Value |
|---|---|
| Status | approved |
| Approved by | Senthilnathan (senthilsweb) |
| Approved date | 2026-08-07 |

## Build tasks

### Phase 0 — Spec (this change folder)
- [x] PRD v0.2 (`docs/prd.md`)
- [x] proposal / design / spec / tasks
- [x] `evals/rubrics.md` written at Inception (before any code)
- [x] Agent + environment YAML drafted (`agent/`)
- [x] Labeled fixture corpus assembled (29 synthetic docs with char-span labels; verify.py + 7 pytest green)
- [x] Owner review → status `approved` (2026-08-07)

### Phase 1 — Core deterministic app (no GenAI, no agent)
- [x] `pipeline/`: checksum, structure gate, extract (text layer → OCR fallback), chunk, presidio_scan, normalize, assemble + `scan.py` CLI running the three trajectories
- [x] Port taxonomy/alias/compliance YAMLs (verbatim) + pydantic schemas
- [x] S3 uploader with `user_login`/`dt`/`sha256` partitioning (env-gated no-op, never-throw)
- [x] DuckDB schema + `db.py` seam + cache lookup on `(checksum, pipeline_version)`
- [x] Gate: L1 unit tests green in CI (57 tests; first green run 2026-08-07)

### Phase 2 — Claude Managed Agent
- [x] Apply environment + agent YAML via `scripts/apply_control_plane.sh`; ids in `agent/applied.json` (never create in request path)
- [x] Host-side custom tools: cache_lookup / persist_result (s3_get/create_run dropped — the client mounts the document as a session resource and the manifest carries scan_id; the S3 mirror happens host-side inside persist_result)
- [x] Session client (consolidation on connect, terminal-idle gate, custom-tool round-trips, post-idle poll) + `client.scan` CLI with client-side cache short-circuit
- [x] Subagent roster wired (doc-extractor / pii-genai-scanner / report-assembler); reject trajectory verified end-to-end (`sesn_01PmKunz…`, 2026-08-07)
- [x] Gate: L2 trajectory + schema evals green — verified on real sessions 2026-08-07: reject trajectory (`sesn_01PmKunz…`: clean bash trail, one persist) and full scan (`sesn_014W2bpr…`: correct step order, schema valid, all excerpts grounded, one persist), assertions replayed from archived event history. Clean-fixture Tier-1 FP run and the pytest-form rerun deferred to the Phase 3 budgeted round (owner credit constraint).

### Phase 3 — GenAI path + model switching
- [x] GenAI extraction (`pipeline/genai_detect.py`: typed per-chunk `messages.parse`, `MODEL_PII_EXTRACTOR → MODEL → error`, code-enforced grounding) — host-side direct path per the D2 amendment; validated live 2026-08-08 with claude-haiku-4-5 on prose_01 (6/8 types, 0 spurious, all grounded)
- [x] `PII_ENGINE` switch live across all three engines on the direct path; normalization merge carries `source_model`
- [ ] Per-model scanner fan-out in sessions (v2 — needs a vault API-key credential)
- [ ] CI engine matrix for L2 (blocked on budgeted L2-in-CI decision)
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
