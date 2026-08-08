"""Forwarder mapping: events → OpenInference spans, verified in-memory."""

import json

import pytest

from client.forwarder import build_exporters, forward_session


@pytest.fixture
def in_memory_provider():
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
        InMemorySpanExporter,
    )

    exporter = InMemorySpanExporter()
    provider = TracerProvider(resource=Resource.create(
        {"service.name": "agent-pii-discovery", "model_id": "agent-pii-discovery"}))
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    return provider, exporter


EVENTS = [
    {"type": "session.status_running", "id": "e1", "processed_at": "2026-08-08T00:00:00+00:00"},
    {"type": "span.model_request_start", "id": "e2", "processed_at": "2026-08-08T00:00:01+00:00"},
    {"type": "span.model_request_end", "id": "e3", "model_request_start_id": "e2",
     "processed_at": "2026-08-08T00:00:05+00:00", "is_error": False,
     "model_usage": {"input_tokens": 10, "output_tokens": 200,
                     "cache_read_input_tokens": 5000, "cache_creation_input_tokens": 100}},
    {"type": "agent.tool_use", "id": "e4", "name": "bash",
     "input": {"command": "echo secret-document-text"},
     "processed_at": "2026-08-08T00:00:06+00:00"},
    {"type": "agent.tool_result", "id": "e5", "processed_at": "2026-08-08T00:00:09+00:00"},
    {"type": "agent.custom_tool_use", "id": "e6", "name": "persist_result",
     "input": {"scan_id": "scan_x", "result_json": json.dumps({
         "run": {"scan_id": "scan_x", "engine": "presidio"},
         "document": {"processing_status": "processed"},
         "findings": [{"canonical_type": "EMAIL_ADDRESS", "occurrences": 3,
                       "sensitivity": "medium"},
                      {"canonical_type": "PERSON_NAME", "occurrences": 2,
                       "sensitivity": "medium"}],
     })},
     "processed_at": "2026-08-08T00:00:10+00:00"},
    {"type": "user.custom_tool_result", "id": "e7", "processed_at": "2026-08-08T00:00:11+00:00"},
    {"type": "session.status_idle", "id": "e8", "processed_at": "2026-08-08T00:00:12+00:00"},
]


def test_span_mapping(in_memory_provider):
    provider, exporter = in_memory_provider
    n = forward_session(EVENTS, scan_meta={"session_id": "sesn_1", "user_login": "u"},
                        provider=provider)
    provider.force_flush()
    spans = {s.name: s for s in exporter.get_finished_spans()}
    assert n == len(spans) == 4  # root + llm + 2 tools

    root = spans["pii_scan.session"]
    assert root.attributes["openinference.span.kind"] == "AGENT"
    assert root.attributes["pii.findings.EMAIL_ADDRESS"] == 3
    assert root.attributes["pii.sensitivity.EMAIL_ADDRESS"] == "medium"
    assert root.attributes["findings_total"] == 5
    assert root.attributes["engine"] == "presidio"
    assert root.attributes["status"] == "processed"

    llm = spans["llm.request"]
    assert llm.attributes["openinference.span.kind"] == "LLM"
    assert llm.attributes["llm.token_count.prompt"] == 5110
    assert llm.attributes["llm.token_count.completion"] == 200
    assert (llm.end_time - llm.start_time) == 4_000_000_000  # start paired by id

    bash = spans["tool.bash"]
    assert bash.attributes["tool.name"] == "bash"
    assert not bash.attributes["tool.host_side"]
    persist = spans["tool.persist_result"]
    assert persist.attributes["tool.host_side"]

    # resource carries the Arize-required model_id
    assert root.resource.attributes["model_id"] == "agent-pii-discovery"


def test_record_io_off_keeps_document_text_out(in_memory_provider, monkeypatch):
    monkeypatch.setenv("TELEMETRY_RECORD_IO", "false")
    provider, exporter = in_memory_provider
    forward_session(EVENTS, provider=provider)
    provider.force_flush()
    for s in exporter.get_finished_spans():
        assert "input.value" not in s.attributes  # no tool inputs → no doc text


def test_record_io_on_includes_inputs(in_memory_provider, monkeypatch):
    monkeypatch.setenv("TELEMETRY_RECORD_IO", "true")
    provider, exporter = in_memory_provider
    forward_session(EVENTS, provider=provider)
    provider.force_flush()
    bash = next(s for s in exporter.get_finished_spans() if s.name == "tool.bash")
    assert "secret-document-text" in bash.attributes["input.value"]


def test_no_backend_is_a_warning_not_a_crash(monkeypatch, caplog):
    for var in ("ARIZE_SPACE_ID", "ARIZE_API_KEY",
                "OTEL_EXPORTER_OTLP_ENDPOINT", "PHOENIX_COLLECTOR_ENDPOINT"):
        monkeypatch.delenv(var, raising=False)
    assert build_exporters() == []
    assert forward_session(EVENTS) == 0  # logs one warning, returns


def test_arize_exporter_configured_from_env(monkeypatch):
    monkeypatch.setenv("ARIZE_SPACE_ID", "space123")
    monkeypatch.setenv("ARIZE_API_KEY", "key123")
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_ENDPOINT", raising=False)
    monkeypatch.delenv("PHOENIX_COLLECTOR_ENDPOINT", raising=False)
    exporters = build_exporters()
    assert len(exporters) == 1
    assert "otlp.arize.com" in exporters[0]._endpoint
