# Skill: extraction_procedure

How to turn an uploaded document into scan-ready chunks. Load before the first
extraction step of a full scan. All commands run from
`/workspace/agent-pii-discovery` with `--workdir /workspace/run`.

## Order of operations

1. **Structure gate first.**
   `python3 -m pipeline.steps --workdir /workspace/run classify <document>`
   Output `structured_columnar` ⇒ stop and take the columnar-reject trajectory.
   Only `unstructured` / `semi_structured` / `unknown` proceed.
2. **Text layer + OCR fallback.**
   `python3 -m pipeline.steps --workdir /workspace/run extract <document>`
   The step handles the fallback internally (text layer first; OCR only for
   images; < 50 non-whitespace chars ⇒ exit code 2 with a reason such as
   `unreadable_document`). Exit 2 ⇒ stop and take the failed trajectory with
   that reason.
3. **Chunk.**
   `python3 -m pipeline.steps --workdir /workspace/run chunk`
   Chunk ids are stable (`chunk_0001`, …) — downstream findings cite them, so
   never re-run chunking after detection has started.

## Rules

- Extraction and chunking are pipeline steps; never paraphrase, summarize, or
  "clean up" document text yourself, and never re-implement a step in ad-hoc
  bash or Python.
- Step stdout is counts and metadata only — report exactly that upward;
  never open `extracted.txt` or `chunks.json` in a message.
- One extract attempt; the step's own fallback is the only retry that exists.
