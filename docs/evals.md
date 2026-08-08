# Evals

At the end you will know the four evaluation layers, what the labeled corpus
contains, and how "correct" is defined before any pipeline code exists.

The eval harness is the point of this project, not an afterthought: rubrics
were written at Inception (before the code), every phase exits through an
eval gate, and the live layer scores real production traffic in Arize AX.
The authoritative rubric document is
[`evals/rubrics.md`](https://github.com/senthilsweb/agent-pii-discovery/blob/main/evals/rubrics.md)
— HARD criteria fail promotion, SOFT criteria log warnings, amendments only
via dated in-place corrections.

## The four layers

| Layer | What it is | Needs | Gate |
|---|---|---|---|
| L1 — Unit tests | pytest over deterministic code: normalizer, alias table, compliance matrix, checksum, cache key, corpus integrity | No network, no model, no key | Every push |
| L2 — Offline agent evals | Real Managed Agents sessions over the labeled corpus; asserts P/R/F1 vs labels, trajectory, schema, grounding, injection resistance — on artifacts, never prose | Labeled corpus + live session | `implemented` |
| L3 — Judge calibration | The rubric judges scored against human-labeled findings; ≥ 90% agreement per criterion before a judge runs live | Calibration set | `verified`, judge deploy |
| L4 — Live regression | Arize online-eval tasks over sampled production traces: judge rubric R1–R6, drift (PSI/KS vs frozen offline baseline), cost monitors | Production traffic | Continuous |

## The labeled corpus

29 synthetic fixtures under `evals/data/`, one directory per fixture with the
document and a `labels.json` sidecar. Generated deterministically by
`evals/corpus/generate.py` (fixed seed; running it twice produces
byte-identical output), and — the load-bearing property — **char spans are
recorded at composition time**, never recovered by searching the text
afterwards, so the grounding evals inherit exact labels.

| Group | Count | Exercises |
|---|---|---|
| `synthetic_prose_01..12` | 12 | P/R/F1 per type — HR letter, clinical note, support thread, loan application, insurance claim, school enrollment, IT incident, travel booking, vehicle record, membership form, genetics report, crypto KYC |
| `synthetic_ocr_01..03` | 3 | OCR fallback — PNG renders of prose fixtures; spans null, matched by value |
| `columnar_01..02` | 2 | Reject path — structure gate fires, no scan tools called |
| `clean_01..04` | 4 | False-positive floor — zero PII by construction |
| `injection_01..04` | 4 | Injection resistance — embedded adversarial instructions, span-marked |
| `idiom_01..04` | 4 | Long-tail recall — fax-block phone, card-last-four, `.co.uk` email, `+44 (0)` phone |

Coverage: **all 35 plantable canonical types** appear across the prose
fixtures — 106 labeled spans total; Tier-1 types appear in 4–9 fixtures each,
including same-value duplicates within a document (the occurrence-counting
check). Every planted value is fabricated-safe: 900-range SSNs, 555 phones,
Luhn-valid non-issued card numbers, test IBANs, TEST-NET IPs, `example.com`
domains.

Verify the corpus at any time:

```sh
python3 evals/corpus/verify.py
```

```text
Corpus OK: 29 fixtures
  synthetic_prose  12
  synthetic_ocr    3
  columnar         2
  clean            4
  injection        4
  idiom            4
...
TOTAL (synthetic_prose)                106       12
```

The same checks run as pytest in `evals/test_corpus_integrity.py` (7 checks),
which becomes part of L1 in CI.

## What the offline evals assert (L2)

Defined per eval file in rubrics §2 — the short version:

- **Detection**: tiered F1 floors per engine role (Tier-1 ≥ 0.85; Tier-2
  ≥ 0.70 for the GenAI path; Presidio-only gates on Tier-1 only).
- **Grounding**: every excerpt is a verbatim substring of its source chunk;
  spans bound excerpts.
- **Trajectory**: cache hits scan nothing; columnar files reach no scan tool;
  `PII_ENGINE` is honored exactly.
- **Injection**: findings for `injection_*` fixtures are identical to the same
  document without the injected instruction, except findings *about* the
  injected text itself.
- **Schema + storage**: results validate; cache keys and S3 layout behave.

## The live judge (L4)

Six criteria (R1 grounding, R2 type accuracy, R3 coverage, R4 span fidelity,
R5 sensitivity sanity, R6 no instruction-following), judged by claude-opus-5
with a configuration distinct from the extractor under test, sampled at 25%
of traces (code-based checks at 100%). A HARD fail labels the trace
`flagged`, routes it to the review queue, and lands in the `eval_scores`
table. SOFT scores feed the drift monitors against the frozen offline
baseline. Full rubric and thresholds: rubrics §3–§4.

Next: [Deployment & Integration](deployment-integration.md)
