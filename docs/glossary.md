# Glossary

At the end you will have a one-line definition for every acronym, metric, and
project-specific term used anywhere else in these docs. Entries link forward
to the page that treats the term in depth — this page defines, it doesn't
re-explain.

## Core domain

| Term | Meaning |
|---|---|
| **PII** | Personally Identifiable Information — data that identifies or could identify a specific person. This project's subject matter. |
| **Canonical type** | One of the 36 fixed entity categories (`PERSON_NAME`, `EMAIL_ADDRESS`, `GOVERNMENT_ID_SSN`, …) every engine's raw label is normalized into. Closed list — see [Reference § Canonical entity types](reference.md#canonical-entity-types). |
| **Structural class** | `unstructured` (prose, scanned image) vs. `columnar` (CSV/XLSX). Decided by the structure gate before any scan runs. |
| **Trajectory** | One of exactly three legal session paths: cache hit, columnar reject, full scan. See [Architecture § Agent flow](architecture.md#agent-flow-the-three-legal-trajectories). |
| **Sensitivity grade** | `low` \| `medium` \| `high` \| `critical` — assigned per canonical type, judged for defensibility by rubric criterion R5. |
| **Grounding** | The invariant that every excerpt an engine reports is a verbatim (whitespace/case-normalized) substring of the source document — never a fabricated or paraphrased value. |

## AI / agent & observability

| Term | Meaning |
|---|---|
| **LLM** | Large Language Model. |
| **GenAI** | Generative AI — this project's shorthand for the LLM-based detection engine, as distinct from the deterministic Presidio engine. |
| **NER** | Named Entity Recognition — the class of model Presidio uses internally to find spans like names and locations. |
| **Presidio** | Microsoft's open-source PII detection library — the deterministic engine option (`PII_ENGINE=presidio`). |
| **CMA / Claude Managed Agents** | Anthropic's hosted agent runtime: Anthropic runs the agent loop *and* hosts a per-session sandbox container. See [Architecture § Tech stack](architecture.md#tech-stack). |
| **Session** | One Managed Agents run — the orchestrator and its subagents operating in a single per-run sandbox, torn down after terminal idle. |
| **Subagent / thread** | A Managed Agents delegate (doc-extractor, pii-genai-scanner, report-assembler) that shares the session's sandbox filesystem but not conversation history. |
| **OTel (OpenTelemetry)** | The vendor-neutral standard for traces, spans, and instrumentation this project exports through. |
| **OTLP** | OpenTelemetry Protocol — the wire protocol OTel exporters use to ship spans to a collector (here, `otlp.arize.com`). |
| **OpenInference** | The semantic-convention spec (span kinds, attribute names) for AI/LLM traces, layered on top of OTel — what makes a span show up correctly as an "LLM call" or "tool call" in Arize. |
| **SSE (Server-Sent Events)** | The one-way event stream a Managed Agents session emits; the client converts this stream into OpenInference spans after the session ends. |
| **Arize AX** | Arize's cloud observability platform for AI systems — this project's trace-ingest, dashboard, and online-eval destination. "AX" is part of the product name, not a separate acronym. |

## Evaluation & metrics

| Term | Meaning |
|---|---|
| **P/R/F1** | Precision / Recall / F1 score — the three standard detection-quality metrics, computed per canonical type per engine/model. Precision = correct-of-flagged; recall = found-of-actual; F1 = their harmonic mean. Formulas: [`evals/rubrics.md` §0](https://github.com/senthilsweb/agent-pii-discovery/blob/main/evals/rubrics.md). |
| **TP / FP / FN** | True Positive / False Positive / False Negative — the counts P/R/F1 are built from. |
| **HARD / SOFT** | Rubric severity. **HARD** = objective, deterministic; any violation fails the eval and blocks promotion. **SOFT** = a directional quality expectation; violations are logged and reviewed, not blocking. |
| **L1 – L4** | The four eval layers: L1 unit tests, L2 offline agent evals (labeled corpus), L3 judge calibration, L4 live regression on production traffic. See [Evals § The four layers](evals.md#the-four-layers). |
| **R1 – R6** | The six live-judge rubric criteria scored per traced scan: grounding, type accuracy, coverage, span fidelity, sensitivity sanity, no instruction-following. See [Evals § The live judge](evals.md#the-live-judge-l4). |
| **Cohen's κ (kappa)** | A chance-corrected agreement statistic; used here to report how often two engines/models agree on a type, better than raw percent-agreement because it discounts agreement expected by chance. |
| **Jaccard (index)** | Set-overlap similarity: intersection size over union size; used here at the document level to compare the *set* of detected types between models. |
| **PSI (Population Stability Index)** | A drift metric comparing a live score distribution against a frozen offline baseline; large PSI flags that live behavior has shifted. |
| **KS (Kolmogorov–Smirnov test)** | A statistical test for whether two distributions differ; used alongside PSI for the same drift comparison. |

## Compliance / regulatory regimes

Seven regimes this project maps findings against by table lookup (never inference):

| Term | Meaning |
|---|---|
| **GDPR** | General Data Protection Regulation — European Union. |
| **CCPA/CPRA** | California Consumer Privacy Act / California Privacy Rights Act — United States (California). |
| **DPDP** | Digital Personal Data Protection Act — India. |
| **PDPL** | Personal Data Protection Law — Argentina, in this project's usage (`PDPL_ARGENTINA`). |
| **HIPAA** | Health Insurance Portability and Accountability Act — United States (health data). |
| **LGPD** | Lei Geral de Proteção de Dados — Brazil. |
| **PIPEDA** | Personal Information Protection and Electronic Documents Act — Canada. |
| **KYC** | Know Your Customer — the identity-verification records exercised by the `synthetic_prose_12` fixture. |

## Engineering / infrastructure

| Term | Meaning |
|---|---|
| **PRD** | Product Requirements Document — [`docs/prd.md`](https://github.com/senthilsweb/agent-pii-discovery/blob/main/docs/prd.md), the authoritative scope/architecture/KPI source. |
| **ADR** | Architecture Decision Record — a dated, single-decision doc under `openspec/adr/`. |
| **CI / CI/CD** | Continuous Integration / Continuous Integration & Continuous Deployment — automated test-on-push, and (where applicable) automated deploy-on-merge. |
| **API** | Application Programming Interface. |
| **CLI** | Command-Line Interface. |
| **SDK** | Software Development Kit. |
| **YAML** | A human-readable data-serialization format ("YAML Ain't Markup Language"); this project's agent/environment control-plane files. |
| **JSON** | JavaScript Object Notation — the result and label-sidecar format. |
| **SQL** | Structured Query Language. |
| **DDL (Data Definition Language)** | The subset of SQL that defines schema (`CREATE TABLE …`) rather than reads/writes rows. |
| **DSN (Data Source Name)** | The connection string a database client uses to reach a server — what would replace the local DuckDB file path if this project's DB seam were pointed at Postgres/MySQL. |
| **ANSI-portable (SQL)** | Written without vendor-specific SQL dialect extensions, so the same schema/queries run unmodified on DuckDB, Postgres, or MySQL. |
| **TTL (Time To Live)** | A fixed expiry duration. Called out in [Configuration § Cache semantics](configuration.md#cache-semantics) specifically because this project's cache has *no* TTL — invalidation is by content/config change only. |
| **S3** | Amazon's Simple Storage Service object-storage API. This deployment points the same S3-compatible client at self-hosted MinIO — see [ADR 0003](https://github.com/senthilsweb/agent-pii-discovery/blob/main/openspec/adr/0003-minio-object-storage.md). |
| **MinIO** | A self-hosted, S3-API-compatible object storage server; this project's actual upload/result store. |
| **DuckDB** | An embedded, file-based analytical SQL database; this project's operational store for scans/findings/eval scores. |
| **VPS (Virtual Private Server)** | A persistently-running rented server — one open option for where the always-on client process could run in production (PRD §15). |
| **GUI** | Graphical User Interface — explicitly absent from this project ([Overview § Limitations](index.md#limitations)); the read surface is JSON, the database, and the parquet export. |
| **IAM (Identity and Access Management)** | Cloud-provider access-control configuration — scoping what an S3 credential is allowed to touch. |
| **OCR (Optical Character Recognition)** | Text extraction from a scanned image (no selectable text layer); this project's fallback extraction path, exercised by the `synthetic_ocr_*` fixtures. |
| **E.164** | The ITU international standard format for phone numbers (e.g. `+14155552671`); the target of this project's phone-number normalization where computable. |
| **FAQ** | Frequently Asked Questions — see [Reference § FAQ](reference.md#faq). |

Next: [Reference](reference.md)
