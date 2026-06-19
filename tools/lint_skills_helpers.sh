#!/usr/bin/env bash
# lint_skills_helpers.sh — Advisory lint for hardcoded `tools/<helper>` references.
#
# Per shared-references/integration-contract.md §2, SKILL.md files must
# resolve helpers via the canonical strict-safe chain
#   .aris/tools/<helper>  →  tools/<helper>  →  $ARIS_REPO/tools/<helper>
# (Codex mirror uses the mirror-side chain), NOT hardcode `python3 tools/foo.py`
# or `bash tools/foo.sh` directly.
#
# This script is ADVISORY: it always exits 0 and only prints findings.
# A future enforcement layer (issue #178) may fail CI on new violations,
# but Phase 2 keeps the contract gentle so the maintainer is not blocked.
#
# Run from the ARIS repo root:
#     bash tools/lint_skills_helpers.sh

set -u

# Patterns that indicate hardcoded helper invocation (no resolver).
INVOCATION_PY='python3 tools/(verify_papers|extract_paper_style|paper_illustration_image2|figure_renderer|arxiv_fetch|semantic_scholar_fetch|deepxiv_fetch|exa_search|openalex_fetch|research_wiki|iteration_log)\.py'
INVOCATION_SH='bash tools/(verify_paper_audits|save_trace|verify_wiki_coverage|overleaf_audit)\.sh'

# Files exempted from the lint:
#   - integration-contract.md (canonical docs include ❌ anti-pattern examples)
#   - wiki-helper-resolution.md (defines the chain; layer-2 reference is intentional)
#   - skills-codex/paper-writing/SKILL.md L525 hook JSON example (placeholder for user
#     ~/.claude/settings.json or ~/.codex/config hook, not a SKILL bash block)
EXEMPTIONS="\
skills/shared-references/integration-contract.md
skills/skills-codex/shared-references/integration-contract.md
skills/shared-references/wiki-helper-resolution.md
skills/skills-codex/shared-references/wiki-helper-resolution.md
skills/skills-codex/paper-writing/SKILL.md"

is_exempt() {
  case "$EXEMPTIONS" in
    *"$1"*) return 0 ;;
  esac
  return 1
}

violation_count=0
violation_report=""

while IFS= read -r f; do
  if is_exempt "$f"; then
    continue
  fi
  py_hits=$(grep -nE "$INVOCATION_PY" "$f" 2>/dev/null || true)
  sh_hits=$(grep -nE "$INVOCATION_SH" "$f" 2>/dev/null || true)
  if [ -n "$py_hits" ] || [ -n "$sh_hits" ]; then
    violation_count=$((violation_count + 1))
    violation_report="${violation_report}
=== $f ==="
    [ -n "$py_hits" ] && violation_report="${violation_report}
${py_hits}"
    [ -n "$sh_hits" ] && violation_report="${violation_report}
${sh_hits}"
  fi
done < <(find skills -name '*.md' -type f 2>/dev/null)

echo "ARIS helper-resolution lint (advisory)"
echo "======================================="
echo "Files with hardcoded \`tools/<helper>\` references: $violation_count"

if [ "$violation_count" -gt 0 ]; then
  printf '%s\n\n' "$violation_report"
  echo "Resolution:"
  echo "  Migrate each violating SKILL.md to the canonical strict-safe resolver"
  echo "  per shared-references/integration-contract.md §2 (assign a semantic"
  echo "  variable like \$AUDIT_VERIFIER / \$TRACE_HELPER / \$<NAME>_FETCHER from"
  echo "  the three-layer chain, then invoke as \`python3 \"\$VAR\" ...\` or"
  echo "  \`bash \"\$VAR\" ...\`)."
  echo ""
  echo "  Per-helper policy (Policy A gate / B side-effect / C forensic /"
  echo "  D1 cascade / D2 multi-source / E diagnostic) is documented in the"
  echo "  \"Per-helper policy assignments\" table of integration-contract.md §2."
fi

echo ""
echo "Status: advisory (this script never fails CI; warnings only)."

exit 0
