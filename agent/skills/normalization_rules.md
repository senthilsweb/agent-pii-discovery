# Skill: normalization_rules

How to interpret normalizer output. Normalization itself is
`pipeline/normalize_findings.py` — pure code, no LLM. This skill exists so the
orchestrator and report-assembler read its output correctly; none of these
rules are yours to apply by hand.

## What the normalizer guarantees

- Every raw finding (Presidio or GenAI, any model) maps to one of the **36
  canonical entity types** via the alias table (`config/label_aliases.yaml`).
  Unrecognized labels become `UNKNOWN` — never an error, never a new type.
- Findings roll up per canonical type: occurrence count, union of chunk ids,
  union of `source_engines` and `source_models`, `max_confidence`, and **max**
  sensitivity (rank: low < medium < high < critical).
- Sample excerpts are capped at 5 per type; each is a verbatim substring of its
  source chunk (the grounding invariant — evals enforce it).
- Output is sorted by canonical type; `normalized_value` present only where a
  canonical form is computable (lowercased email, E.164 phone).

## Rules for consumers

- Never rename, merge, or re-grade types in prose. If the normalizer says
  `UNKNOWN`, the report says `UNKNOWN`.
- Compliance impact comes from `config/compliance_matrix.yaml` lookup already
  embedded in the result — quote it, never derive regimes yourself.
- Cross-model comparison reads `source_models` on each rolled-up finding; a
  type found by one model and not another is signal, not an error to repair.
