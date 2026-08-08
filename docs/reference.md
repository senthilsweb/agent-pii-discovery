# Reference

## Configuration reference

The complete variable table lives on its own page: [Configuration](configuration.md).

## Result schema

One `result.json` per scan (persisted to DuckDB and mirrored to S3). Per
finding, after normalization:

| Field | Type | Meaning |
|---|---|---|
| `canonical_type` | enum (36 values) | One of the canonical entity types |
| `raw_labels_seen` | string[] | Labels exactly as engines/models returned them |
| `occurrences` | int | Distinct occurrences rolled up |
| `chunk_ids` | string[] | Where in the document |
| `sample_excerpts` | string[] (≤5) | Verbatim substrings of the source (grounding invariant) |
| `span` | {chunk_id, start, end} | Char offsets where available |
| `normalized_value` | string? | Canonical form where computable (lowercased email, E.164 phone) |
| `source_engines` | ("presidio"\|"genai")[] | Which paths found it |
| `source_models` | string[] | Which models (GenAI findings) |
| `max_confidence` | 0–1 | Max across merged raw findings |
| `sensitivity` | low\|medium\|high\|critical | Max across merged raw findings |

Document envelope: file metadata, `structural_class`, `processing_status`,
`extraction_method`, `ocr_enabled`, `chunk_count`, `engine`, `models`,
`compliance_impact` (regimes + hits + severity), and the run block
(`scan_id`, `session_id`, timestamps). Authoritative prose: PRD §8.

## Database schema

Four ANSI-portable tables — `documents` (by checksum), `scans` (by run,
joined to traces via `session_id`), `findings` (one row per rolled-up
finding), `eval_scores` (written back from Arize). Full DDL: PRD §9.2.

## Status values

| `processing_status` | Meaning |
|---|---|
| `processed` | Full scan completed |
| `skipped_out_of_scope` | Columnar/structured file — rejected by the structure gate |
| `failed` | Extraction or pipeline failure; `reason` populated |
| `cache_hit` (scan status) | Result served from cache; no session ran |

## Canonical entity types

36 types across identity, contact, government IDs, financial, health,
special-category (GDPR Art. 9), network/device, and context groups, plus
`OTHER_SENSITIVE` and the `UNKNOWN` fallback. The closed list and alias
rules: PRD §8; the coverage each fixture group exercises:
[Evals](evals.md).

## FAQ

**Why exactly one generative step?**
Determinism, cost, and injection defense in one decision — the LLM never
emits a number, so embedded instructions have no channel to change one. See
[design D2](https://github.com/senthilsweb/agent-pii-discovery/blob/main/openspec/changes/add-pii-discovery-agent/design.md).

**Why is there no cache TTL?**
The cache key includes `pipeline_version`; configuration change is the
invalidation. See PRD §9 and [Configuration](configuration.md).

**Why Arize AX and not local Phoenix?**
The owner already operates Arize cloud, and its online-eval tasks are the
live-eval mechanism this project exists to learn. Phoenix remains a dev-only
fan-out. See [ADR 0001](https://github.com/senthilsweb/agent-pii-discovery/blob/main/openspec/adr/0001-claude-managed-agents-and-arize.md).

**Why don't the R1–R6 judges run inside Arize?**
Three of the six criteria (R2, R3, R6) need to see the excerpt or document
passage to judge, and production traces deliberately carry none of it. The
judges run locally, where the database legitimately holds the full result,
and verdicts are pushed onto the trace afterward. See
[Evals § live judge](evals.md#the-live-judge-l4) and
[ADR 0002](https://github.com/senthilsweb/agent-pii-discovery/blob/main/openspec/adr/0002-arize-eval-push-not-native-judge.md).

**Why do eval floors differ per engine?**
Published benchmarks put bare Presidio at F1 ≈ 0.57 on contextual types — a
uniform Tier-2 gate would fail on arrival while telling us nothing. See the
dated corrections in [rubrics §0](https://github.com/senthilsweb/agent-pii-discovery/blob/main/evals/rubrics.md).

**Why was the `openai_privacy_filter` engine dropped?**
Its 8-class taxonomy cannot express the 36 canonical types, and published
fine-tuning curves need thousands of labeled documents per domain. See PRD §15.

**Why does the orchestrator run on Claude if the extraction model is switchable?**
The harness (Managed Agents) is Claude-native; the extraction step is a tool
that owns its own provider call, so the comparison surface is independent of
the runtime. See [design D2](https://github.com/senthilsweb/agent-pii-discovery/blob/main/openspec/changes/add-pii-discovery-agent/design.md).

## Known limitations

- Detection only; no redaction, no masking, no data-subject workflows.
- Scanned images depend on OCR quality; an unreadable scan fails the run
  (`unreadable_document`) rather than guessing.
- Tier-3 (semantic) entity types are reported without CI floors — recall on
  them is unproven until Phase 3 measurement.
- The GenAI path's span offsets are best-effort; only Presidio guarantees them.
- No load or scale testing has been performed.

## Roadmap

- [x] Phase 0 — PRD, openspec change, agent control plane, rubrics, fixture corpus
- [x] Phase 1 — deterministic pipeline (checksum → S3 → cache → Presidio → normalize → DuckDB)
- [x] Phase 2 — Claude Managed Agent end to end
- [ ] Phase 3 — GenAI path + model switching
- [ ] Phase 4 — trace forwarder + Arize dashboards
- [ ] Phase 5 — live eval: judges, drift monitors, flagged queue
- [ ] Phase 6 — cheat-sheet card

The working detail lives in the
[openspec task register](https://github.com/senthilsweb/agent-pii-discovery/blob/main/openspec/changes/add-pii-discovery-agent/tasks.md)
— the docs never carry their own TODO list.
