#!/usr/bin/env bash
# verify_wiki_coverage.sh — Diagnostic (NOT a gate) for research-wiki coverage.
#
# Compares arXiv IDs referenced in recent session artifacts against those
# already ingested into `research-wiki/papers/`. Reports the delta so the
# user can run `/research-wiki sync --arxiv-ids <missing>` to backfill.
#
# This is a best-effort diagnostic. Because ARIS has no canonical "papers
# I actually read" log (unlike paper-writing's audit artifacts), scans
# grep over likely sources and will miss papers read via channels it
# doesn't scan. See `shared-references/integration-contract.md` §6
# (Verifier or diagnostic) — this tool is intentionally non-blocking.
#
# Usage:
#   bash tools/verify_wiki_coverage.sh <wiki_root> [--scan <path> ...] [--json-out <path>]
#
# Defaults:
#   --scan: scans CWD-level `.aris/traces/`, `paper/`, `PAPER_PLAN.md`,
#           `NARRATIVE_REPORT.md`, `references.bib` if they exist.
#   --json-out: <wiki_root>/.wiki-coverage-report.json
#
# Exit codes:
#   0  Diagnostic ran. Any coverage gap is reported but not blocking.
#   2  Bad arguments / wiki_root not found.
#
# Note: exit 0 regardless of coverage outcome — this is NOT a gate.

set -uo pipefail

WIKI_ROOT=""
JSON_OUT=""
SCAN_PATHS=()

while [[ $# -gt 0 ]]; do
    case "$1" in
        --scan)     SCAN_PATHS+=("${2:?--scan requires a path}"); shift 2 ;;
        --json-out) JSON_OUT="${2:?--json-out requires a path}"; shift 2 ;;
        -h|--help)  sed -n '2,22p' "$0" | sed 's/^# \?//'; exit 0 ;;
        --*)        echo "unknown option: $1" >&2; exit 2 ;;
        *)
            if [[ -z "$WIKI_ROOT" ]]; then WIKI_ROOT="$1"
            else echo "unexpected positional: $1" >&2; exit 2; fi
            shift ;;
    esac
done

[[ -n "$WIKI_ROOT" ]] || { echo "usage: $0 <wiki_root> [--scan <path> ...] [--json-out <path>]" >&2; exit 2; }
[[ -d "$WIKI_ROOT" ]] || { echo "wiki_root not found: $WIKI_ROOT" >&2; exit 2; }
WIKI_ROOT="$(cd "$WIKI_ROOT" && pwd)"

# Default scan set: obvious places where arxiv IDs show up
if [[ ${#SCAN_PATHS[@]} -eq 0 ]]; then
    for p in .aris/traces paper PAPER_PLAN.md NARRATIVE_REPORT.md references.bib; do
        [[ -e "$p" ]] && SCAN_PATHS+=("$p")
    done
fi

[[ -n "$JSON_OUT" ]] || JSON_OUT="$WIKI_ROOT/.wiki-coverage-report.json"

# Regex: 4-digit year + . + 4-5 digits + optional vN (modern arXiv) OR
#        category(.subclass)?/Ndigits (legacy, e.g. cs/0601001, cs.LG/0703124)
ARXIV_RE='\b(arXiv:|arxiv:|abs/)?([0-9]{4}\.[0-9]{4,5}(v[0-9]+)?|[a-z\-]+(\.[A-Z]{2})?\/[0-9]{7}(v[0-9]+)?)\b'

# Collect referenced arxiv ids from scan set
REFERENCED=$(mktemp)
trap 'rm -f "$REFERENCED" "$INGESTED" "$MISSING"' EXIT

for path in "${SCAN_PATHS[@]}"; do
    if [[ -e "$path" ]]; then
        # grep recursively for files, flat for directories; suppress "is a directory"
        grep -rohE "$ARXIV_RE" "$path" 2>/dev/null || true
    fi
done \
    | sed -E 's#^(arXiv:|arxiv:|abs/)##; s/v[0-9]+$//' \
    | grep -v '^$' \
    | sort -u > "$REFERENCED"

# Collect ingested ids from wiki frontmatter.
# Use POSIX [[:space:]] (BSD sed on macOS does not understand \s).
INGESTED=$(mktemp)
if [[ -d "$WIKI_ROOT/papers" ]]; then
    grep -hoE 'arxiv:[[:space:]]*"?[^"[:space:]]+' "$WIKI_ROOT/papers"/*.md 2>/dev/null \
        | sed -E 's/^arxiv:[[:space:]]*"?//; s/"$//; s/v[0-9]+$//' \
        | grep -v '^null$' \
        | grep -v '^$' \
        | sort -u > "$INGESTED"
else
    > "$INGESTED"
fi

# Missing = referenced but not ingested
MISSING=$(mktemp)
comm -23 "$REFERENCED" "$INGESTED" > "$MISSING"

REF_COUNT=$(wc -l < "$REFERENCED" | tr -d ' ')
ING_COUNT=$(wc -l < "$INGESTED" | tr -d ' ')
MISS_COUNT=$(wc -l < "$MISSING" | tr -d ' ')

# Write JSON report
mkdir -p "$(dirname "$JSON_OUT")"
{
    echo "{"
    echo "  \"tool\": \"verify_wiki_coverage.sh\","
    echo "  \"wiki_root\": \"$WIKI_ROOT\","
    echo "  \"scanned_paths\": ["
    if [[ ${#SCAN_PATHS[@]} -gt 0 ]]; then
        printf '    "%s"' "${SCAN_PATHS[0]}"
        for ((i=1; i<${#SCAN_PATHS[@]}; i++)); do printf ',\n    "%s"' "${SCAN_PATHS[$i]}"; done
        echo ""
    fi
    echo "  ],"
    echo "  \"generated_at\": \"$(date -u +%Y-%m-%dT%H:%M:%SZ)\","
    echo "  \"referenced_arxiv_ids\": $REF_COUNT,"
    echo "  \"ingested_arxiv_ids\": $ING_COUNT,"
    echo "  \"missing_from_wiki\": $MISS_COUNT,"
    echo "  \"diagnostic_only\": true,"
    echo "  \"missing_ids\": ["
    if [[ "$MISS_COUNT" -gt 0 ]]; then
        first=1
        while read -r id; do
            if [[ "$first" -eq 1 ]]; then
                printf '    "%s"' "$id"
                first=0
            else
                printf ',\n    "%s"' "$id"
            fi
        done < "$MISSING"
        echo ""
    fi
    echo "  ]"
    echo "}"
} > "$JSON_OUT"

# Human-readable summary
echo "" >&2
echo "Research wiki coverage (diagnostic — not blocking)" >&2
echo "  wiki:       $WIKI_ROOT" >&2
echo "  scanned:    ${SCAN_PATHS[*]:-<none>}" >&2
echo "  referenced: $REF_COUNT arxiv id(s)" >&2
echo "  ingested:   $ING_COUNT arxiv id(s)" >&2
echo "  missing:    $MISS_COUNT" >&2
echo "  report:     $JSON_OUT" >&2
echo "" >&2

if [[ "$MISS_COUNT" -gt 0 ]]; then
    echo "Missing from wiki (first 20):" >&2
    head -20 "$MISSING" | sed 's/^/    /' >&2
    [[ "$MISS_COUNT" -gt 20 ]] && echo "    ... ($((MISS_COUNT-20)) more)" >&2
    echo "" >&2
    # Build comma-joined list up to 20 ids for backfill hint
    HINT_IDS=$(head -20 "$MISSING" | paste -sd, -)
    # Resolve helper path the same way the skills do (per
    # skills/shared-references/wiki-helper-resolution.md)
    HINT_SCRIPT=".aris/tools/research_wiki.py"
    [[ -f "$HINT_SCRIPT" ]] || HINT_SCRIPT="tools/research_wiki.py"
    [[ -f "$HINT_SCRIPT" ]] || { [[ -n "${ARIS_REPO:-}" ]] && HINT_SCRIPT="$ARIS_REPO/tools/research_wiki.py"; }
    [[ -f "$HINT_SCRIPT" ]] || HINT_SCRIPT="<resolve-via-shared-ref>/research_wiki.py"
    echo "Backfill suggestion:" >&2
    echo "    python3 \"$HINT_SCRIPT\" sync $WIKI_ROOT --arxiv-ids $HINT_IDS" >&2
    [[ "$MISS_COUNT" -gt 20 ]] && echo "    (or --from-file to pass the full list)" >&2
    echo "" >&2
fi

# Always exit 0 — this is a diagnostic, not a gate.
exit 0
