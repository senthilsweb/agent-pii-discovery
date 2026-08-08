"""Session events → OpenInference spans → Arize AX (Phase 4).

The trace forwarder this project exists to learn from. Managed Agents has no
native OTel export — tracing surfaces as the session event stream — so this
module converts a session's events into OpenInference-conventioned OTel spans
and ships them over OTLP/HTTP. Runs after the session, off the request path;
a missing or unreachable backend degrades to one logged warning (never a
failed scan). Works on archived sessions too — event history is a free read.

Hard-won rules baked in (verified in the ai-agents monorepo, 2026-07-15):
- Arize AX's collector returns 500 for spans whose Resource lacks `model_id`.
- TELEMETRY_RECORD_IO=false (the default) keeps document text out of spans:
  attributes carry names, counts, tokens, and ids only.

Span mapping:
    session                      → AGENT root span `pii_scan.session`
    span.model_request_start/end → LLM child (token counts from model_usage)
    agent.tool_use / tool_result → TOOL child (duration from the result event)
    agent.custom_tool_use        → TOOL child (host-side tools)
    persist_result payload       → per-type finding counts on the root span
"""

from __future__ import annotations

import json
import logging
import os
import sys
from datetime import datetime, timezone
from typing import Any

log = logging.getLogger("pii.forwarder")

SERVICE_NAME = "agent-pii-discovery"
_ARIZE_ENDPOINT = "https://otlp.arize.com/v1/traces"


# --- small helpers over SDK objects OR plain dicts -------------------------

def _get(e: Any, key: str, default=None):
    if isinstance(e, dict):
        return e.get(key, default)
    return getattr(e, key, default)


def _ns(ts: Any) -> int | None:
    """processed_at (datetime or ISO string) → epoch nanoseconds."""
    if ts is None:
        return None
    if isinstance(ts, str):
        ts = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return int(ts.timestamp() * 1_000_000_000)


def _record_io() -> bool:
    return os.environ.get("TELEMETRY_RECORD_IO", "false").lower() == "true"


# --- exporter wiring -------------------------------------------------------

def build_exporters() -> list:
    """One OTLP/HTTP exporter per configured backend; empty list = no-op.

    Arize AX (ARIZE_SPACE_ID + ARIZE_API_KEY) and/or any generic OTLP target
    (OTEL_EXPORTER_OTLP_ENDPOINT [+_HEADERS]) and/or a local dev Phoenix
    (PHOENIX_COLLECTOR_ENDPOINT). Each fails independently.
    """
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

    exporters = []
    space, key = os.environ.get("ARIZE_SPACE_ID"), os.environ.get("ARIZE_API_KEY")
    if space and key:
        exporters.append(OTLPSpanExporter(
            endpoint=_ARIZE_ENDPOINT, headers={"space_id": space, "api_key": key}))
    generic = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT")
    if generic:
        hdrs = dict(h.split("=", 1) for h in
                    os.environ.get("OTEL_EXPORTER_OTLP_HEADERS", "").split(",") if "=" in h)
        exporters.append(OTLPSpanExporter(
            endpoint=generic.rstrip("/") + "/v1/traces", headers=hdrs or None))
    phoenix = os.environ.get("PHOENIX_COLLECTOR_ENDPOINT")
    if phoenix:
        exporters.append(OTLPSpanExporter(endpoint=phoenix.rstrip("/") + "/v1/traces"))
    return exporters


def _provider(exporters: list):
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    # model_id is REQUIRED by Arize AX — its collector 500s without it.
    provider = TracerProvider(resource=Resource.create(
        {"service.name": SERVICE_NAME, "model_id": SERVICE_NAME}))
    for exp in exporters:
        provider.add_span_processor(BatchSpanProcessor(exp))
    return provider


# --- the mapping -----------------------------------------------------------

def forward_session(events: list, scan_meta: dict | None = None,
                    provider=None) -> int:
    """Convert one session's events into spans; returns the span count.

    `provider` is injectable for tests (in-memory exporter); when None, one is
    built from env and force-flushed before returning. With no backend
    configured this logs one warning and returns 0.
    """
    own_provider = provider is None
    if own_provider:
        exporters = build_exporters()
        if not exporters:
            log.warning("forwarder: no telemetry backend configured "
                        "(ARIZE_SPACE_ID/ARIZE_API_KEY, OTEL_EXPORTER_OTLP_ENDPOINT, "
                        "or PHOENIX_COLLECTOR_ENDPOINT) — skipping")
            return 0
        provider = _provider(exporters)
    tracer = provider.get_tracer("pii.forwarder")

    times = [_ns(_get(e, "processed_at")) for e in events]
    times = [t for t in times if t]
    if not times:
        return 0
    t_start, t_end = min(times), max(times)

    meta = dict(scan_meta or {})
    # the persist payload is the authoritative result summary
    for e in events:
        if _get(e, "type") == "agent.custom_tool_use" and _get(e, "name") == "persist_result":
            try:
                result = json.loads(_get(e, "input")["result_json"])
                meta.setdefault("scan_id", result["run"]["scan_id"])
                meta.setdefault("engine", result["run"]["engine"])
                meta.setdefault("status", result["document"]["processing_status"])
                meta["findings_total"] = sum(f["occurrences"] for f in result["findings"])
                for f in result["findings"]:
                    meta[f"pii.findings.{f['canonical_type']}"] = f["occurrences"]
            except Exception:  # noqa: BLE001 — telemetry never throws
                pass

    count = 0
    root = tracer.start_span("pii_scan.session", start_time=t_start)
    root.set_attribute("openinference.span.kind", "AGENT")
    for k, v in meta.items():
        if v is not None:
            root.set_attribute(str(k), v)

    from opentelemetry import trace as trace_api
    ctx = trace_api.set_span_in_context(root)

    # LLM spans: pair model_request_start/end by id
    starts = {_get(e, "id"): e for e in events if _get(e, "type") == "span.model_request_start"}
    for e in events:
        if _get(e, "type") != "span.model_request_end":
            continue
        start_ev = starts.get(_get(e, "model_request_start_id"))
        s_t = _ns(_get(start_ev, "processed_at")) if start_ev else _ns(_get(e, "processed_at"))
        span = tracer.start_span("llm.request", context=ctx, start_time=s_t or t_start)
        span.set_attribute("openinference.span.kind", "LLM")
        usage = _get(e, "model_usage")
        if usage:
            prompt = (_get(usage, "input_tokens", 0) or 0) + \
                     (_get(usage, "cache_read_input_tokens", 0) or 0) + \
                     (_get(usage, "cache_creation_input_tokens", 0) or 0)
            completion = _get(usage, "output_tokens", 0) or 0
            span.set_attribute("llm.token_count.prompt", prompt)
            span.set_attribute("llm.token_count.completion", completion)
            span.set_attribute("llm.token_count.total", prompt + completion)
        if _get(e, "is_error"):
            span.set_attribute("error", True)
        span.end(end_time=_ns(_get(e, "processed_at")) or t_end)
        count += 1

    # TOOL spans: duration from the next matching result event, else zero
    result_types = {"agent.tool_result", "user.custom_tool_result"}
    for i, e in enumerate(events):
        etype = _get(e, "type")
        if etype not in ("agent.tool_use", "agent.custom_tool_use"):
            continue
        s_t = _ns(_get(e, "processed_at"))
        e_t = s_t
        for later in events[i + 1:]:
            if _get(later, "type") in result_types:
                e_t = _ns(_get(later, "processed_at")) or s_t
                break
        name = _get(e, "name", "tool")
        span = tracer.start_span(f"tool.{name}", context=ctx, start_time=s_t or t_start)
        span.set_attribute("openinference.span.kind", "TOOL")
        span.set_attribute("tool.name", name)
        span.set_attribute("tool.host_side", etype == "agent.custom_tool_use")
        tool_input = _get(e, "input")
        if _record_io() and tool_input is not None:
            span.set_attribute("input.value", json.dumps(tool_input, default=str)[:4000])
        thread = _get(e, "session_thread_id")
        if thread:
            span.set_attribute("session.thread_id", str(thread))
        span.end(end_time=e_t or t_end)
        count += 1

    root.end(end_time=t_end)
    count += 1

    if own_provider:
        provider.force_flush()
        provider.shutdown()
    return count


def main(argv: list[str] | None = None) -> int:
    """CLI: forward a (possibly archived) session by id — a free API read."""
    import argparse

    from anthropic import Anthropic

    parser = argparse.ArgumentParser(description="Forward session events to Arize/OTLP")
    parser.add_argument("session_id")
    parser.add_argument("--user", default=None)
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    client = Anthropic()
    events = list(client.beta.sessions.events.list(session_id=args.session_id))
    meta = {"session_id": args.session_id}
    if args.user:
        meta["user_login"] = args.user
    n = forward_session(events, scan_meta=meta)
    print(json.dumps({"session_id": args.session_id, "events": len(events), "spans": n}))
    return 0 if n else 1


if __name__ == "__main__":
    sys.exit(main())
