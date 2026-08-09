# Operations

At the end you will know what is observable in production, what it costs, and
what to do when something breaks. Unfamiliar acronym? Check the
[Glossary](glossary.md).

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
| Whole session | AGENT root span — `session_id`, `scan_id`, `checksum`, `user_login`, `pii.engine`, `cache_hit`, `pii.findings.<TYPE>` (count), `pii.sensitivity.<TYPE>` (grade — no value, no excerpt) |
| Cache hit (no session) | Same span name (`pii_scan.session`), emitted directly by `client/scan.py` via `forward_cache_hit()` — `cache_hit=true`, `request_id`, `scan_id` (the original scan that served it), `checksum`, `user_login`. No LLM/TOOL children (nothing ran). |

Production spans carry counts, types, tokens, and ids — never document text
(`TELEMETRY_RECORD_IO=false`). Each Managed Agents session also has a live
Console trace view, useful during development.

## Metrics

| KPI | Kind | Where |
|---|---|---|
| P/R/F1 per canonical type, per engine, per model | Offline gate | CI (L2), floors in [rubrics §0](https://github.com/senthilsweb/agent-pii-discovery/blob/main/evals/rubrics.md) |
| Judge score distribution R1–R6 | Live | Judged locally, pushed to Arize ([Evals § live judge](evals.md#the-live-judge-l4)) |
| Drift vs frozen offline baseline (PSI — Population Stability Index / KS — Kolmogorov–Smirnov test) | Live monitor | Arize |
| Flagged-for-review rate | Live monitor | Arize → `eval_scores` table (target < 2%) |
| Cache hit rate | Live | `cache_hit` trace attribute, or `db.cache_hit_rate()` locally — doesn't depend on Arize being configured |
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
| Session halts at "bootstrap failed", agent reports the script path missing | The clone must run before the bootstrap script (the script lives inside the repo it clones). The system prompt inlines the clone command since orchestrator v2 — if this reappears, check the prompt wasn't edited back. Seen: `sesn_01BYaMCt…` (2026-08-07). |
| Bootstrap fails with `requires a different Python: 3.11.x not in '>=3.12'` | The sandbox's default `python3` is 3.11; 3.12/3.13 exist beside it. The bootstrap builds `/workspace/venv` on the newest interpreter and all step commands run through it. Seen: `sesn_01NtVoGY…` (2026-08-07). |
| Agent can't find the mounted document at its `mount_path` | File resources mount under `/mnt/session/uploads/<mount_path>`, not at the literal path. The client's manifest carries the real location. Seen: `sesn_01BYaMCt…` (2026-08-07). |
| A scan session ends `end_turn` but nothing persisted | The agent halted honestly before `persist_result` (setup failure) — read its final message and the bash tool results in the event log; the session trace URL is printed by the client. |
| Arize collector returns 500 on every span | The `model_id` resource attribute is missing. Restore `Resource({service.name, model_id})` in the forwarder. Verified against `otlp.arize.com` 2026-07-15 (monorepo). |
| Spans arrive in the dev Phoenix but not Arize | The two exporters fail independently by design — check `ARIZE_SPACE_ID`/`ARIZE_API_KEY`; a misconfigured backend logs one warning and drops its own spans only. |
| A scan re-runs for a document that should be cached | The detection prompt, model, engine, or taxonomy changed — `pipeline_version` moved, so the miss is correct. Confirm by diffing the manifest's `pipeline_version` against the cached row. Note rejects (`skipped_out_of_scope`) are never cache-served — only `processed` results are. |
| `client.scan` (or any host-side call) suddenly 404s on the orchestrator agent / environment | `ANTHROPIC_API_KEY` is set somewhere in the shell or `.env` and belongs to a different workspace than `agent/applied.json`'s resources — an API key always outranks the `ant auth login` profile. Fix: `unset ANTHROPIC_API_KEY` (or remove it from `.env`) and re-verify with `ant auth status` / a free `agents.retrieve()` call. **Never** put a static Anthropic key in this project's `.env` — host auth is the OAuth profile only; a static key's only legitimate home here is a vault `environment_variable` credential (ADR 0004), which has no workspace-matching requirement. Seen: 2026-08-08 (issue #14), caught before any live session used the bad credential. |

Procedures with cost or risk: archiving the Managed Agent or its environment
is **permanent** (read-only, no unarchive, new sessions cannot reference it) —
never archive as cleanup; pin sessions to an older version instead and confirm
with the owner first.

Next: [Reference](reference.md)
