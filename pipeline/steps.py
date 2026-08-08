"""Step-level CLI for the sandboxed agent — one subcommand per pipeline stage.

The orchestrator drives these via bash inside the Managed Agents sandbox, so
each stage is separately observable in the trace (trajectory evals depend on
that). Steps communicate through JSON artifacts in a workdir and print ONLY
counts and metadata to stdout — never document text or finding values (the
monorepo's counts-only tool-return rule).

Workdir convention:
    manifest.json      written by the agent from the kickoff message
    structure.json     classify
    extracted.txt      extract (the text itself — stays on disk)
    extract_info.json  extract
    chunks.json        chunk
    raw_findings.json  presidio
    findings.json      normalize
    result.json        assemble
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from pipeline.chunking import Chunk, chunk_text
from pipeline.compliance import map_compliance_impact
from pipeline.extract import ExtractionError, extract_text
from pipeline.normalize import normalize_findings
from pipeline.schemas import DocumentMeta, DocumentResult, RawFinding, RunInfo
from pipeline.structure import classify_structure


def _read(workdir: Path, name: str):
    return json.loads((workdir / name).read_text())


def _write(workdir: Path, name: str, payload) -> None:
    (workdir / name).write_text(json.dumps(payload, indent=2))


def _emit(payload: dict) -> None:
    """The step's stdout contract: counts and metadata only."""
    print(json.dumps(payload))


def step_classify(workdir: Path, file: str) -> None:
    p = Path(file)
    sample = None
    if p.suffix.lower() in {".txt", ".md", ".text"}:
        sample = p.read_text(encoding="utf-8", errors="ignore")[:4096]
    cls = classify_structure(p, sample_text=sample)
    _write(workdir, "structure.json", {"structural_class": cls, "file": str(p)})
    _emit({"structural_class": cls})


def step_extract(workdir: Path, file: str) -> None:
    try:
        ex = extract_text(file)
    except ExtractionError as exc:
        _write(workdir, "extract_info.json", {"failed": True, "reason": exc.reason})
        _emit({"failed": True, "reason": exc.reason})
        raise SystemExit(2)
    (workdir / "extracted.txt").write_text(ex.text)
    info = {"method": ex.method, "ocr_enabled": ex.ocr_enabled,
            "page_count": ex.page_count, "chars": len(ex.text)}
    _write(workdir, "extract_info.json", info)
    _emit(info)


def step_chunk(workdir: Path) -> None:
    text = (workdir / "extracted.txt").read_text()
    chunks = chunk_text(text)
    _write(workdir, "chunks.json",
           [{"chunk_id": c.chunk_id, "text": c.text, "doc_start": c.doc_start} for c in chunks])
    _emit({"chunk_count": len(chunks)})


def step_presidio(workdir: Path) -> None:
    from pipeline.presidio_scan import get_analyzer, scan_with

    text = (workdir / "extracted.txt").read_text()
    chunks = [Chunk(**c) for c in _read(workdir, "chunks.json")]
    findings = scan_with(get_analyzer(), text, chunks)
    _write(workdir, "raw_findings.json", [f.model_dump() for f in findings])
    _emit({"engine": "presidio", "finding_count": len(findings)})


def step_normalize(workdir: Path) -> None:
    raw = [RawFinding.model_validate(f) for f in _read(workdir, "raw_findings.json")]
    normalized = normalize_findings(raw)
    _write(workdir, "findings.json", [f.model_dump() for f in normalized])
    _emit({"types": {f.canonical_type: f.occurrences for f in normalized}})


def step_assemble(workdir: Path, status: str, reason: str | None) -> None:
    manifest = _read(workdir, "manifest.json")
    structure = _read(workdir, "structure.json") if (workdir / "structure.json").exists() else {}
    p = Path(manifest["document_path"])

    meta_kwargs: dict = {
        "source_path": manifest["document_path"],
        "file_name": manifest["file_name"],
        "file_type": p.suffix.lstrip(".").lower() or "unknown",
        "size_bytes": p.stat().st_size if p.exists() else 0,
        "structural_class": structure.get("structural_class", "unknown"),
        "processing_status": status,
        "reason": reason,
    }
    findings = []
    if status == "processed":
        info = _read(workdir, "extract_info.json")
        chunks = _read(workdir, "chunks.json")
        meta_kwargs.update(
            page_count=info.get("page_count"), ocr_enabled=info["ocr_enabled"],
            extraction_method=info["method"], chunk_count=len(chunks),
        )
        findings = _read(workdir, "findings.json")

    result = DocumentResult(
        checksum=manifest["checksum"],
        user_login=manifest["user_login"],
        document=DocumentMeta(**meta_kwargs),
        findings=findings,
        compliance_impact=map_compliance_impact([f["canonical_type"] for f in findings]),
        run=RunInfo(
            scan_id=manifest["scan_id"],
            session_id=manifest.get("session_id"),
            pipeline_version=manifest["pipeline_version"],
            engine=manifest["engine"],
            models=manifest.get("models", []),
            started_at=manifest["started_at"],
            ended_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        ),
    )
    (workdir / "result.json").write_text(result.model_dump_json(indent=2))
    _emit({"status": status,
           "types": {f.canonical_type: f.occurrences for f in result.findings},
           "jurisdictions": result.compliance_impact.impacted_jurisdictions})


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="pipeline.steps")
    parser.add_argument("--workdir", default=".")
    sub = parser.add_subparsers(dest="step", required=True)
    sub.add_parser("classify").add_argument("file")
    sub.add_parser("extract").add_argument("file")
    sub.add_parser("chunk")
    sub.add_parser("presidio")
    sub.add_parser("normalize")
    asm = sub.add_parser("assemble")
    asm.add_argument("--status", default="processed",
                     choices=["processed", "skipped_out_of_scope", "failed"])
    asm.add_argument("--reason", default=None)
    args = parser.parse_args(argv)

    workdir = Path(args.workdir)
    workdir.mkdir(parents=True, exist_ok=True)
    if args.step == "classify":
        step_classify(workdir, args.file)
    elif args.step == "extract":
        step_extract(workdir, args.file)
    elif args.step == "chunk":
        step_chunk(workdir)
    elif args.step == "presidio":
        step_presidio(workdir)
    elif args.step == "normalize":
        step_normalize(workdir)
    elif args.step == "assemble":
        step_assemble(workdir, args.status, args.reason)
    return 0


if __name__ == "__main__":
    sys.exit(main())
