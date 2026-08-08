#!/usr/bin/env bash
# Sandbox bootstrap — run ONCE at session start, idempotent.
# Clones this (public) repo and installs the pipeline with the Presidio
# engine + small spaCy model into /workspace/venv. The sandbox's default
# python3 is 3.11 (verified in session sesn_01NtVo…) while the package needs
# >=3.12 — so we pick the newest available interpreter explicitly and all
# pipeline commands run via /workspace/venv/bin/python.
set -euo pipefail

REPO_DIR="${REPO_DIR:-/workspace/agent-pii-discovery}"
VENV="${VENV:-/workspace/venv}"

if [ ! -d "$REPO_DIR" ]; then
  git clone --depth 1 https://github.com/senthilsweb/agent-pii-discovery.git "$REPO_DIR"
fi
cd "$REPO_DIR"

PYBIN=$(command -v python3.13 || command -v python3.12 || command -v python3)
if [ ! -x "$VENV/bin/python" ]; then
  "$PYBIN" -m venv "$VENV"
fi

"$VENV/bin/pip" install --quiet --upgrade pip
"$VENV/bin/pip" install --quiet -e ".[presidio]"
"$VENV/bin/python" -m spacy download en_core_web_sm --quiet 2>/dev/null || \
  "$VENV/bin/pip" install --quiet \
    "en_core_web_sm @ https://github.com/explosion/spacy-models/releases/download/en_core_web_sm-3.8.0/en_core_web_sm-3.8.0-py3-none-any.whl"

"$VENV/bin/python" - <<'PY'
import sys, pipeline, presidio_analyzer, spacy
spacy.load("en_core_web_sm")
print(f"bootstrap OK — python {sys.version.split()[0]}")
PY
