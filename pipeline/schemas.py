"""Pydantic models — the typed contract every pipeline stage speaks.

The result shapes mirror PRD §8; canonical_type values are validated against
the closed taxonomy so a schema-valid result can never carry an invented type.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator

from pipeline.taxonomy import CANONICAL_ENTITY_TYPES

Sensitivity = Literal["low", "medium", "high", "critical"]
StructuralClass = Literal["structured_columnar", "semi_structured", "unstructured", "unknown"]
ProcessingStatus = Literal["processed", "skipped_out_of_scope", "failed"]
SourceEngine = Literal["presidio", "genai"]

SENSITIVITY_RANK: dict[str, int] = {"low": 0, "medium": 1, "high": 2, "critical": 3}


class Span(BaseModel):
    """Character offsets of a finding within its chunk."""
    chunk_id: str
    start: int = Field(ge=0)
    end: int = Field(ge=0)


class RawFinding(BaseModel):
    """One pre-normalization finding, from either engine."""
    raw_label: str
    value_excerpt: str = Field(max_length=200)
    span: Span | None = None
    confidence: float = Field(ge=0.0, le=1.0)
    sensitivity: Sensitivity
    source_engine: SourceEngine
    source_model: str | None = None
    chunk_id: str


class NormalizedFinding(BaseModel):
    """One canonical type's roll-up across engines and models."""
    canonical_type: str
    raw_labels_seen: list[str]
    occurrences: int = Field(ge=1)
    chunk_ids: list[str]
    sample_excerpts: list[str] = Field(max_length=5)
    spans: list[Span] = Field(default_factory=list, max_length=20)
    normalized_value: str | None = None
    max_confidence: float = Field(ge=0.0, le=1.0)
    sensitivity: Sensitivity
    source_engines: list[SourceEngine]
    source_models: list[str] = Field(default_factory=list)

    @field_validator("canonical_type")
    @classmethod
    def _known_type(cls, v: str) -> str:
        if v not in CANONICAL_ENTITY_TYPES:
            raise ValueError(f"not a canonical entity type: {v}")
        return v


class ComplianceHit(BaseModel):
    """One implicated regime and what triggered it."""
    jurisdiction: str
    regulation_name: str
    triggered_by: list[str]
    severity: Literal["informational", "moderate", "high"]


class ComplianceImpact(BaseModel):
    """Regime lookup output — pure table math, never model output."""
    impacted_jurisdictions: list[str]
    hits: list[ComplianceHit]
    regime_matrix_version: str


class DocumentMeta(BaseModel):
    """What we know about the document independent of any scan."""
    source_path: str
    file_name: str
    file_type: str
    size_bytes: int
    page_count: int | None = None
    structural_class: StructuralClass
    processing_status: ProcessingStatus
    ocr_enabled: bool = False
    extraction_method: Literal["text_layer", "ocr", "none"] = "none"
    chunk_count: int = 0
    reason: str | None = None


class RunInfo(BaseModel):
    """Identity + timing of one scan run."""
    scan_id: str
    session_id: str | None = None
    pipeline_version: str
    engine: str
    models: list[str] = Field(default_factory=list)
    started_at: str
    ended_at: str | None = None


class DocumentResult(BaseModel):
    """The one result artifact per scan — persisted to DB and mirrored to S3."""
    checksum: str
    user_login: str
    document: DocumentMeta
    findings: list[NormalizedFinding]
    compliance_impact: ComplianceImpact
    run: RunInfo
