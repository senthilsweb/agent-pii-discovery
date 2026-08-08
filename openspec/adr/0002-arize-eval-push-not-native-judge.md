# ADR 0002 — Live judges run locally and push to Arize; not native Arize tasks

Date: 2026-08-08 · Status: accepted

## Decision

The six rubric criteria (R1–R6) are judged by our own code (`evals/judge/`),
never inside Arize itself, and the verdicts are pushed onto the matching
trace/span via the Arize SDK (`client.spans.update_evaluations()`). Arize's
native "online-eval task" UI is not used as the judging mechanism for R1–R4
and R6. It remains available for **R5 only**, as an optional, redundant
native path — not required once the push mechanism exists.

## Why

R2 (type accuracy), R3 (coverage), and R6 (no instruction-following) cannot
be judged without seeing the actual excerpt or document passage. Production
spans deliberately carry none of that (`TELEMETRY_RECORD_IO=false`, PRD §12,
ADR 0001) — the sandbox's only channel to the outside world for PII values is
the operational database, not the trace backend. Configuring Arize's native
judge to evaluate these criteria would require exporting document content
into spans, which reopens the exact exposure the architecture was built to
close.

R5 (sensitivity sanity) is the one criterion that needs only `canonical_type`
+ `sensitivity` grade — no value, no excerpt — so it's judgeable purely from
span attributes (`pii.sensitivity.<TYPE>`, added 2026-08-08) with zero
content ever reaching Arize. It was initially set up as a native Arize task
for exactly this reason.

## Consequences

- Once the local-judge push exists, it computes R5 the same way as the other
  five criteria (`evals/judge/runner.py` already calls `judge_sensitivity`).
  A native Arize task for R5 would then be a second, redundant evaluator
  under a different name, scored by a differently-configured judge with no
  shared calibration — not a second guarantee, just drift risk. **The native
  R5 task is therefore not required once the push mechanism ships; build one
  or the other, not both.**
- The Anthropic key needed for the judge model lives in our own environment
  only (`MODEL_JUDGE`), never inside an Arize AI Provider Integration.
- Arize still shows every criterion in the trace UI and still drives drift
  monitors and dashboards — it becomes purely the observability/monitoring
  surface, never an execution surface for judging.
- The push job runs off the request path (after `persist_result`, same as
  the trace forwarder), so live-eval cost and latency stay decoupled from
  scans exactly as PRD §10.4 requires.
