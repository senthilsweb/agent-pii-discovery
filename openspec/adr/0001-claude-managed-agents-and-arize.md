# ADR 0001 — Claude Managed Agents runtime; Arize AX for traces and live eval

Date: 2026-08-07 · Status: accepted

## Decision

1. The agent runs on **Claude Managed Agents** (hosted agent loop + per-session
   sandbox), configured as version-controlled YAML applied with the `ant` CLI.
   Sessions pin `{agent_id, version}`; agents are never created in the request
   path.
2. Traces and live eval live in **Arize AX (cloud)**. Because Managed Agents
   exposes tracing as a session event stream (not a native OTel exporter), we
   own a forwarder: session events → OpenInference spans → OTLP →
   `otlp.arize.com`. Local Phoenix remains an optional dev-only second export.

## Why

- One-shot scan jobs map cleanly to session-per-run; sandboxing gives
  deny-by-default egress around untrusted documents; the event stream carries
  the full trajectory + token usage, which is exactly the raw material live
  eval needs.
- The owner already operates Arize cloud; Arize's online-eval tasks provide
  scheduled judge runs over sampled traces without any request-path coupling.

## Consequences

- The forwarder is a first-class component with its own tests; telemetry
  failure degrades to a warning, never a failed scan.
- Spans must set the `model_id` resource attribute — Arize's collector returns
  500 without it (verified in the ai-agents monorepo, 2026-07-15).
- `TELEMETRY_RECORD_IO=false` in production: no document text in Arize.
- Vendor coupling is confined to the forwarder + eval-task definitions; the
  span format is OpenInference/OTLP, so a backend swap is a config change.
