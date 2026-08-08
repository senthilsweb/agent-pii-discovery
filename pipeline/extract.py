"""Text extraction: native text layer first, OCR fallback second.

The rule from agent/skills/extraction_procedure.md: try the text layer, fall
back to OCR only when a PDF/image yields fewer than 50 non-whitespace chars,
and fail plainly (`unreadable_document`) rather than guess. Heavy dependencies
(pypdf, pytesseract/Pillow) import lazily so L1 unit tests need neither.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

_MIN_TEXT_CHARS = 50


class ExtractionError(Exception):
    """Raised with a machine-usable reason ('unreadable_document', ...)."""

    def __init__(self, reason: str, detail: str = "") -> None:
        self.reason = reason
        super().__init__(f"{reason}: {detail}" if detail else reason)


@dataclass
class Extraction:
    """What extraction produced and how."""
    text: str
    method: str  # "text_layer" | "ocr"
    ocr_enabled: bool
    page_count: int | None = None


def _usable(text: str) -> bool:
    return len("".join(text.split())) >= _MIN_TEXT_CHARS


def _extract_pdf_text(path: Path) -> tuple[str, int]:
    from pypdf import PdfReader  # lazy: optional [extract] dependency

    reader = PdfReader(str(path))
    return "\n".join((page.extract_text() or "") for page in reader.pages), len(reader.pages)


def _extract_ocr(path: Path) -> str:
    import pytesseract  # lazy: optional [extract] dependency
    from PIL import Image

    return pytesseract.image_to_string(Image.open(path))


def extract_text(path: str | Path) -> Extraction:
    """Extract scan-ready text or raise ExtractionError with a reason."""
    p = Path(path)
    ext = p.suffix.lower()

    if ext in {".txt", ".md", ".text"}:
        text = p.read_text(encoding="utf-8")
        if not text.strip():
            raise ExtractionError("empty_document", str(p))
        return Extraction(text=text, method="text_layer", ocr_enabled=False)

    if ext == ".pdf":
        text, pages = _extract_pdf_text(p)
        if _usable(text):
            return Extraction(text=text, method="text_layer", ocr_enabled=False, page_count=pages)
        # Scanned PDF: page-image OCR is a Phase 2+ concern; fail plainly now.
        raise ExtractionError("unreadable_document", f"pdf text layer <{_MIN_TEXT_CHARS} chars")

    if ext in {".png", ".jpg", ".jpeg", ".tif", ".tiff"}:
        text = _extract_ocr(p)
        if _usable(text):
            return Extraction(text=text, method="ocr", ocr_enabled=True)
        raise ExtractionError("unreadable_document", f"ocr yielded <{_MIN_TEXT_CHARS} chars")

    raise ExtractionError("unsupported_file_type", ext or "no extension")
