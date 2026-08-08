# ADR 0004 — Vault credential provisioned for the deferred v2 scanner threads

Date: 2026-08-08 · Status: accepted (infra only — not yet wired into sessions)

## Decision

A Managed Agents vault (`vlt_011CdquAYPJMTvYMyqSmYQmG`) now holds one
`environment_variable` credential (`vcrd_01QLjBtKj2BmZjTEXfEfkAF7`,
`secret_name: ANTHROPIC_API_KEY`, `injection_location: {header: true}`,
`networking.allowed_hosts: [api.anthropic.com]`) — a static Anthropic API key
scoped to header-only substitution and to exactly one host. This is the
credential that Phase 3's deferred "per-model scanner fan-out in sessions"
item (design D2 amendment) was blocked on.

**This ADR records provisioning only.** The vault and credential exist; they
are **not yet referenced by any session** (`client/session.py` does not pass
`vault_ids`), the environment's `allowed_hosts` does not yet include
`api.anthropic.com`, and `pii-genai-scanner.agent.yaml`'s custom tool still
calls out to the host-side `pipeline/genai_detect.py`, unchanged. Actually
moving the GenAI leg into the sandbox is a separate, larger scope decision —
new session wiring, new environment config, new L2 trajectory coverage for
an in-sandbox extraction call — and stays out of scope until explicitly
requested.

## Incident: the same key was briefly placed as host-side default auth

While provisioning this credential, the static key was first set as
`ANTHROPIC_API_KEY` in the project's `.env` — the wrong location. An API key
in that env var outranks the `ant auth login` OAuth profile in the SDK's
credential precedence, and this key belongs to a **different
workspace/org** than the one `agent/applied.json`'s resources live in.
Verified concretely: `client.beta.agents.retrieve(orchestrator_id)` returned
`404 Agent not found` with the key active, and succeeded again immediately
after removing it from `.env`.

**Consequence had this gone unnoticed:** every host-side call in the
project — `client.scan`'s session creation, the judge, `genai_detect.py` —
would have either failed outright (anything referencing the existing
agent/environment/session resources) or silently run under a different
org's billing (plain `messages.parse()` calls that don't reference a
specific workspace resource, like the judge and extraction calls).

**Fix:** removed `ANTHROPIC_API_KEY` from `.env`, added a comment there
explaining why it must never be set for this project, and re-verified host
auth against the OAuth profile before doing anything else. The same key
value was then used correctly — as the vault credential's `secret_value`,
which has no workspace-matching requirement (any valid key can make a plain
`messages.parse()` call from inside a sandbox).

## Why this distinction matters

Host-side auth (`ant auth login` profile, or `ANTHROPIC_API_KEY` if one must
be set) authenticates *your process* to the Anthropic Managed Agents control
plane — it needs to see the workspace your agents/environments/sessions
actually live in. A vault `environment_variable` credential authenticates
*the sandbox's own outbound requests* at egress — a completely different
trust boundary with no workspace-matching constraint at all. The two are
easy to conflate because both ultimately hold "an Anthropic API key," but
they serve different actors (the host process vs. the sandbox) through
different mechanisms (SDK credential resolution vs. vault substitution).

## Consequences

- The vault + credential are reusable infrastructure now — wiring the v2
  scanner design later is a config change (`vault_ids` on session create,
  one `allowed_hosts` entry), not a new provisioning step.
- `agent/applied.json` gained `genai_scanner_vault_id` and
  `genai_scanner_vault_credential_id`.
- Logged as a defect in `openspec/observations/0001` alongside the project's
  other found-and-fixed issues — the same discipline applied to code defects
  applies to operational/credential mistakes too.
