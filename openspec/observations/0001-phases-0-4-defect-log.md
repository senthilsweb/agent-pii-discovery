# Observation 0001 — Defect log, Phases 0–4 (2026-08-07 → 2026-08-08)

Ten defects were found and resolved during the Phase 0–4 bolts. Each is
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

## The patterns worth keeping

1. **Live sessions are the only place platform reality shows up.** Three of
   ten (#5–#7) were empirical sandbox facts no documentation stated; each was
   found by one cheap smoke session and is now a runbook entry.
2. **Defense in depth caught what prompts missed.** The DB primary key (#9)
   and the forwarder's degrade-to-warning (#10) turned would-be silent
   corruption into loud, diagnosable signals.
3. **Honest-halt beats improvisation.** The agent's refusal to fake past a
   broken bootstrap (#5) made root-causing trivial — the trajectory rules'
   "stop, don't improvise" clause paid for itself immediately.
4. **Replayability is free evidence.** Archived session event histories let
   every gate assertion re-run at zero token cost (#8, #9 verdicts).
