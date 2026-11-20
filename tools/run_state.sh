#!/usr/bin/env bash
# ARIS Run State — track pipeline phase completion for resume.
# Usage: bash run_state.sh set <phase> done         (phase completed by executor)
#        bash run_state.sh accept <phase> <verdict_id> <reviewer>  (cross-model passed)
#        bash run_state.sh get                       (print current state)
#        bash run_state.sh resume                    (print next phase to run, or "done")
set -euo pipefail

STATE_DIR=".aris/runs"
STATE_FILE="$STATE_DIR/run_state.json"
mkdir -p "$STATE_DIR"

# Initialize if missing
if [ ! -f "$STATE_FILE" ]; then
    cat > "$STATE_FILE" << 'JSONEOF'
{"phases": {"0": "pending", "1": "pending", "2": "pending", "3": "pending", "4": "pending"}, "reviewer": "", "started_at": "", "last_updated": ""}
JSONEOF
fi

ACTION="${1:-}"
PHASE="${2:-}"

case "$ACTION" in
    set)
        STATUS="${3:-done}"
        python3 -c "
import json, sys
with open('$STATE_FILE') as f: s = json.load(f)
s['phases']['$PHASE'] = '$STATUS'
s['last_updated'] = '$(date -u +%Y-%m-%dT%H:%M:%SZ)'
with open('$STATE_FILE','w') as f: json.dump(s, f, indent=2)
" 2>/dev/null || python -c "
import json
with open('$STATE_FILE') as f: s = json.load(f)
s['phases']['$PHASE'] = '$STATUS'
s['last_updated'] = '$(date -u +%Y-%m-%dT%H:%M:%SZ)'
with open('$STATE_FILE','w') as f: json.dump(s, f, indent=2)
"
        echo "Phase $PHASE → $STATUS"
        ;;
    accept)
        VERDICT_ID="${3:-}"; REVIEWER="${4:-}"
        python3 -c "
import json
with open('$STATE_FILE') as f: s = json.load(f)
s['phases']['$PHASE'] = 'accepted'
s['reviewer'] = '$REVIEWER'
s['verdict_id'] = '$VERDICT_ID'
s['last_updated'] = '$(date -u +%Y-%m-%dT%H:%M:%SZ)'
with open('$STATE_FILE','w') as f: json.dump(s, f, indent=2)
" 2>/dev/null || python -c "
import json
with open('$STATE_FILE') as f: s = json.load(f)
s['phases']['$PHASE'] = 'accepted'
s['reviewer'] = '$REVIEWER'
s['verdict_id'] = '$VERDICT_ID'
s['last_updated'] = '$(date -u +%Y-%m-%dT%H:%M:%SZ)'
with open('$STATE_FILE','w') as f: json.dump(s, f, indent=2)
"
        echo "Phase $PHASE accepted by $REVIEWER ($VERDICT_ID)"
        ;;
    get)
        python3 -c "import json; s=json.load(open('$STATE_FILE')); print(json.dumps(s, indent=2))" 2>/dev/null \
        || python -c "import json; s=json.load(open('$STATE_FILE')); print(json.dumps(s, indent=2))"
        ;;
    resume)
        # Find first non-terminal phase
        python3 -c "
import json
s = json.load(open('$STATE_FILE'))
for p in ['0','1','2','3','4']:
    if s['phases'][p] not in ('accepted'):
        print(p)
        break
else:
    print('done')
" 2>/dev/null || python -c "
import json
s = json.load(open('$STATE_FILE'))
for p in ['0','1','2','3','4']:
    if s['phases'][p] not in ('accepted'):
        print(p)
        break
else:
    print('done')
"
        ;;
    *)
        echo "Usage: bash run_state.sh <set|accept|get|resume> [phase] [status|verdict_id] [reviewer]"
        exit 1
        ;;
esac
