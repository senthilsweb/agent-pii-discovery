"""The columnar gate — structured files are rejected before any scan.

Columnar data (CSV/spreadsheets) is out of scope by design: column-level PII
classification is a different product. The gate must run before extraction so
the reject trajectory touches no scan tool (a HARD trajectory eval).
"""

from __future__ import annotations

from pathlib import Path

from pipeline.schemas import StructuralClass

_COLUMNAR_EXTENSIONS = {".csv", ".tsv", ".xlsx", ".xls", ".parquet"}
_TEXTUAL_EXTENSIONS = {".txt", ".md", ".text"}
_DOCUMENT_EXTENSIONS = {".pdf", ".docx"}
_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".tif", ".tiff"}


def _looks_delimited(text: str) -> bool:
    """Heuristic for extensionless/misnamed exports: consistent delimiter
    counts across the first lines is a table, not prose."""
    lines = [ln for ln in text.splitlines()[:10] if ln.strip()]
    if len(lines) < 3:
        return False
    for delim in (",", "\t", ";", "|"):
        counts = [ln.count(delim) for ln in lines]
        if counts[0] >= 2 and len(set(counts)) == 1:
            return True
    return False


def classify_structure(path: str | Path, sample_text: str | None = None) -> StructuralClass:
    """Classify a file for the gate. `sample_text` lets .txt content override
    the extension when the content is plainly a delimited table."""
    ext = Path(path).suffix.lower()
    if ext in _COLUMNAR_EXTENSIONS:
        return "structured_columnar"
    if ext in _TEXTUAL_EXTENSIONS:
        if sample_text is not None and _looks_delimited(sample_text):
            return "structured_columnar"
        return "unstructured"
    if ext in _DOCUMENT_EXTENSIONS:
        return "semi_structured"
    if ext in _IMAGE_EXTENSIONS:
        return "unstructured"
    return "unknown"


def is_in_scope(structural_class: StructuralClass) -> bool:
    """Only non-columnar documents proceed to extraction."""
    return structural_class != "structured_columnar"
