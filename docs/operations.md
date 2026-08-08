# Operations

At the end you will know what is observable in production, what it costs, and
what to do when something breaks.

## Logging

The client process logs session lifecycle (created, terminal state, duration),
tool round-trips, and forwarder delivery. Telemetry backends that are missing
or unreachable produce exactly one logged warning — never a failed scan.

## Tracing

Every session's event stream is converted to OpenInference spans and shipped
to Arize AX by the forwarder (client-side, after the session, off the request
path):

| Session event | Span |
|---|---|
| `span.model_request_start` / `_end` | LLM span — model, latency, token usage (`model_usage`) |
| `agent.tool_use` / `tool_result` | TOOL span — name, duration, status |
| Thread events | One sub-trace per subagent, tagged with its model |
| Whole session | AGENT root span — `session_id`, `scan_id`, `checksum`, `user_login`, `pii.engine`, `cache_hit`, per-type finding counts |

Production spans carry counts, types, tokens, and ids — never document text
(`TELEMETRY_RECORD_IO=false`). Each Managed Agents session also has a live
Console trace view, useful during development.

## Metrics

| KPI | Kind | Where |
|---|---|---|
| P/R/F1 per canonical type, per engine, per model | Offline gate | CI (L2), floors in [rubrics §0](https://github.com/senthilsweb/agent-pii-discovery/blob/main/evals/rubrics.md) |
| Judge score distribution R1–R6 | Live | Arize online evals |
| Drift vs frozen offline baseline (PSI / KS) | Live monitor | Arize |
| Flagged-for-review rate | Live monitor | Arize → `eval_scores` table (target < 2%) |
| Cache hit rate | Live | `cache_hit` trace attribute |
| Cost/doc, tokens/doc, latency p95 | Live monitor | Arize (from `model_usage`) |
| Per-type finding-volume mix | Live | Cheap no-ground-truth drift signal |

## Health checks

v1 has no long-running service to probe; health is "did the last scan trace
arrive in Arize" — checked by the post-deploy verification in
[Deployment & Integration](deployment-integration.md).

## Cost considerations

Three meters run per scan: Claude tokens (orchestrator + subagents), the
extraction model's tokens (per compared model), and Managed Agents runtime
(~$0.08 per active session-hour, billed on active time). Live-eval cost is
controlled by sampling — judges at 25% of traces, code-based checks at 100% —
tuned after the first week of real traffic. The cache exists precisely to
make repeat uploads free.

## Runbooks

Failures that have actually been observed (this list grows only from real
incidents, starting with those inherited from the monorepo's verified
experience):

| Failure | Fix |
|---|---|
| Arize collector returns 500 on every span | The `model_id` resource attribute is missing. Restore `Resource({service.name, model_id})` in the forwarder. Verified against `otlp.arize.com` 2026-07-15 (monorepo). |
| Spans arrive in the dev Phoenix but not Arize | The two exporters fail independently by design — check `ARIZE_SPACE_ID`/`ARIZE_API_KEY`; a misconfigured backend logs one warning and drops its own spans only. |
| A scan re-runs for a document that should be cached | The detection prompt, model, engine, or taxonomy changed — `pipeline_version` moved, so the miss is correct. Confirm by diffing the manifest's `pipeline_version` against the cached row. |

Procedures with cost or risk: archiving the Managed Agent or its environment
is **permanent** (read-only, no unarchive, new sessions cannot reference it) —
never archive as cleanup; pin sessions to an older version instead and confirm
with the owner first.

Next: [Reference](reference.md)
