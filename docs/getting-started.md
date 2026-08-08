# Getting Started

At the end you will have the repository locally, know what runs today, and
know where every artifact of the current phase lives.

## Prerequisites

| Requirement | Why |
|---|---|
| Python 3.12+ | Pipeline scripts, client, eval harness |
| `ant` CLI | Applies the Managed Agents control plane from `agent/*.yaml` |
| Anthropic API key (Managed Agents beta) | Runs sessions; orchestrator model |
| AWS account + S3 bucket | Upload and result storage |
| Arize AX account (space + API key) | Trace ingest and online evals |
| A `MODEL_PII_EXTRACTOR` provider key | The one generative step (any supported provider) |

## Installation

```sh
git clone https://github.com/senthilsweb/agent-pii-discovery.git
cd agent-pii-discovery
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
```

Optional extras: `[presidio]` (the real NER engine — downloads a spaCy
model), `[s3]` (boto3 uploader), `[extract]` (PDF + OCR support). None are
needed for the test suite.

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
