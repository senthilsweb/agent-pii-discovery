# Code Tour

At the end you will know where everything lives, which files carry the
project's invariants, and where the intent behind the code is recorded.

## The tree

```text
agent-pii-discovery/
├── AGENTS.md                      # conventions; loaded by Claude Code via CLAUDE.md
├── docs/
│   ├── prd.md                     # PRD v0.2 — scope, architecture, KPIs, phases
│   └── *.md                       # this site
├── agent/                         # Managed Agents control plane (versioned YAML)
│   ├── pii-orchestrator.agent.yaml  # the coordinator: model, tools, subagent roster
│   ├── environment.yaml           # sandbox: limited networking, deny-by-default egress
│   ├── system_prompt.md           # the three legal trajectories + hard rules
│   └── skills/                    # load-on-demand procedures for the agent
│       ├── extraction_procedure.md
│       ├── detection_prompt.md    # the GenAI extraction prompt (versioned)
│       ├── normalization_rules.md
│       └── report_template.md
├── evals/
│   ├── rubrics.md                 # HARD/SOFT rubrics, floors, judge criteria
│   ├── corpus/generate.py         # seeded fixture generator (spans recorded at composition)
│   ├── corpus/verify.py           # span/coverage validator
│   ├── data/<fixture_id>/         # document + labels.json sidecar per fixture
│   └── test_corpus_integrity.py   # the same checks as pytest (L1)
└── openspec/
    ├── changes/add-pii-discovery-agent/   # proposal / design / tasks / spec
    └── adr/                       # 0001: Managed Agents + Arize decision
```

`pipeline/` (sandbox scripts) and `client/` (session driver, host-side tools,
trace forwarder) are added by Phases 1–2.

## The load-bearing files

| File | The rule it enforces, and why |
|---|---|
| `evals/rubrics.md` | Written before any code; the evals define the target. Floors are per engine role; amendments only via dated in-place corrections. |
| `agent/system_prompt.md` | Enumerates the only three legal trajectories (cache hit, columnar reject, full scan) and forbids the LLM from emitting numbers — trajectory correctness is a HARD eval. |
| `agent/skills/detection_prompt.md` | The GenAI extraction prompt. Any edit changes `pipeline_version`, which invalidates the result cache by design — prompt changes can never silently reuse stale results. |
| `agent/environment.yaml` | Deny-by-default egress around untrusted documents. Hosts are added here only with a written reason. |
| `evals/corpus/generate.py` | Char spans are recorded at composition time, never found by searching afterwards — the grounding evals are only as trustworthy as these labels. |
| `.gitignore` | `uploads/`, `data/`, `exports/`, `*.duckdb` blocked: the repo is public and the subject matter is PII. Committed fixtures are synthetic only. |
| `openspec/changes/*/.openspec.yaml` | The status gate (`proposed → approved → implemented → verified`); nothing is built before `approved`. |

## Patterns worth knowing before editing

- **One generative step.** Exactly one pipeline step calls a model (typed
  extraction). Everything else is deterministic code. Before adding an LLM
  call anywhere, read ADR-worthy justification into the openspec change first.
- **Models resolve from env** (`MODEL_PII_EXTRACTOR → MODEL → startup error`);
  never hard-code a model id.
- **Config can't invent types.** The 36-type taxonomy is closed; alias YAML
  maps into it, unknowns degrade to `UNKNOWN`.
- **Evals assert on artifacts** (`result.json`, DB rows, trace attributes),
  never on the agent's prose.

## Where the intent lives

Code answers *what*; the *why* is recorded in
[`openspec/changes/add-pii-discovery-agent/design.md`](https://github.com/senthilsweb/agent-pii-discovery/blob/main/openspec/changes/add-pii-discovery-agent/design.md)
(decisions D1–D8),
[`openspec/adr/0001`](https://github.com/senthilsweb/agent-pii-discovery/blob/main/openspec/adr/0001-claude-managed-agents-and-arize.md)
(runtime + observability choice), and the
[PRD](https://github.com/senthilsweb/agent-pii-discovery/blob/main/docs/prd.md)
(§0 records what changed from v0.1 and why).

Next: [Architecture](architecture.md)
