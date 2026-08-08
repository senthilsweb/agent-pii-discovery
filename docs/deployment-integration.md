# Deployment & Integration

At the end you will know how each part of the system deploys — the agent
control plane, the client, and this docs site — and how other systems read
its output.

## Configuration

All configuration is environment-driven — see [Configuration](configuration.md).

## Deployment

The system has three deployable parts with different cadences:

### Agent control plane (deploy on config change)

The Managed Agent and its sandbox environment are version-controlled YAML in
`agent/`, applied once with the `ant` CLI and referenced by id thereafter:

```sh
cd agent
ENV_ID=$(ant beta:environments create < environment.yaml --transform id -r)
AGENT_ID=$(ant beta:agents create < pii-orchestrator.agent.yaml --transform id -r)
# updates create a new immutable version:
ant beta:agents update --agent-id "$AGENT_ID" --version <N> < pii-orchestrator.agent.yaml
```

Store the returned ids in the environment (`PII_AGENT_ID`,
`PII_ENVIRONMENT_ID`). Sessions pin `{id, version}`; agents are never created
in the request path. These commands land as part of Phase 2's gate — they are
recorded here as the contract the phase implements.

### Client (v1: local process)

The upload CLI/API, host-side tools, and trace forwarder run as one Python
process on the operator's machine in v1. Where it runs permanently (VPS,
serverless per upload) is an open question tracked in PRD §15.

### Docs site (this wiki)

Built and published by `.github/workflows/docs.yml` on any push to `main`
touching `docs/**` or `mkdocs.yml`: MkDocs Material, strict build (broken
links fail), deployed to GitHub Pages via the Pages Actions flow. The
docs-scoped path filter means a docs commit never triggers anything else.

## Upgrading

| What changed | How to upgrade | Side effects |
|---|---|---|
| Agent YAML (prompt, tools, roster) | `ant beta:agents update` → new version; update `PII_AGENT_VERSION` | Running sessions keep their pinned version |
| Detection prompt (`agent/skills/detection_prompt.md`) | Redeploy client env | `pipeline_version` changes → cache misses on all documents, by design |
| Extraction model (`MODEL_PII_EXTRACTOR`) | Env change only | Same cache invalidation as above |
| Taxonomy / alias YAML | Version bump in the file header | Same cache invalidation; re-baseline offline evals before trusting live drift monitors |
| DB engine (DuckDB → Postgres/MySQL) | Swap the DSN behind `db.py` | Schema is ANSI-portable; no DDL change expected |

Post-deploy verification: run one fixture through the full path, confirm the
result JSON validates, and confirm the trace appears in Arize with correct
span attributes before returning to normal traffic.

## Integration methods

| Method | When to use | Status |
|---|---|---|
| CLI (`python -m client.scan <file> --user <login>`) | One-off scans, scripting | Planned — Phase 2 ([task register](https://github.com/senthilsweb/agent-pii-discovery/blob/main/openspec/changes/add-pii-discovery-agent/tasks.md)) |
| Result JSON on S3 (`results/user_login=…/…/result.json`) | Downstream systems consuming per-document results | Contract defined (PRD §8–9) |
| DuckDB / SQL over the operational tables | Ad-hoc analysis, the flagged-review queue | Contract defined (PRD §9.2) |
| Public parquet export (no excerpts) | Zero-infrastructure dashboards; `SELECT … FROM 'https://…/findings.parquet'` | Planned — Phase 4+ |
| Arize AX | Quality monitoring, online evals | Phase 4–5 |

Next: [Operations](operations.md)
