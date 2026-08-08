# agent-pii-discovery

A sensitive-data (PII) discovery agent that runs entirely on **Claude Managed
Agents**, with **live evaluation of production traces in Arize AX**. Upload a
document → deterministic scan (Presidio + regex) and/or a GenAI scan with a
switchable model → one normalized, canonical result → S3 + DuckDB → every run
traced into Arize, where LLM-as-judge evals score real traffic after the fact.

The point of the project is learning **live eval** — evals attached to
production traces, decoupled from the request path. The PII use case is chosen
because it gives clean ground truth.

- Full requirements: `docs/prd.md` (v0.2)
- Design spec: `openspec/changes/add-pii-discovery-agent/`
- Eval rubrics (written before the code): `evals/rubrics.md`

## Process

Every non-trivial change goes through `openspec/changes/<name>/`
(proposal → design → tasks → spec) before and during implementation, with the
status lifecycle `proposed → approved → implemented → verified → archived`.
This mirrors the AI-DLC-tailored process used in the `ai-agents` monorepo and
`agent-job-matcher`. Numbered ADRs live in `openspec/adr/`; empirical findings
in `openspec/observations/`.

Promotion is gated by the four-layer eval harness (PRD §11):
L1 unit tests + L2 offline agent evals green ⇒ `implemented`;
L2 metric floors + L3 judge calibration ⇒ `verified`. No promotion on red.

## Layout

- `docs/prd.md` — the PRD (source of truth for scope and phases).
- `openspec/` — this repo owns its own openspec tree (standalone-repo
  convention, like job-pilot/job-scout).
- `agent/` — the Claude Managed Agent control plane, as version-controlled
  YAML applied with the `ant` CLI (`ant beta:agents create < agent/pii-orchestrator.agent.yaml`).
  - `pii-orchestrator.agent.yaml` — the coordinator agent (create once, store
    the id; **never** create agents in the request path).
  - `environment.yaml` — the sandbox environment (`limited` networking,
    deny-by-default egress).
  - `system_prompt.md` — the orchestrator system prompt (inlined into the
    agent YAML via `@file` at apply time).
  - `skills/` — load-on-demand skill markdown for the agent (per-agent skills
    convention from the monorepo).
- `evals/` — rubrics + (later) the pytest harness and labeled fixture corpus.
- `client/` (later phases) — the host-side session client, custom tools
  (S3/DuckDB), and the session-event → OpenInference → Arize forwarder.
- `pipeline/` (later phases) — deterministic scripts run in the sandbox
  (extract, chunk, presidio scan, normalize, assemble).

## Conventions (inherited from the ai-agents monorepo)

- **Exactly one generative step** — the typed PII extraction call. Counts,
  scores, and compliance verdicts are always computed in code; the LLM never
  emits a number. This is also the prompt-injection defense.
- **Models resolve from env, no hard-coded defaults**:
  `MODEL_<ROLE>_* → MODEL_* → startup error` (e.g. `MODEL_PII_EXTRACTOR`).
- **Engine switch**: `PII_ENGINE` = `presidio | presidio_genai | genai_only`,
  required, no silent default; reserved names fail fast.
- **Canonical taxonomy**: 36 canonical entity types + YAML alias table; config
  can never invent a new type; unknown labels degrade to `UNKNOWN`, never throw.
- **Telemetry degrades, never crashes**: missing/unreachable backend = one
  logged warning. Arize AX requires the `model_id` resource attribute on spans
  (its collector returns 500 without it). `TELEMETRY_RECORD_IO=false` in
  production — document text never leaves for Arize.
- **Runs and data are gitignored** — uploads and results contain real PII and
  this repo is public. Fixtures are synthetic only. The published parquet
  export is the slim, no-excerpt variant.
- **Credentials never enter the sandbox** — S3/DB access via host-side custom
  tools or vault egress substitution.

## Run

- Install: `python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"`
- L1 tests (57; no network/model/key): `.venv/bin/pytest`
- Scan a document (deterministic path): `PII_ENGINE=presidio .venv/bin/python -m pipeline.scan <file> --user <login>` (prose scans need the `[presidio]` extra)
- Corpus verifier: `python3 evals/corpus/verify.py`
- Target for Phase 2+: offline evals `pytest evals/ -m offline` (one CI job per `PII_ENGINE` value); apply agent config `cd agent && ant beta:agents create < pii-orchestrator.agent.yaml`
