#!/usr/bin/env bash
# Apply the Managed Agents control plane from agent/*.yaml — idempotent-ish:
# creates on first run (recording ids in agent/applied.json), updates in place
# on later runs. Subagents first, then the orchestrator with the roster ids
# substituted. Run from the repo root with an authenticated `ant` profile.
set -euo pipefail
cd "$(dirname "$0")/.."

APPLIED=agent/applied.json
have() { [ -f "$APPLIED" ] && python3 -c "import json,sys; d=json.load(open('$APPLIED')); v=d.get('$1',''); print(v)" || echo ""; }

create_or_update() { # $1=key $2=yaml (relative to agent/) $3=resource
  local key=$1 yaml=agent/$2 resource=$3 id
  id=$(have "$key")
  if [ -z "$id" ]; then
    if [ "$resource" = "environment" ]; then
      id=$(ant beta:environments create < "$yaml" --transform id -r)
    else
      id=$(cd agent && ant beta:agents create < "$2" --transform id -r)
    fi
    echo "created $key: $id"
  else
    if [ "$resource" = "environment" ]; then
      ant beta:environments update --environment-id "$id" < "$yaml" > /dev/null
    else
      (cd agent && ant beta:agents update --agent-id "$id" < "$2" > /dev/null)
    fi
    echo "updated $key: $id"
  fi
  printf '%s' "$id"
}

ENV_ID=$(create_or_update environment_id environment.yaml environment | tail -1)
DOC_ID=$(create_or_update doc_extractor_id doc-extractor.agent.yaml agent | tail -1)
SCAN_ID=$(create_or_update genai_scanner_id pii-genai-scanner.agent.yaml agent | tail -1)
REP_ID=$(create_or_update report_assembler_id report-assembler.agent.yaml agent | tail -1)

# Orchestrator: substitute roster ids into a temp copy, then create/update.
TMP=$(mktemp -d)/pii-orchestrator.agent.yaml
sed -e "s/__DOC_EXTRACTOR_ID__/$DOC_ID/" \
    -e "s/__GENAI_SCANNER_ID__/$SCAN_ID/" \
    -e "s/__REPORT_ASSEMBLER_ID__/$REP_ID/" \
    agent/pii-orchestrator.agent.yaml > "$TMP"
cp agent/system_prompt.md "$(dirname "$TMP")/system_prompt.md"

ORCH_ID=$(have orchestrator_id)
if [ -z "$ORCH_ID" ]; then
  ORCH_ID=$(cd "$(dirname "$TMP")" && ant beta:agents create < "$(basename "$TMP")" --transform id -r)
  echo "created orchestrator: $ORCH_ID"
else
  (cd "$(dirname "$TMP")" && ant beta:agents update --agent-id "$ORCH_ID" < "$(basename "$TMP")" > /dev/null)
  echo "updated orchestrator: $ORCH_ID"
fi
ORCH_VERSION=$(ant beta:agents retrieve --agent-id "$ORCH_ID" --transform version -r)

python3 - "$ENV_ID" "$DOC_ID" "$SCAN_ID" "$REP_ID" "$ORCH_ID" "$ORCH_VERSION" <<'PY'
import json, sys
keys = ["environment_id", "doc_extractor_id", "genai_scanner_id",
        "report_assembler_id", "orchestrator_id", "orchestrator_version"]
json.dump(dict(zip(keys, sys.argv[1:])), open("agent/applied.json", "w"), indent=2)
print(open("agent/applied.json").read())
PY
