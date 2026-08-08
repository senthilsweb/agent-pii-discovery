# Skill: report_template

Template for the human-readable summary the report-assembler renders from the
persisted `result.json`. Every number, type, and regime below is copied from
the JSON — the template adds prose glue only.

---

## PII Scan Report — {file_name}

**Scan** {scan_id} · {started_at} · engine `{engine}` · models {models}
**Document** {mime_type}, {size_bytes} bytes{, page_count pages} · checksum `{checksum_short}`
**Status** {processed | skipped_out_of_scope | failed (+reason)} {· cache hit}

### Findings ({total_types} types, {total_occurrences} occurrences)

| Type | Occurrences | Max sensitivity | Found by | Sample |
|---|---|---|---|---|
| {canonical_type} | {occurrences} | {sensitivity} | {source_engines ∪ source_models} | {first sample_excerpt} |

*(One row per rolled-up finding, sorted as in result.json. No findings ⇒ state
"No PII detected" and omit the table.)*

### Compliance impact

{impacted_jurisdictions as a sentence}, e.g. "Findings implicate GDPR (EU),
HIPAA (US) — severity high — triggered by GOVERNMENT_ID_SSN, HEALTH_CONDITION."
If empty: "No mapped compliance regimes are implicated."

### Notes

- {extraction_method, ocr_enabled if true, chunk_count}
- {any per-model disagreement worth a sentence: types found by one model only}

---

Rules: no recommendations, no risk advice, no speculation beyond the JSON; the
excerpt column is the only place document text may appear.
