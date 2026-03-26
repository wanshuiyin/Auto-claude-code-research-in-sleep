#!/usr/bin/env python3
"""
Compare directions from multiple IDEA_REPORTs and generate ranking.
"""

import os
import re
import glob
from pathlib import Path

def parse_idea_report(filepath):
    """Extract key information from IDEA_REPORT.md"""
    with open(filepath, 'r') as f:
        content = f.read()

    # Try to extract direction name
    direction_match = re.search(r'\*\*Direction\*\*:\s*(.+)', content)
    direction = direction_match.group(1) if direction_match else "Unknown"

    # Count ideas generated
    idea_count = len(re.findall(r'###\s+\[?Idea', content))

    # Check for recommended idea
    has_recommendation = 'RECOMMENDED' in content or '🏆' in content

    # Try to find score
    score_match = re.search(r'Reviewer score:\s*(\d+\.?\d*)/10', content)
    score = float(score_match.group(1)) if score_match else 0

    # Try to find pilot result
    pilot_match = re.search(r'Pilot:\s*(POSITIVE|NEGATIVE|WEAK)', content)
    pilot = pilot_match.group(1) if pilot_match else "Unknown"

    return {
        'file': filepath,
        'direction': direction[:60] + '...' if len(direction) > 60 else direction,
        'idea_count': idea_count,
        'has_recommendation': has_recommendation,
        'score': score,
        'pilot': pilot
    }

def main():
    project_root = Path(__file__).parent.parent
    report_dir = project_root / 'sub-dirs'

    print("=" * 80)
    print("MRI Motion Correction - Direction Comparison")
    print("=" * 80)
    print()

    reports = []
    for subdir in report_dir.iterdir():
        if subdir.is_dir() and subdir.name.startswith('sub-'):
            report_file = subdir / 'IDEA_REPORT.md'
            if report_file.exists():
                reports.append(parse_idea_report(str(report_file)))

    if not reports:
        print("No IDEA_REPORT.md files found yet.")
        print("Wait for agents to complete Phase 1.")
        return

    # Sort by score and recommendation
    reports.sort(key=lambda x: (x['has_recommendation'], x['score']), reverse=True)

    print(f"{'Rank':<6} {'Direction':<45} {'Ideas':<7} {'Pilot':<10} {'Score':<7} {'★':<3}")
    print("-" * 80)

    for i, r in enumerate(reports, 1):
        star = "★" if r['has_recommendation'] else ""
        print(f"{i:<6} {r['direction']:<45} {r['idea_count']:<7} {r['pilot']:<10} {r['score']:<7.1f} {star:<3}")

    print()
    print("=" * 80)
    print("Recommendation")
    print("=" * 80)

    top = reports[0] if reports else None
    if top and top['has_recommendation']:
        print(f"Top direction: {top['direction']}")
        print(f"Reviewer score: {top['score']}/10")
        print()
        print("Next steps:")
        print("1. Review the full IDEA_REPORT.md")
        print("2. Check refine-logs/FINAL_PROPOSAL.md")
        print("3. Proceed to /experiment-bridge")
    else:
        print("No clear recommendation yet.")
        print("Wait for more agents to complete or review partial results.")

    # Save comparison
    output_file = project_root / 'IDEA_CANDIDATES.md'
    with open(output_file, 'w') as f:
        f.write("# Idea Candidates - MRI Motion Correction\n\n")
        f.write("Generated from multi-agent exploration.\n\n")
        f.write("| Rank | Direction | Ideas | Pilot | Score | Status |\n")
        f.write("|------|-----------|-------|-------|-------|--------|\n")

        for i, r in enumerate(reports, 1):
            status = "RECOMMENDED" if r['has_recommendation'] else "BACKUP"
            f.write(f"| {i} | {r['direction'][:40]}... | {r['idea_count']} | {r['pilot']} | {r['score']:.1f} | {status} |\n")

        f.write("\n")
        if top and top['has_recommendation']:
            f.write(f"## Active Idea: {top['direction'][:50]}\n")
            f.write(f"- File: {top['file']}\n")
            f.write(f"- Score: {top['score']}/10\n")
            f.write("- Next: /experiment-bridge\n")

    print()
    print(f"Saved comparison to: {output_file}")

if __name__ == '__main__':
    main()
