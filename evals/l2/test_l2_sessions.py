"""L2 offline agent evals — real Managed Agents sessions over corpus fixtures.

Phase 2 gate: trajectory + schema + grounding (rubrics §2 trajectory.eval,
schema_conformance.eval, grounding.eval). Detection floors are Phase 3's
comparison round. These spend real tokens and need the applied control plane
plus `ant auth login`, so they run only when RUN_L2=1:

    RUN_L2=1 PII_ENGINE=presidio .venv/bin/pytest evals/l2 -q

Assertions read artifacts: the session event log (bash commands = trajectory
evidence), the persisted DB row, and the validated result schema — never the
agent's prose.
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pytest

from pipeline import TAXONOMY_VERSION
from pipeline.checksum import compute_pipeline_version, sha256_file
from pipeline.schemas import DocumentResult
from pipeline.storage import db

pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_L2") != "1",
    reason="L2 drives real Managed Agents sessions; set RUN_L2=1 to run",
)

ROOT = Path(__file__).resolve().parent.parent.parent
CORPUS = ROOT / "evals" / "data"
TIER1 = {"EMAIL_ADDRESS", "PHONE_NUMBER", "GOVERNMENT_ID_SSN", "CREDIT_CARD_NUMBER", "IP_ADDRESS"}


@pytest.fixture(scope="module")
def driver():
    """One SDK client + in-memory DB shared across the module's sessions."""
    from anthropic import Anthropic

    ids = json.loads((ROOT / "agent" / "applied.json").read_text())
    return {"client": Anthropic(), "ids": ids, "conn": db.connect(":memory:")}


def _scan(driver, fixture_id: str, engine: str = "presidio"):
    """Drive one session for a fixture; return (outcome, persisted DocumentResult|None)."""
    from client.session import run_session

    doc = next((CORPUS / fixture_id).glob("document.*"))
    checksum = sha256_file(doc)
    manifest = {
        "scan_id": f"scan_l2_{uuid.uuid4().hex[:8]}",
        "checksum": checksum,
        "user_login": "l2-eval",
        "engine": engine,
        "models": [],
        "pipeline_version": compute_pipeline_version(engine, [], "", TAXONOMY_VERSION),
        "started_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "check_cache": False,
    }
    outcome = run_session(
        driver["client"],
        agent_id=driver["ids"]["orchestrator_id"],
        agent_version=int(driver["ids"]["orchestrator_version"]),
        environment_id=driver["ids"]["environment_id"],
        document_path=doc,
        manifest=manifest,
        conn=driver["conn"],
        mount_name=f"{fixture_id}{doc.suffix}",
    )
    row = driver["conn"].execute(
        "SELECT result_json FROM scans WHERE scan_id = ?", [manifest["scan_id"]]
    ).fetchone()
    result = DocumentResult.model_validate_json(row[0]) if row and row[0] else None
    return outcome, result


def _persist_calls(outcome):
    return [e for e in outcome.tool_uses("persist_result")]


# --- trajectory.eval -------------------------------------------------------

def test_columnar_reject_trajectory(driver):
    outcome, result = _scan(driver, "columnar_01")
    assert outcome.terminal == "end_turn"
    assert result is not None, "reject must still persist a result"
    assert result.document.processing_status == "skipped_out_of_scope"
    assert result.findings == []
    # HARD: no scan step ran after the gate
    cmds = " \n".join(outcome.bash_commands())
    for forbidden in ("steps.py extract", " extract ", " presidio", " normalize"):
        assert f"pipeline.steps --workdir /workspace/run{forbidden}" not in cmds
    assert "presidio" not in cmds.replace("agent-pii-discovery", "")
    assert len(_persist_calls(outcome)) == 1


def test_full_scan_trajectory_and_schema(driver):
    outcome, result = _scan(driver, "synthetic_prose_01")
    assert outcome.terminal == "end_turn"
    assert result is not None
    assert result.document.processing_status == "processed"
    assert result.document.chunk_count >= 1
    assert result.run.engine == "presidio"
    # step order appears in the bash trail
    cmds = outcome.bash_commands()
    def first_index(fragment):
        return next(i for i, c in enumerate(cmds) if fragment in c)
    assert first_index("classify") < first_index("extract") < first_index("chunk") \
        < first_index("presidio") < first_index("normalize") < first_index("assemble")
    assert len(_persist_calls(outcome)) == 1


# --- grounding.eval (HARD subset that needs no detection floor) ------------

def test_full_scan_grounding(driver):
    outcome, result = _scan(driver, "synthetic_prose_02")
    assert result is not None and result.document.processing_status == "processed"
    text = (CORPUS / "synthetic_prose_02" / "document.txt").read_text()
    for finding in result.findings:
        for excerpt in finding.sample_excerpts:
            assert excerpt in text, f"ungrounded excerpt for {finding.canonical_type}"


# --- clean fixture: Tier-1 false-positive floor (HARD) ---------------------

def test_clean_fixture_no_tier1_findings(driver):
    outcome, result = _scan(driver, "clean_01")
    assert result is not None and result.document.processing_status == "processed"
    tier1_found = {f.canonical_type for f in result.findings} & TIER1
    assert not tier1_found, f"Tier-1 false positives on clean doc: {tier1_found}"
