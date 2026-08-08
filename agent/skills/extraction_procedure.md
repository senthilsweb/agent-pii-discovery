# Skill: extraction_procedure

How to turn an uploaded document into scan-ready chunks. Load before the first
extraction step of a full scan.

## Order of operations

1. **Structure gate first.** Run `pipeline/classify_structure.py <file>`.
   Output `structured_columnar` ⇒ stop and take the columnar-reject trajectory.
   Only `unstructured` / `semi_structured` proceed.
2. **Text layer.** Run `pipeline/extract_text.py <file>`. It tries the native
   text layer (PDF/DOCX/TXT) first and reports `extraction_method: text_layer`
   with a character count.
3. **OCR fallback.** If the text layer yields fewer than 50 non-whitespace
   characters for a PDF/image, rerun with `--ocr`. Record
   `extraction_method: ocr` and `ocr_enabled: true`. Never OCR a file that
   already produced a usable text layer.
4. **Chunk.** Run `pipeline/chunk_text.py` on the extracted text. Chunk ids are
   stable (`chunk_0001`, …) — downstream findings cite them, so never re-chunk
   after detection has started.

## Rules

- Extraction and chunking are scripts; do not paraphrase, summarize, or "clean
  up" document text yourself.
- A scanned image that OCR cannot read (still < 50 chars) is a failed
  extraction: assemble a `failed` result with reason `unreadable_document`.
- Report only counts and metadata (method, chunk count, char count) back to the
  orchestrator thread — never the text itself.
