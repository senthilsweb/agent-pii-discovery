"""Host-side custom tool handlers — the credential boundary.

These run in the client process, not the sandbox: DB and S3 access happen
here, so the session container never holds a cloud credential. Every handler
returns (json_string, is_error) and must never raise — a tool failure is a
result the agent handles, not a client crash.
"""

from __future__ import annotations

import json
from datetime import date
from typing import Any

from pipeline.schemas import DocumentResult
from pipeline.storage import db, s3


def handle_tool_call(name: str, tool_input: dict, conn: Any) -> tuple[str, bool]:
    """Dispatch one agent.custom_tool_use to its handler."""
    try:
        if name == "cache_lookup":
            return _cache_lookup(conn, tool_input)
        if name == "persist_result":
            return _persist_result(conn, tool_input)
        if name == "detect_pii_genai":
            return json.dumps({"error": "the GenAI path lands in Phase 3"}), True
        return json.dumps({"error": f"unknown tool: {name}"}), True
    except Exception as exc:  # noqa: BLE001 — reported to the agent, never fatal
        return json.dumps({"error": str(exc)}), True


def _cache_lookup(conn: Any, tool_input: dict) -> tuple[str, bool]:
    cached = db.cache_lookup(conn, tool_input["checksum"], tool_input["pipeline_version"])
    if cached is None:
        return json.dumps({"hit": False}), False
    return json.dumps({"hit": True, "result_json": cached.model_dump_json()}), False


def _persist_result(conn: Any, tool_input: dict) -> tuple[str, bool]:
    result = DocumentResult.model_validate_json(tool_input["result_json"])
    if result.run.scan_id != tool_input.get("scan_id"):
        return json.dumps({"error": "scan_id mismatch with result.json"}), True
    db.upsert_document(conn, result, s3_key=None)
    db.insert_scan(conn, result)
    s3.put_bytes(  # env-gated no-op without a bucket
        result.model_dump_json(indent=2).encode(),
        s3.result_key(result.user_login, date.today(), result.checksum),
    )
    return json.dumps({"ok": True, "scan_id": result.run.scan_id}), False
