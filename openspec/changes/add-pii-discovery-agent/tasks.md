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
- [x] **Live storage backend wired 2026-08-08** ([ADR 0003](../../adr/0003-minio-object-storage.md)): self-hosted MinIO, shared `ai-agents` bucket, credentials reused from `linkedin-cover-generator`. Fixed a real bug found in the process — `s3.py`'s client had no path-style addressing, which MinIO requires (`OBJECT_STORE_FORCE_PATH_STYLE`). Verified with a real put/list/delete round trip and a full deterministic-pipeline scan (`scan_51a46c946b8f`) — both `uploads/` and `results/` objects landed correctly, no prefix collision with other agents' `runs/` data.
- [x] DuckDB schema + `db.py` seam + cache lookup on `(checksum, pipeline_version)`
- [x] Gate: L1 unit tests green in CI (57 tests; first green run 2026-08-07)

### Phase 2 — Claude Managed Agent
- [x] Apply environment + agent YAML via `scripts/apply_control_plane.sh`; ids in `agent/applied.json` (never create in request path)
- [x] Host-side custom tools: cache_lookup / persist_result (s3_get/create_run dropped — the client mounts the document as a session resource and the manifest carries scan_id; the S3 mirror happens host-side inside persist_result)
- [x] Session client (consolidation on connect, terminal-idle gate, custom-tool round-trips, post-idle poll) + `client.scan` CLI with client-side cache short-circuit
- [x] Subagent roster wired (doc-extractor / pii-genai-scanner / report-assembler); reject trajectory verified end-to-end (`sesn_01PmKunz…`, 2026-08-07)
- [x] Gate: L2 trajectory + schema evals green — verified on real sessions 2026-08-07: reject trajectory (`sesn_01PmKunz…`: clean bash trail, one persist) and full scan (`sesn_014W2bpr…`: correct step order, schema valid, all excerpts grounded, one persist), assertions replayed from archived event history.
- [x] L2 rerun on the Sonnet-5 orchestrator (v4), 2026-08-08, 4 sessions, assertions replayed from stored events: **all HARD checks green** — columnar reject clean, both full scans correct step order + schema + 0 ungrounded excerpts, clean_01 zero Tier-1 false positives (closes the deferred FP-floor run). One **SOFT** warning: prose_01 session called `persist_result` twice; the DB primary key rejected the duplicate (data intact) — prompt hardened in v5. Client stream-race hang fixed (terminal events now honored during history replay).

### Phase 3 — GenAI path + model switching
- [x] GenAI extraction (`pipeline/genai_detect.py`: typed per-chunk `messages.parse`, `MODEL_PII_EXTRACTOR → MODEL → error`, code-enforced grounding) — host-side direct path per the D2 amendment; validated live 2026-08-08 with claude-haiku-4-5 on prose_01 (6/8 types, 0 spurious, all grounded)
- [x] `PII_ENGINE` switch live across all three engines on the direct path; normalization merge carries `source_model`
- [ ] Per-model scanner fan-out in sessions (v2 — the vault credential is now provisioned, [ADR 0004](../../adr/0004-scanner-vault-provisioned.md): `vlt_011CdquAYPJMTvYMyqSmYQmG`, header-only, scoped to `api.anthropic.com`. NOT yet wired into sessions/environment — needs explicit go-ahead, it's a real scope change: `vault_ids` on session create, `api.anthropic.com` in environment `allowed_hosts`, new L2 trajectory coverage)
- [ ] CI engine matrix for L2 (blocked on budgeted L2-in-CI decision)
- [ ] Gate: L2 P/R/F1 floors per model (rubrics §0); cross-model agreement reported

### Phase 4 — Observability
- [x] Session-event → OpenInference forwarder (`client/forwarder.py`: AGENT root + LLM/TOOL children, token counts from `model_usage`, `model_id` resource attr, `TELEMETRY_RECORD_IO` gate, degrades to one warning; works on archived sessions; auto-runs after each scan). 5 mapping tests in-memory.
- [x] Verified against a real collector 2026-08-08: archived L2 session `sesn_01Ju4eNE…` → 81 events → 22 spans, root span queryable in local Phoenix with scan_id/engine/per-type counts.
- [x] Arize AX ingest — credentials sourced from claimwise-agents 2026-08-08; all 10 archived sessions backfilled (822 events → 231 spans, zero export errors). Traces land in the Arize project named by the `model_id` resource attribute: **agent-pii-discovery**.
- [ ] Owner spot-check in the Arize UI (project `agent-pii-discovery`: 10 traces, token counts on LLM spans, finding counts on root spans) → then dashboards for the live KPIs

### Phase 5 — Live eval
- [x] R1 grounding + R4 span fidelity as deterministic code checks (`evals/judge/checks.py`, 100% of traces, no LLM)
- [x] R2 type-accuracy LLM judge (`evals/judge/llm_judge.py`, `MODEL_JUDGE → MODEL → error`, structured verdicts, unparseable = fail-not-pass) + deterministic calibration-case generator from corpus sidecars
- [x] L3 calibration shake-out 2026-08-08: **R2 @ 96.7% agreement (29/30) with claude-haiku-4-5 judge — passes the ≥90% threshold.** Sole disagreement is a judge-defensible ambiguity (bare passport-format ID without context) → improvement logged: pass chunk context for context-dependent ID types before the opus calibration round.
- [x] R3 coverage / R5 sensitivity / R6 injection-sign judges + deterministic calibration generators (R3: full-vs-holdout detected lists; R5: matrix-derived defensible/indefensible grades; R6: honest vs semantically-matched obeyed variants from injection fixtures)
- [x] **L3 GATE PASSED (2026-08-08, claude-opus-5 judge): R2 100% (30 cases — context fix took it from 96.7%), R3 100% (23), R5 100% (30), R6 100% (8, after fixing a calibration-case defect the judge itself exposed: injection_03's "empty findings" suppression variant was mismatched — the judge was right, the case was wrong).** R1/R4 are deterministic code, no calibration needed.
- [x] Judge runner (`evals/judge/runner.py`): R1/R4 at 100% + calibrated R2/R5 per scan (≤10 findings), writes `eval_scores`, HARD fail ⇒ `flagged`; `flagged_queue()` is the review-queue query.
- [x] Design decision (2026-08-08, [ADR 0002](../../adr/0002-arize-eval-push-not-native-judge.md)): judges run locally and push to Arize via `update_evaluations()`, not as native Arize tasks — R2/R3/R6 need document content our production spans deliberately don't carry. R5-only native task is optional/redundant, documented but not required. Setup walkthrough for both paths: [docs/evals.md § live judge](../../../docs/evals.md).
- [x] `pii.sensitivity.<TYPE>` attribute added to the root span (type + grade only, no PII value) — makes R5 judgeable natively if ever wanted; all 10 archived sessions re-forwarded with it.
- [x] **Local push job built (2026-08-08):** `evals/judge/push.py` — runs at the end of every `client.scan`, right after the forwarder, while the document is still on disk (no cold-storage re-fetch needed). R1/R4 at 100%, R2/R3/R5/R6 sampled (`PII_JUDGE_SAMPLE_RATE`, default 25%, deterministic per `scan_id`). `client/forwarder.py` now returns the root span/trace id; `pipeline/storage/db.py` gained `record_span()`/`mark_judged()`/`unjudged_scans()` + migration-safe schema columns. Verified end-to-end on two real scans (`scan_ec4fa1dcac53`, `scan_e0c77560b026`) — real Opus judge, real Arize push (`spans_updated=1`, `error_count=0`), correctly flagged two genuine Presidio false positives. 17 new tests, 106 total green.
- [ ] Drift (PSI vs offline baseline) + cost monitors in Arize over `llm.token_count.*` and `pii.findings.*` (owner, Arize UI — no eval task needed)
- [ ] Gate: one week of live scores on real traffic

### Phase 6 — Cheat-sheet card
- [ ] Reshape PRD into the 3–4 page A4 card (intent / design / operations)
