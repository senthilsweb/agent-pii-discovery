# Proposal — add-pii-discovery-agent

## Why

Our eval flow today is offline only: evals run in CI/CD, gate promotion, and
then measurement stops at the production boundary. We want to close that gap by
attaching evals to production traces — model drift, cost, and tool-trajectory
checks running on real traffic without touching the request path. PII discovery
is the chosen use case because it gives clean ground truth, and we already own
proven building blocks (canonical taxonomy, Presidio engine switch, normalizer,
OTel instrumentation) in the `ai-agents` monorepo.

This is also the first project on **Claude Managed Agents** — a hosted agent
loop + per-session sandbox — so the repo doubles as the reference for running
our agent conventions on that runtime.

## What changes

- New public repo `agent-pii-discovery` with its own openspec tree.
- A Claude Managed Agent (`pii-orchestrator`, coordinator + three subagents)
  that scans an uploaded document for PII along two paths (deterministic
  Presidio/regex; GenAI with a switchable model) and produces one normalized
  result per document.
- Storage: uploads in S3 partitioned by `user_login`/`dt`/`sha256`; results in
  DuckDB with an ANSI-portable schema (production path: Postgres/MySQL).
- Observability: a session-event → OpenInference/OTel forwarder shipping every
  run to Arize AX; online LLM-as-judge evals + drift/cost monitors on sampled
  production traces.
- A four-layer eval harness (unit / offline agent evals / judge calibration /
  live regression evals) that gates every phase.

## Impact

- No existing system is modified; the `ai-agents` monorepo is a source of
  ported code and conventions only.
- Real PII is handled: uploads/results are gitignored, S3 is private with
  lifecycle expiry, trace IO recording is off in production, and the published
  parquet export carries no excerpts.
- Costs: Claude token usage (orchestrator + extraction + judges) plus
  ~$0.08/session-hour Managed Agents runtime, S3/DuckDB storage, Arize AX
  ingest. Judge sampling starts at 25% and is tuned by observed cost.
