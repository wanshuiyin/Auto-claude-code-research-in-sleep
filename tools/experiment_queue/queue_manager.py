#!/usr/bin/env python3
"""Legacy entry point — forwards to canonical queue_manager.

Phase 3.3 (Arch C) moved the implementation to
    skills/experiment-queue/scripts/queue_manager.py

This shim keeps the directory-level resolver chain working
(.aris/tools/experiment_queue/ → tools/experiment_queue/ →
$ARIS_REPO/tools/experiment_queue/ → same, via the global pointer
file ~/.aris/repo, #366). Once a SKILL has resolved
the directory, it runs `python3 $QUEUE_TOOLS/queue_manager.py`,
which lands here, which os.execv's into the canonical script.

See `skills/experiment-queue/SKILL.md` for the resolver block.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parent.parent
REAL = REPO_ROOT / "skills" / "experiment-queue" / "scripts" / "queue_manager.py"


def main() -> int:
    if not REAL.is_file():
        sys.stderr.write(
            f"ERROR: canonical queue_manager.py not found at {REAL}.\n"
            "       Phase 3.3 moved this helper into the\n"
            "       /experiment-queue SKILL ('skills/experiment-queue/scripts/').\n"
            "       Your local checkout may be incomplete — try `git pull`\n"
            "       or rerun `bash tools/install_aris.sh` to refresh the\n"
            "       project-local symlink chain.\n"
        )
        return 1
    os.execv(sys.executable, [sys.executable, str(REAL), *sys.argv[1:]])
    return 0  # unreachable; os.execv does not return on success


if __name__ == "__main__":
    sys.exit(main())
