# Getting Started

At the end you will have the repository locally, know what runs today, and
know where every artifact of the current phase lives.

## Prerequisites

| Requirement | Why |
|---|---|
| Python 3.12+ | Pipeline scripts, client, eval harness |
| `ant` CLI | Applies the Managed Agents control plane from `agent/*.yaml` |
| Anthropic API key (Managed Agents beta) | Runs sessions; orchestrator model |
| S3-compatible object store | Upload and result storage. Self-hosted MinIO in this deployment ([ADR 0003](https://github.com/senthilsweb/agent-pii-discovery/blob/main/openspec/adr/0003-minio-object-storage.md)) — AWS S3 also works, no code change |
| Arize AX account (space + API key) | Trace ingest and online evals |
| `MODEL_PII_EXTRACTOR` + `MODEL_JUDGE` provider keys | The one generative step and the live judge (any supported provider; must differ from each other and from the orchestrator) |

## Installation

```sh
git clone https://github.com/senthilsweb/agent-pii-discovery.git
cd agent-pii-discovery
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
```

Optional extras: `[presidio]` (the real NER — named entity recognition —
engine, downloads a spaCy model), `[s3]` (boto3 uploader), `[extract]` (PDF +
OCR — optical character recognition — support). None are needed for the test
suite. Any acronym on this page is defined in the [Glossary](glossary.md).

## Quick start

Run the L1 suite (57 tests: pipeline units + corpus integrity — no network,
no model, no key):

```sh
.venv/bin/pytest
```

Scan a fixture through the deterministic pipeline:

```sh
PII_ENGINE=presidio .venv/bin/python -m pipeline.scan \
    evals/data/columnar_01/document.csv --user senthil
```

```json
{
  "scan_id": "scan_44244d7120f9",
  "status": "skipped_out_of_scope",
  "reason": "structured_columnar",
  "findings": {},
  "jurisdictions": []
}
```

That is the columnar-reject trajectory: the structure gate fired, no scan
tool ran, and the scan row landed in the (gitignored) DuckDB at
`data/pii.duckdb`. Scanning prose documents with real Presidio needs the
`[presidio]` extra; the corpus verifier is
`python3 evals/corpus/verify.py`.

The GenAI engine runs on the same direct path with a switchable model
(authenticates via your `ant auth login` profile — no API key env var):

```sh
PII_ENGINE=genai_only MODEL_PII_EXTRACTOR=claude-haiku-4-5 \
    .venv/bin/python -m pipeline.scan evals/data/synthetic_prose_01/document.txt --user senthil
```

```json
{
  "scan_id": "scan_98c698daaef2",
  "status": "processed",
  "findings": {
    "DATE_OF_BIRTH": 1, "EMAIL_ADDRESS": 1, "GOVERNMENT_ID_SSN": 1,
    "PERSON_NAME": 1, "PHONE_NUMBER": 1, "PHYSICAL_ADDRESS": 1
  },
  "jurisdictions": ["CCPA_CPRA", "DPDP_INDIA", "GDPR", "LGPD", "PDPL_ARGENTINA", "PIPEDA"]
}
```

Each jurisdiction code is one of the seven compliance regimes this project
maps findings against — spelled out in the
[Glossary § Compliance / regulatory regimes](glossary.md#compliance-regulatory-regimes).

The Managed Agents session path and the GenAI engine arrive with Phases 2–3;
each phase's exit gate is in the
[openspec tasks](https://github.com/senthilsweb/agent-pii-discovery/blob/main/openspec/changes/add-pii-discovery-agent/tasks.md).

## Reading order

1. [PRD](https://github.com/senthilsweb/agent-pii-discovery/blob/main/docs/prd.md) — scope, architecture, KPIs
2. [openspec change](https://github.com/senthilsweb/agent-pii-discovery/tree/main/openspec/changes/add-pii-discovery-agent) — proposal → design → spec → tasks
3. [Eval rubrics](https://github.com/senthilsweb/agent-pii-discovery/blob/main/evals/rubrics.md) — what "correct" means, defined before the code
4. [Architecture](architecture.md) — how a scan flows once built

## Project structure

```text
agent/       Managed Agents control plane (YAML) + system prompt + skills
docs/        this site + the PRD
evals/       rubrics, fixture corpus + generator, integrity tests
openspec/    proposal / design / spec / tasks + ADRs
```

The full annotated tree and the load-bearing files are in the
[Code Tour](code-tour.md).

Next: [Code Tour](code-tour.md)
