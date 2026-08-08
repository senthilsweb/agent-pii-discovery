# Observation 0001 — Defect log, Phases 0–5 (2026-08-07 → 2026-08-08)

Thirteen defects were found and resolved during the Phase 0–5 bolts. Each is
tracked as a GitHub issue with phase, evidence (session ids where a live
session exposed it), root cause, and fixing commit. Consolidated here so the
lessons outlive the issue tracker.

| # | Phase / bolt | Defect | Fixed in |
|---|---|---|---|
| #1 | 0 · spec | PRD v0.1 claimed native OTel export from Managed Agents (none exists — event stream only) | 1fd80eb / 8485984 |
| #2 | 0 · rubrics | Uniform Tier-2 floor unrealistic for bare Presidio (benchmark-corrected to per-engine floors) | af8de4c |
| #3 | 0 · corpus | Unanchored `data/` gitignore would silently drop the fixture corpus | faeb8bd |
| #4 | 1 · packaging | egg-info build artifact committed | 576c88c |
| #5 | 2 · bring-up | Bootstrap chicken-and-egg: script path referenced before clone (`sesn_01BYaMCt…`) | 877b90e |
| #6 | 2 · bring-up | File resources mount under `/mnt/session/uploads/<mount_path>` (`sesn_01BYaMCt…`) | 877b90e |
| #7 | 2 · bring-up | Sandbox default python3 is 3.11 vs `>=3.12` (`sesn_01NtVoGY…`) | 117551b |
| #8 | 2 · client | Session driver hang: terminal event consumed in history replay never reappears on the stream | 3cd21e5 |
| #9 | 2→3 · Sonnet L2 | Duplicate `persist_result` call (SOFT); DB primary key held (`sesn_01J5oGVv…`) | 3cd21e5 |
| #10 | 4 · env plumbing | BSD grep alternation dropped ARIZE_SPACE_ID mid-copy; surfaced by the forwarder's no-backend warning | in-session |
| #12 | 4 · CI | `dev` extra missing the OTel OTLP exporter package — CI silently red for ~10 commits, never caught because local dev used a hand-provisioned venv | (this session) |
| #13 | 5 · MinIO wiring | boto3 client had no path-style addressing (MinIO requires it); initial endpoint given was the console vhost, not the S3 API | (this session) |

## The patterns worth keeping

1. **Live sessions are the only place platform reality shows up.** Three of
   thirteen (#5–#7) were empirical sandbox facts no documentation stated;
   each was found by one cheap smoke session and is now a runbook entry.
2. **Defense in depth caught what prompts missed.** The DB primary key (#9)
   and the forwarder's degrade-to-warning (#10) turned would-be silent
   corruption into loud, diagnosable signals.
3. **Honest-halt beats improvisation.** The agent's refusal to fake past a
   broken bootstrap (#5) made root-causing trivial — the trajectory rules'
   "stop, don't improvise" clause paid for itself immediately.
4. **Replayability is free evidence.** Archived session event histories let
   every gate assertion re-run at zero token cost (#8, #9 verdicts).
5. **A green local venv is not evidence of a green CI.** #12 survived ten
   commits because local testing used a venv that had accumulated extras by
   hand across sessions, while CI installs `.[dev]` fresh every time. The
   fix that actually caught it: install into a brand-new venv and run the
   full suite there — a real CI simulation, not "it passed on my machine."
6. **Verify externally-given values before trusting them.** #13's endpoint
   half came from a value handed over in conversation, not derived from the
   codebase — it looked plausible and was wrong. The fix wasn't guessing a
   correction; it was testing the literal value first (got a real error),
   then checking what a *known-working* sibling deployment
   (`linkedin-cover-generator`) actually uses, and testing that.
