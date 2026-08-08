#!/usr/bin/env bash
# Sandbox bootstrap — run ONCE at session start, idempotent.
# Clones this (public) repo and installs the pipeline with the Presidio
# engine + small spaCy model. The environment's limited networking allows
# package managers plus the GitHub hosts this needs.
set -euo pipefail

REPO_DIR="${REPO_DIR:-/workspace/agent-pii-discovery}"

if [ ! -d "$REPO_DIR" ]; then
  git clone --depth 1 https://github.com/senthilsweb/agent-pii-discovery.git "$REPO_DIR"
fi
cd "$REPO_DIR"

python3 -m pip install --quiet -e ".[presidio]"
python3 -m spacy download en_core_web_sm --quiet 2>/dev/null || \
  python3 -m pip install --quiet \
    "en_core_web_sm @ https://github.com/explosion/spacy-models/releases/download/en_core_web_sm-3.8.0/en_core_web_sm-3.8.0-py3-none-any.whl"

python3 - <<'PY'
import pipeline, presidio_analyzer, spacy
spacy.load("en_core_web_sm")
print("bootstrap OK")
PY
