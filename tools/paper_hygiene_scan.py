#!/usr/bin/env python3
"""Legacy entry point — forwards to the canonical paper_hygiene_scan.

The canonical implementation lives at
    skills/paper-hygiene-audit/scripts/paper_hygiene_scan.py
(Phase 3 layout — Arch C — self-contained single-owner helper, as for
figure_renderer.py and experiment_queue/).

This shim keeps the four legacy resolver layers working:

  layer 1  <project>/.aris/tools/paper_hygiene_scan.py
           → symlink to $ARIS_REPO/tools/ → this file (shim)
           → $ARIS_REPO/skills/paper-hygiene-audit/scripts/paper_hygiene_scan.py

  layer 2  <project>/tools/paper_hygiene_scan.py
           → this file (when running from inside the ARIS repo)

  layer 3  $ARIS_REPO/tools/paper_hygiene_scan.py
           → this file (when ARIS_REPO env var or manifest sets it)

  layer 4  $ARIS_REPO/tools/paper_hygiene_scan.py
           → this file (when ARIS_REPO is resolved from the global
             pointer file ~/.aris/repo, #366 — no project manifest needed)

Shim semantics: `os.execv` replaces the current Python process with the real
helper, so the helper sees its own `__file__`, `sys.path[0]`, and argv
exactly as if it had been invoked directly.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parent
REAL = REPO_ROOT / "skills" / "paper-hygiene-audit" / "scripts" / "paper_hygiene_scan.py"


def _fail(msg: str) -> int:
    sys.stderr.write(msg + "\n")
    return 1


def main() -> int:
    if not REAL.is_file():
        return _fail(
            f"ERROR: canonical paper_hygiene_scan.py not found at {REAL}.\n"
            "       It lives in the /paper-hygiene-audit SKILL\n"
            "       ('skills/paper-hygiene-audit/scripts/'). Your local checkout\n"
            "       may be incomplete — try `git pull` from the ARIS repo, or rerun\n"
            "       `bash tools/install_aris.sh` to refresh the project-local\n"
            "       symlink chain."
        )
    # os.execv replaces this Python process; argv[0] is the real path so
    # the helper sees its own __file__ and computes paths correctly.
    os.execv(sys.executable, [sys.executable, str(REAL), *sys.argv[1:]])
    return 0  # unreachable; os.execv does not return on success


if __name__ == "__main__":
    sys.exit(main())
