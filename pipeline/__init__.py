"""Deterministic PII discovery pipeline (Phase 1).

Every module here is deterministic code — the one generative step
(`detect_pii_genai`) lands in Phase 3 and lives outside this package's
guarantees. Design: openspec/changes/add-pii-discovery-agent/design.md.
"""

TAXONOMY_VERSION = "1"  # bumped when config/label_aliases.yaml changes shape
