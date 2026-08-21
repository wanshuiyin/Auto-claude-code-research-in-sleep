#!/usr/bin/env python3
"""Legacy entry point — forwards to the canonical figure_renderer.

The canonical implementation now lives at
    skills/figure-spec/scripts/figure_renderer.py
(Phase 3.1 — Arch C — self-contained single-owner helper).

This shim exists so existing users keep working without re-running
install_aris.sh. The four legacy resolver layers all still hit a
valid Python module:

  layer 1  <project>/.aris/tools/figure_renderer.py
           → symlink to $ARIS_REPO/tools/figure_renderer.py
           → this file (shim)
           → $ARIS_REPO/skills/figure-spec/scripts/figure_renderer.py

  layer 2  <project>/tools/figure_renderer.py
           → this file (when running from inside the ARIS repo)

  layer 3  $ARIS_REPO/tools/figure_renderer.py
           → this file (when ARIS_REPO env var or manifest sets it)

  layer 4  $ARIS_REPO/tools/figure_renderer.py
           → this file (when ARIS_REPO is resolved from the global
             pointer file ~/.aris/repo, #366 — no project manifest needed)

Shim semantics: `os.execv` replaces the current Python process with
the real helper, so the helper sees its own `__file__`, `sys.path[0]`,
and argv exactly as if it had been invoked directly. No extra
process layer, no environment pollution.

The shim itself is kept minimal so a Python 3.6+ interpreter on any
platform (including older macOS system python) can run it.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parent
REAL = REPO_ROOT / "skills" / "figure-spec" / "scripts" / "figure_renderer.py"


def _fail(msg: str) -> int:
    sys.stderr.write(msg + "\n")
    return 1


def main() -> int:
    if not REAL.is_file():
        return _fail(
            f"ERROR: canonical figure_renderer.py not found at {REAL}.\n"
            "       The Phase 3.1 migration moved this helper into the\n"
            "       /figure-spec SKILL ('skills/figure-spec/scripts/'). Your\n"
            "       local checkout may be incomplete — try `git pull` from the\n"
            "       ARIS repo, or rerun `bash tools/install_aris.sh` to refresh\n"
            "       the project-local symlink chain."
        )
    # os.execv replaces this Python process; argv[0] is the real path so
    # the helper sees its own __file__ and computes paths correctly.
    os.execv(sys.executable, [sys.executable, str(REAL), *sys.argv[1:]])
    return 0  # unreachable; os.execv does not return on success


if __name__ == "__main__":
    sys.exit(main())
