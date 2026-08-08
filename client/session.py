"""Managed Agents session driver.

Implements the documented client patterns: consolidation on connect (history
fetch + live stream, deduped by event id), the correct terminal gate (idle is
terminal only when stop_reason is not requires_action), custom-tool
round-trips with session_thread_id echo, and a post-idle status poll before
returning. Auth comes from the `ant auth login` profile — no env key.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from anthropic import Anthropic

from client.tools import handle_tool_call

WORKSPACE = "default"  # Console slug; this org's key lives in the Default workspace


@dataclass
class SessionOutcome:
    """What one driven session produced."""
    session_id: str
    events: list[Any] = field(default_factory=list)
    terminal: str = "unknown"  # end_turn | retries_exhausted | terminated

    def tool_uses(self, name: str | None = None) -> list[Any]:
        """All agent.tool_use / agent.custom_tool_use events, optionally by tool name."""
        out = []
        for e in self.events:
            if e.type in ("agent.tool_use", "agent.custom_tool_use"):
                if name is None or getattr(e, "name", None) == name:
                    out.append(e)
        return out

    def bash_commands(self) -> list[str]:
        """Every bash command the sandbox ran — the trajectory evidence."""
        cmds = []
        for e in self.tool_uses("bash"):
            command = (getattr(e, "input", None) or {}).get("command")
            if command:
                cmds.append(command)
        return cmds


def run_session(
    client: Anthropic,
    agent_id: str,
    agent_version: int,
    environment_id: str,
    document_path: str | Path,
    manifest: dict,
    conn: Any,
    mount_name: str | None = None,
) -> SessionOutcome:
    """Create, drive to terminal idle, and return one scan session."""
    doc = Path(document_path)
    uploaded = client.beta.files.upload(file=doc.open("rb"))
    mount_path = f"/workspace/inputs/{mount_name or doc.name}"
    # Empirical (smoke test 2026-08-07): file resources are mounted under
    # /mnt/session/uploads/<mount_path>, not at the literal mount_path.
    manifest = dict(manifest,
                    document_path=f"/mnt/session/uploads{mount_path}",
                    file_name=doc.name)

    session = client.beta.sessions.create(
        agent={"type": "agent", "id": agent_id, "version": agent_version},
        environment_id=environment_id,
        title=f"scan {manifest['scan_id']}",
        resources=[{"type": "file", "file_id": uploaded.id, "mount_path": mount_path}],
        initial_events=[{
            "type": "user.message",
            "content": [{"type": "text",
                         "text": "Job manifest:\n```json\n" + json.dumps(manifest, indent=2) + "\n```"}],
        }],
    )
    print(f"session {session.id} — trace: https://platform.claude.com/workspaces/{WORKSPACE}/sessions/{session.id}")

    outcome = SessionOutcome(session_id=session.id)
    seen: set[str] = set()

    def ingest(event: Any) -> None:
        if event.id in seen:
            return
        seen.add(event.id)
        outcome.events.append(event)
        if event.type == "agent.custom_tool_use":
            content, is_error = handle_tool_call(event.name, event.input or {}, conn)
            reply = {
                "type": "user.custom_tool_result",
                "custom_tool_use_id": event.id,
                "content": [{"type": "text", "text": content}],
                "is_error": is_error,
            }
            thread_id = getattr(event, "session_thread_id", None)
            if thread_id:
                reply["session_thread_id"] = thread_id
            client.beta.sessions.events.send(session.id, events=[reply])

    def terminal_of(event: Any) -> str | None:
        """Terminal state this event implies, or None. Must be checked in the
        history replay AND the live stream — a terminal event that arrived
        before the history fetch never re-appears on the stream, and waiting
        there hangs forever (bug found in the 2026-08-08 L2 rerun)."""
        if event.type == "session.status_terminated":
            return "terminated"
        if event.type == "session.status_idle":
            stop_type = getattr(getattr(event, "stop_reason", None), "type", None)
            if stop_type != "requires_action":
                return stop_type or "end_turn"
        return None

    # Consolidation: open the stream first, then replay history, then tail.
    stream = client.beta.sessions.events.stream(session_id=session.id)
    terminal: str | None = None
    for event in client.beta.sessions.events.list(session_id=session.id):
        ingest(event)
        terminal = terminal or terminal_of(event)
    if terminal is None:
        for event in stream:
            ingest(event)
            terminal = terminal_of(event)
            if terminal:
                break
    outcome.terminal = terminal or "unknown"

    # Post-idle status-write race: let the queryable status settle.
    for _ in range(10):
        if client.beta.sessions.retrieve(session.id).status != "running":
            break
        time.sleep(0.5)
    return outcome
