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
```

There is nothing to `pip install` in the current phase — the repo is
specification, agent configuration, rubrics, and the labeled fixture corpus.
The Python package lands with Phase 1.

## What runs today

The fixture corpus verifier is the first runnable code:

```sh
python3 evals/corpus/verify.py
```

It re-validates every fixture's character spans and prints the entity-type
coverage table. The same checks run as pytest in `evals/test_corpus_integrity.py`.

The scan pipeline, session client, and the commands documented in
[Deployment & Integration](deployment-integration.md) arrive with Phases 1–3;
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
