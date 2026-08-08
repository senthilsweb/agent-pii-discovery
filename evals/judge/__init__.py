"""Phase 5 — the judge layer.

R1 (grounding) and R4 (span fidelity) are deterministic code checks
(`checks.py`, run at 100% of traces, free). R2/R3/R5/R6 are LLM judges
(`llm_judge.py`); no judge runs live until calibration (`calibrate.py`)
shows ≥90% agreement with labeled cases (rubrics §3). Judge model resolves
`MODEL_JUDGE → MODEL → error` and must differ from the extractor under test.
"""
