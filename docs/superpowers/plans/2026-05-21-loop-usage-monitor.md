# Loop Usage Monitor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an iteration-budget guardrail (`tools/loop_budget.py`) that stops `auto-review-loop*` skills before they exhaust Claude.ai / ChatGPT subscription quotas; wire all three loop skills to consult it via the repo's standard helper-resolution chain.

**Architecture:** Stdlib-only Python CLI (`check` / `record` / `status`) backed by an append-only JSONL log at `~/.aris/usage/loop-usage.jsonl`. Three loop skills resolve the helper via the canonical `.aris/tools` → `tools` → `$ARIS_REPO/tools` chain, call `check --side <claude|codex>` before each executor / reviewer turn, and call `record` after success. Policy A (gate): if the helper cannot be resolved, loops refuse to run.

**Tech Stack:** Python 3 stdlib (`argparse`, `json`, `datetime`, `pathlib`), `unittest` for tests. No third-party dependencies. Spec at `docs/superpowers/specs/2026-05-21-loop-usage-monitor-design.md`.

---

## Background for the implementer

You are about to land a small Python CLI plus three Markdown skill patches in a research-automation repo (ARIS). Two repo conventions matter:

**Helper resolution.** SKILL.md files invoke helpers in `tools/` via a three-layer resolver chain documented in `skills/shared-references/integration-contract.md` §2. Skills must use that chain — never a hardcoded `tools/<helper>` path — because downstream projects install ARIS as a sibling and reach helpers through `.aris/tools/`. Cross-skill helpers ship a dedicated resolver doc under `skills/shared-references/<helper>-resolution.md` that other skills `[include]` or copy-paste from. Mirrors: `wiki-helper-resolution.md`, `review-tracing.md`.

**Failure policies.** The same contract assigns each helper a failure policy. Ours is **Policy A (gate)**: if the helper cannot be resolved, the calling skill must `echo ERROR ... ; exit 1` rather than degrade. The exit code IS the gate.

**install_aris.sh.** Already symlinks `.aris/tools → tools` as a directory (rule S12). Putting a new file in `tools/` makes it auto-resolvable in downstream projects with no installer change.

---

## File Structure

```
tools/loop_budget.py                                   ← NEW: CLI + library
tests/test_loop_budget.py                              ← NEW: unittest tests
skills/shared-references/loop-budget-resolution.md     ← NEW: resolver doc
skills/shared-references/integration-contract.md       ← EDIT: add Policy A row
skills/auto-review-loop/SKILL.md                       ← EDIT: budget guard section
skills/auto-review-loop-llm/SKILL.md                   ← EDIT: budget guard section
skills/auto-review-loop-minimax/SKILL.md               ← EDIT: budget guard section
```

The Python file holds both the library functions (importable by tests) and the CLI entrypoint, mirroring `tools/watchdog.py`'s structure.

---

## Task 1: Scaffold `loop_budget.py` and the first failing test

**Files:**
- Create: `tools/loop_budget.py`
- Create: `tests/test_loop_budget.py`

- [ ] **Step 1: Write the first failing test**

Create `tests/test_loop_budget.py`:

```python
#!/usr/bin/env python3
"""Tests for tools/loop_budget.py — iteration-budget guard for auto-review-loop skills."""

import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "tools" / "loop_budget.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("loop_budget", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class LoopBudgetTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="loop-budget-"))
        os.environ["ARIS_USAGE_DIR"] = str(self.tmp)
        # Reset budget env to defaults known by tests.
        for k in (
            "CLAUDE_LOOP_MAX_ITERATIONS", "CLAUDE_LOOP_WINDOW_HOURS",
            "CODEX_LOOP_MAX_ITERATIONS", "CODEX_LOOP_WINDOW_HOURS",
            "CLAUDE_LOOP_WARN_AT",
        ):
            os.environ.pop(k, None)
        self.mod = _load_module()

    def tearDown(self):
        os.environ.pop("ARIS_USAGE_DIR", None)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_script_exists_and_is_python3(self):
        self.assertTrue(SCRIPT.exists(), f"{SCRIPT} must exist")
        # Smoke test: import succeeds and module exposes `usage_path`.
        self.assertTrue(hasattr(self.mod, "usage_path"))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_loop_budget -v`
Expected: FAIL — `tools/loop_budget.py` doesn't exist yet, so `spec_from_file_location` returns `None` → `AttributeError`.

- [ ] **Step 3: Write minimal `tools/loop_budget.py` to pass**

Create `tools/loop_budget.py`:

```python
#!/usr/bin/env python3
"""loop_budget.py — iteration-budget guard for auto-review-loop* skills.

Subcommands:
    check  --side {claude|codex}                  → exit 0 ok, 2 over budget
    record --side {claude|codex} --skill <name>   → append one record
    status                                        → print human summary

State file: $ARIS_USAGE_DIR/loop-usage.jsonl  (default: ~/.aris/usage/loop-usage.jsonl)

See docs/superpowers/specs/2026-05-21-loop-usage-monitor-design.md.
"""
from __future__ import annotations

import os
from pathlib import Path

DEFAULT_USAGE_DIR = "~/.aris/usage"
USAGE_FILE_NAME = "loop-usage.jsonl"


def usage_path() -> Path:
    base = Path(os.environ.get("ARIS_USAGE_DIR", DEFAULT_USAGE_DIR)).expanduser()
    return base / USAGE_FILE_NAME
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest tests.test_loop_budget -v`
Expected: PASS — 1 test passes.

- [ ] **Step 5: Commit**

```bash
git add tools/loop_budget.py tests/test_loop_budget.py
git commit -m "feat(loop_budget): scaffold tool and first test"
```

---

## Task 2: `record` subcommand (TDD)

**Files:**
- Modify: `tools/loop_budget.py`
- Modify: `tests/test_loop_budget.py`

- [ ] **Step 1: Add failing tests for `record`**

Append inside `LoopBudgetTest` in `tests/test_loop_budget.py`:

```python
    def _run(self, *args):
        return subprocess.run(
            [sys.executable, str(SCRIPT), *args],
            capture_output=True, text=True, env={**os.environ},
        )

    def test_record_creates_state_dir_and_file(self):
        out = self._run("record", "--side", "claude", "--skill", "auto-review-loop")
        self.assertEqual(out.returncode, 0, out.stderr)
        state_file = self.tmp / "loop-usage.jsonl"
        self.assertTrue(state_file.exists())
        lines = state_file.read_text().strip().splitlines()
        self.assertEqual(len(lines), 1)
        rec = json.loads(lines[0])
        self.assertEqual(rec["side"], "claude")
        self.assertEqual(rec["skill"], "auto-review-loop")
        # ts must parse as ISO-8601 UTC with Z suffix.
        self.assertTrue(rec["ts"].endswith("Z"))
        datetime.strptime(rec["ts"], "%Y-%m-%dT%H:%M:%SZ")

    def test_record_appends_subsequent_calls(self):
        self._run("record", "--side", "claude", "--skill", "auto-review-loop")
        self._run("record", "--side", "codex", "--skill", "auto-review-loop-llm")
        lines = (self.tmp / "loop-usage.jsonl").read_text().strip().splitlines()
        self.assertEqual(len(lines), 2)
        self.assertEqual(json.loads(lines[0])["side"], "claude")
        self.assertEqual(json.loads(lines[1])["side"], "codex")

    def test_record_rejects_unknown_side(self):
        out = self._run("record", "--side", "bogus", "--skill", "x")
        self.assertNotEqual(out.returncode, 0)
        self.assertIn("bogus", out.stderr)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m unittest tests.test_loop_budget -v`
Expected: 3 new tests FAIL (no argparse / no `record` command).

- [ ] **Step 3: Implement `record` + CLI shell**

Replace the contents of `tools/loop_budget.py` with:

```python
#!/usr/bin/env python3
"""loop_budget.py — iteration-budget guard for auto-review-loop* skills.

Subcommands:
    check  --side {claude|codex}                  → exit 0 ok, 2 over budget
    record --side {claude|codex} --skill <name>   → append one record
    status                                        → print human summary

State file: $ARIS_USAGE_DIR/loop-usage.jsonl  (default: ~/.aris/usage/loop-usage.jsonl)

See docs/superpowers/specs/2026-05-21-loop-usage-monitor-design.md.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_USAGE_DIR = "~/.aris/usage"
USAGE_FILE_NAME = "loop-usage.jsonl"
SIDES = ("claude", "codex")


def usage_path() -> Path:
    base = Path(os.environ.get("ARIS_USAGE_DIR", DEFAULT_USAGE_DIR)).expanduser()
    return base / USAGE_FILE_NAME


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def cmd_record(args: argparse.Namespace) -> int:
    path = usage_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    record = {"ts": _utc_now_iso(), "side": args.side, "skill": args.skill}
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record) + "\n")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="loop_budget")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_record = sub.add_parser("record", help="Append one iteration record.")
    p_record.add_argument("--side", required=True, choices=SIDES)
    p_record.add_argument("--skill", required=True)
    p_record.set_defaults(func=cmd_record)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m unittest tests.test_loop_budget -v`
Expected: 4 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add tools/loop_budget.py tests/test_loop_budget.py
git commit -m "feat(loop_budget): add record subcommand"
```

---

## Task 3: `check` subcommand — under/over budget + side filter (TDD)

**Files:**
- Modify: `tools/loop_budget.py`
- Modify: `tests/test_loop_budget.py`

- [ ] **Step 1: Add failing tests**

Append inside `LoopBudgetTest`:

```python
    def _write_records(self, recs):
        """Write a list of dicts to the state file directly."""
        path = self.tmp / "loop-usage.jsonl"
        with path.open("w", encoding="utf-8") as fh:
            for r in recs:
                fh.write(json.dumps(r) + "\n")

    @staticmethod
    def _iso(dt):
        return dt.strftime("%Y-%m-%dT%H:%M:%SZ")

    def test_check_empty_state_is_under_budget(self):
        out = self._run("check", "--side", "claude")
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn("0/", out.stderr)

    def test_check_exits_2_when_at_cap(self):
        os.environ["CLAUDE_LOOP_MAX_ITERATIONS"] = "3"
        now = datetime.now(timezone.utc)
        self._write_records([
            {"ts": self._iso(now), "side": "claude", "skill": "x"},
            {"ts": self._iso(now), "side": "claude", "skill": "x"},
            {"ts": self._iso(now), "side": "claude", "skill": "x"},
        ])
        out = self._run("check", "--side", "claude")
        self.assertEqual(out.returncode, 2, out.stderr)
        self.assertIn("STOP", out.stderr)

    def test_check_under_cap_when_one_short(self):
        os.environ["CLAUDE_LOOP_MAX_ITERATIONS"] = "3"
        now = datetime.now(timezone.utc)
        self._write_records([
            {"ts": self._iso(now), "side": "claude", "skill": "x"},
            {"ts": self._iso(now), "side": "claude", "skill": "x"},
        ])
        out = self._run("check", "--side", "claude")
        self.assertEqual(out.returncode, 0, out.stderr)

    def test_check_only_counts_matching_side(self):
        os.environ["CLAUDE_LOOP_MAX_ITERATIONS"] = "2"
        now = datetime.now(timezone.utc)
        self._write_records([
            {"ts": self._iso(now), "side": "claude", "skill": "x"},
            {"ts": self._iso(now), "side": "codex", "skill": "x"},
            {"ts": self._iso(now), "side": "codex", "skill": "x"},
        ])
        # Claude side: 1/2, ok. Codex side: 2/2, over.
        self.assertEqual(self._run("check", "--side", "claude").returncode, 0)
        self.assertEqual(self._run("check", "--side", "codex").returncode, 2)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m unittest tests.test_loop_budget -v`
Expected: 4 new tests FAIL — no `check` subcommand wired up yet.

- [ ] **Step 3: Implement `check`**

Add these constants, imports, and helpers to `tools/loop_budget.py`. Replace the existing file contents with:

```python
#!/usr/bin/env python3
"""loop_budget.py — iteration-budget guard for auto-review-loop* skills.

Subcommands:
    check  --side {claude|codex}                  → exit 0 ok, 2 over budget
    record --side {claude|codex} --skill <name>   → append one record
    status                                        → print human summary

State file: $ARIS_USAGE_DIR/loop-usage.jsonl  (default: ~/.aris/usage/loop-usage.jsonl)

See docs/superpowers/specs/2026-05-21-loop-usage-monitor-design.md.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

DEFAULT_USAGE_DIR = "~/.aris/usage"
USAGE_FILE_NAME = "loop-usage.jsonl"
SIDES = ("claude", "codex")

DEFAULT_CAPS = {"claude": 15, "codex": 30}
DEFAULT_WINDOW_HOURS = {"claude": 5.0, "codex": 5.0}
DEFAULT_WARN_AT = 0.8


def usage_path() -> Path:
    base = Path(os.environ.get("ARIS_USAGE_DIR", DEFAULT_USAGE_DIR)).expanduser()
    return base / USAGE_FILE_NAME


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_ts(ts: str) -> datetime:
    # Accept "...Z" and "+00:00" forms.
    if ts.endswith("Z"):
        ts = ts[:-1] + "+00:00"
    return datetime.fromisoformat(ts)


def _config_for(side: str) -> tuple[int, float]:
    cap_env = f"{side.upper()}_LOOP_MAX_ITERATIONS"
    win_env = f"{side.upper()}_LOOP_WINDOW_HOURS"
    cap = int(os.environ.get(cap_env, DEFAULT_CAPS[side]))
    window = float(os.environ.get(win_env, DEFAULT_WINDOW_HOURS[side]))
    return cap, window


def _warn_threshold() -> float:
    return float(os.environ.get("CLAUDE_LOOP_WARN_AT", DEFAULT_WARN_AT))


def load_records(path: Path) -> list[dict]:
    if not path.exists():
        return []
    out: list[dict] = []
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                print(f"[loop_budget] skip unparseable line: {line[:60]!r}", file=sys.stderr)
                continue
    return out


def filter_window(records: list[dict], side: str, now: datetime, window_hours: float) -> list[dict]:
    cutoff = now - timedelta(hours=window_hours)
    out: list[dict] = []
    for r in records:
        if r.get("side") != side:
            continue
        ts_raw = r.get("ts")
        if not isinstance(ts_raw, str):
            continue
        try:
            ts = _parse_ts(ts_raw)
        except ValueError:
            continue
        if ts >= cutoff:
            out.append(r)
    return out


def cmd_record(args: argparse.Namespace) -> int:
    path = usage_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    record = {"ts": _utc_now_iso(), "side": args.side, "skill": args.skill}
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record) + "\n")
    return 0


def cmd_check(args: argparse.Namespace) -> int:
    side = args.side
    cap, window_hours = _config_for(side)
    now = datetime.now(timezone.utc)
    in_window = filter_window(load_records(usage_path()), side, now, window_hours)
    used = len(in_window)
    if used >= cap:
        if in_window:
            oldest = min(_parse_ts(r["ts"]) for r in in_window)
            reset_local = (oldest + timedelta(hours=window_hours)).astimezone()
            reset_str = reset_local.strftime("%Y-%m-%d %H:%M %Z").strip()
        else:
            reset_str = "unknown"
        print(
            f"[budget] {side} {used}/{cap} in {window_hours}h window — STOP. "
            f"Next slot frees at {reset_str}.",
            file=sys.stderr,
        )
        return 2
    util = used / cap if cap > 0 else 1.0
    if util >= _warn_threshold():
        print(
            f"[budget warning] {side} {used}/{cap} ({int(util * 100)}%), "
            f"{cap - used} iterations until cap.",
            file=sys.stderr,
        )
    else:
        print(f"[budget] {side} {used}/{cap} in {window_hours}h window, ok", file=sys.stderr)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="loop_budget")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_check = sub.add_parser("check", help="Exit 0 if under budget, 2 if at/over.")
    p_check.add_argument("--side", required=True, choices=SIDES)
    p_check.set_defaults(func=cmd_check)

    p_record = sub.add_parser("record", help="Append one iteration record.")
    p_record.add_argument("--side", required=True, choices=SIDES)
    p_record.add_argument("--skill", required=True)
    p_record.set_defaults(func=cmd_record)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m unittest tests.test_loop_budget -v`
Expected: 8 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add tools/loop_budget.py tests/test_loop_budget.py
git commit -m "feat(loop_budget): add check subcommand with cap + side filter"
```

---

## Task 4: `check` — rolling window + warning threshold + reset time (TDD)

**Files:**
- Modify: `tests/test_loop_budget.py`

(Implementation already supports these; we are pinning the behaviour with explicit tests.)

- [ ] **Step 1: Add tests for window expiry, warning, and reset-time**

Append inside `LoopBudgetTest`:

```python
    def test_check_ignores_records_older_than_window(self):
        os.environ["CLAUDE_LOOP_MAX_ITERATIONS"] = "2"
        os.environ["CLAUDE_LOOP_WINDOW_HOURS"] = "5"
        now = datetime.now(timezone.utc)
        old = now - timedelta(hours=6)
        self._write_records([
            {"ts": self._iso(old), "side": "claude", "skill": "x"},
            {"ts": self._iso(old), "side": "claude", "skill": "x"},
            {"ts": self._iso(now), "side": "claude", "skill": "x"},
        ])
        # Only 1 record falls within the 5h window; cap=2 → under.
        self.assertEqual(self._run("check", "--side", "claude").returncode, 0)

    def test_check_warns_at_threshold(self):
        os.environ["CLAUDE_LOOP_MAX_ITERATIONS"] = "5"
        os.environ["CLAUDE_LOOP_WARN_AT"] = "0.8"
        now = datetime.now(timezone.utc)
        self._write_records([
            {"ts": self._iso(now), "side": "claude", "skill": "x"} for _ in range(4)
        ])
        out = self._run("check", "--side", "claude")
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn("warning", out.stderr.lower())
        self.assertIn("80%", out.stderr)

    def test_check_reports_reset_time_when_over_cap(self):
        os.environ["CLAUDE_LOOP_MAX_ITERATIONS"] = "1"
        os.environ["CLAUDE_LOOP_WINDOW_HOURS"] = "5"
        ref = datetime.now(timezone.utc) - timedelta(hours=1)
        self._write_records([{"ts": self._iso(ref), "side": "claude", "skill": "x"}])
        out = self._run("check", "--side", "claude")
        self.assertEqual(out.returncode, 2, out.stderr)
        # Reset should be approx ref + 5h, i.e. ~4 hours from now.
        # We just assert the message includes a "Next slot frees at" timestamp.
        self.assertIn("Next slot frees at", out.stderr)
```

- [ ] **Step 2: Run tests to verify they pass**

Run: `python3 -m unittest tests.test_loop_budget -v`
Expected: 11 tests PASS (3 new + 8 existing). No code changes needed — implementation already covers these.

- [ ] **Step 3: Commit**

```bash
git add tests/test_loop_budget.py
git commit -m "test(loop_budget): pin rolling-window, warning, reset-time behavior"
```

---

## Task 5: `check` — corrupted JSONL and missing state (TDD)

**Files:**
- Modify: `tests/test_loop_budget.py`

- [ ] **Step 1: Add tests for robustness**

Append inside `LoopBudgetTest`:

```python
    def test_check_skips_unparseable_lines_without_crashing(self):
        os.environ["CLAUDE_LOOP_MAX_ITERATIONS"] = "5"
        now = datetime.now(timezone.utc)
        path = self.tmp / "loop-usage.jsonl"
        with path.open("w", encoding="utf-8") as fh:
            fh.write("this is not json\n")
            fh.write(json.dumps({"ts": self._iso(now), "side": "claude", "skill": "x"}) + "\n")
            fh.write("\n")  # blank line
            fh.write('{"ts": "garbage", "side": "claude"}\n')  # bad ts
        out = self._run("check", "--side", "claude")
        self.assertEqual(out.returncode, 0, out.stderr)
        # Should count only the one valid line.
        self.assertIn("1/5", out.stderr)

    def test_check_handles_missing_state_file(self):
        # Setup left ARIS_USAGE_DIR pointing at a freshly-made empty dir.
        out = self._run("check", "--side", "codex")
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn("0/", out.stderr)
```

- [ ] **Step 2: Run tests to verify they pass**

Run: `python3 -m unittest tests.test_loop_budget -v`
Expected: 13 tests PASS. Implementation already handles these cases.

- [ ] **Step 3: Commit**

```bash
git add tests/test_loop_budget.py
git commit -m "test(loop_budget): pin tolerance for corrupt and missing state"
```

---

## Task 6: `status` subcommand + `ARIS_USAGE_DIR` override (TDD)

**Files:**
- Modify: `tools/loop_budget.py`
- Modify: `tests/test_loop_budget.py`

- [ ] **Step 1: Add failing tests**

Append inside `LoopBudgetTest`:

```python
    def test_status_prints_both_sides_and_exits_zero(self):
        now = datetime.now(timezone.utc)
        self._write_records([
            {"ts": self._iso(now), "side": "claude", "skill": "x"},
            {"ts": self._iso(now), "side": "codex", "skill": "y"},
            {"ts": self._iso(now), "side": "codex", "skill": "y"},
        ])
        out = self._run("status")
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn("claude", out.stdout)
        self.assertIn("codex", out.stdout)
        self.assertIn("1/", out.stdout)
        self.assertIn("2/", out.stdout)

    def test_status_with_no_state_shows_zero(self):
        out = self._run("status")
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn("0/", out.stdout)

    def test_aris_usage_dir_override_isolated_per_test(self):
        # setUp pointed ARIS_USAGE_DIR at self.tmp; nothing should leak from $HOME.
        self._run("record", "--side", "claude", "--skill", "x")
        self.assertTrue((self.tmp / "loop-usage.jsonl").exists())
        # And ~/.aris/usage/loop-usage.jsonl should NOT have been touched by this test.
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m unittest tests.test_loop_budget -v`
Expected: 2 of 3 new tests FAIL (no `status` subcommand). The override test should pass because `usage_path()` already honors `ARIS_USAGE_DIR`.

- [ ] **Step 3: Implement `status`**

In `tools/loop_budget.py`, add this function above `build_parser`:

```python
def cmd_status(args: argparse.Namespace) -> int:
    now = datetime.now(timezone.utc)
    records = load_records(usage_path())
    for side in SIDES:
        cap, window_hours = _config_for(side)
        in_window = filter_window(records, side, now, window_hours)
        used = len(in_window)
        pct = (used / cap * 100) if cap > 0 else 100
        if in_window:
            oldest = min(_parse_ts(r["ts"]) for r in in_window)
            reset_local = (oldest + timedelta(hours=window_hours)).astimezone()
            tail = f"next slot frees at {reset_local.strftime('%H:%M %Z').strip()}"
        else:
            tail = "plenty of headroom"
        print(f"{side:8s}: {used}/{cap} in {window_hours}h window ({pct:.0f}%) — {tail}")
    return 0
```

And register the subparser inside `build_parser`, right before `return parser`:

```python
    p_status = sub.add_parser("status", help="Print current usage per side.")
    p_status.set_defaults(func=cmd_status)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m unittest tests.test_loop_budget -v`
Expected: 16 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add tools/loop_budget.py tests/test_loop_budget.py
git commit -m "feat(loop_budget): add status subcommand"
```

---

## Task 7: End-to-end CLI smoke check

**Files:** none modified — just verification.

- [ ] **Step 1: Run the tool manually against a throwaway state dir**

```bash
export ARIS_USAGE_DIR=$(mktemp -d)
python3 tools/loop_budget.py status
python3 tools/loop_budget.py record --side claude --skill manual-smoke
python3 tools/loop_budget.py record --side codex  --skill manual-smoke
python3 tools/loop_budget.py status
python3 tools/loop_budget.py check --side claude && echo "claude ok"
python3 tools/loop_budget.py check --side codex  && echo "codex ok"
CLAUDE_LOOP_MAX_ITERATIONS=1 python3 tools/loop_budget.py check --side claude ; echo "exit=$?"
unset ARIS_USAGE_DIR
```

Expected: `status` shows 1/15 claude and 1/30 codex after the two records; final `check` with `CLAUDE_LOOP_MAX_ITERATIONS=1` prints "STOP. Next slot frees at ..." and exits 2.

- [ ] **Step 2: Run the full test suite once more**

Run: `python3 -m unittest tests.test_loop_budget -v`
Expected: 16 PASS.

No commit (no file changes).

---

## Task 8: Resolver doc for skills

**Files:**
- Create: `skills/shared-references/loop-budget-resolution.md`

- [ ] **Step 1: Write the resolver doc**

Create `skills/shared-references/loop-budget-resolution.md`:

````markdown
# Loop Budget Helper Resolution

This document describes how `auto-review-loop*` skills resolve `tools/loop_budget.py`.
The pattern mirrors `wiki-helper-resolution.md` and `review-tracing.md`.

## Resolver block

Paste this into the skill's bash setup, then use `$LOOP_BUDGET_SCRIPT` thereafter.

```bash
cd "$(git rev-parse --show-toplevel 2>/dev/null || pwd)" || exit 1
if [ -z "${ARIS_REPO:-}" ] && [ -f .aris/installed-skills.txt ]; then
    ARIS_REPO=$(awk -F'\t' '$1=="repo_root"{print $2; exit}' .aris/installed-skills.txt 2>/dev/null) || true
fi
LOOP_BUDGET_SCRIPT=".aris/tools/loop_budget.py"
[ -f "$LOOP_BUDGET_SCRIPT" ] || LOOP_BUDGET_SCRIPT="tools/loop_budget.py"
[ -f "$LOOP_BUDGET_SCRIPT" ] || { [ -n "${ARIS_REPO:-}" ] && LOOP_BUDGET_SCRIPT="$ARIS_REPO/tools/loop_budget.py"; }
[ -f "$LOOP_BUDGET_SCRIPT" ] || LOOP_BUDGET_SCRIPT=""
```

## Failure policy (Policy A — gate)

If the helper is unresolved, the loop MUST refuse to start:

```bash
[ -n "$LOOP_BUDGET_SCRIPT" ] || {
  echo "ERROR: loop_budget.py not resolved at .aris/tools/, tools/, or \$ARIS_REPO/tools/." >&2
  echo "       The auto-review-loop guard cannot enforce subscription quota; aborting." >&2
  echo "       Fix: rerun bash tools/install_aris.sh, export ARIS_REPO, or copy the helper to tools/." >&2
  exit 1
}
```

## Pre-iteration check

Run before each side's call. Exit 0 = ok; exit 2 = at/over budget; the tool prints
a one-line status to stderr in both cases.

```bash
python3 "$LOOP_BUDGET_SCRIPT" check --side claude || exit $?  # before executor turn
python3 "$LOOP_BUDGET_SCRIPT" check --side codex  || exit $?  # before reviewer turn
```

## Post-call record

Run after each side's call succeeds:

```bash
python3 "$LOOP_BUDGET_SCRIPT" record --side claude --skill <this-skill-name>
python3 "$LOOP_BUDGET_SCRIPT" record --side codex  --skill <this-skill-name>
```

## Configuration

Defaults are conservative for $100/mo Claude.ai and ChatGPT subscriptions.
Override per-machine via environment:

| Env var                         | Default | Meaning                                  |
|---------------------------------|---------|------------------------------------------|
| `CLAUDE_LOOP_MAX_ITERATIONS`    | `15`    | Executor turns per Claude window         |
| `CLAUDE_LOOP_WINDOW_HOURS`      | `5`     | Claude rolling window length             |
| `CODEX_LOOP_MAX_ITERATIONS`     | `30`    | Reviewer turns per Codex window          |
| `CODEX_LOOP_WINDOW_HOURS`       | `5`     | Codex rolling window length              |
| `CLAUDE_LOOP_WARN_AT`           | `0.8`   | Warn-stderr threshold (still exits 0)    |
| `ARIS_USAGE_DIR`                | `~/.aris/usage` | State directory                  |

## Status (manual inspection)

`python3 "$LOOP_BUDGET_SCRIPT" status` prints current usage on both sides — no exit-code semantics, safe to run anytime.
````

- [ ] **Step 2: Commit**

```bash
git add skills/shared-references/loop-budget-resolution.md
git commit -m "docs(shared-references): resolver for loop_budget helper"
```

---

## Task 9: Add Policy A row to the integration contract

**Files:**
- Modify: `skills/shared-references/integration-contract.md`

- [ ] **Step 1: Locate the per-helper policy table**

Find the table that begins with `| Helper (canonical name) | Policy | Rationale |` (around line 312 — look for the row beginning `| \`verify_paper_audits.sh\` | A (gate) |`).

- [ ] **Step 2: Insert a new row immediately after the `verify_paper_audits.sh` row**

Replace:

```markdown
| `verify_paper_audits.sh` | A (gate) | Exit code is the source of truth for submission readiness |
| `save_trace.sh` | C (forensic) | Trace artifacts are load-bearing for audit traceability and reviewer-independence audit |
```

with:

```markdown
| `verify_paper_audits.sh` | A (gate) | Exit code is the source of truth for submission readiness |
| `loop_budget.py` | A (gate) | Exit code is the gate for subscription quota; unresolved means the auto-review-loop cannot enforce its budget |
| `save_trace.sh` | C (forensic) | Trace artifacts are load-bearing for audit traceability and reviewer-independence audit |
```

- [ ] **Step 3: Commit**

```bash
git add skills/shared-references/integration-contract.md
git commit -m "docs(integration-contract): classify loop_budget.py as Policy A"
```

---

## Task 10: Patch `auto-review-loop` SKILL.md

**Files:**
- Modify: `skills/auto-review-loop/SKILL.md`

- [ ] **Step 1: Locate the Loop boundary**

Find the line `### Loop (repeat up to MAX_ROUNDS)` (around line 79). The new section will be inserted **immediately before** that line, so the resolver + budget guard runs before the first iteration and the check/record instructions are visible alongside the loop description.

- [ ] **Step 2: Insert the budget guard section**

Insert this block immediately before `### Loop (repeat up to MAX_ROUNDS)`:

````markdown
### Subscription Budget Guard

Before entering the loop, resolve the budget helper and refuse to start if it
cannot be found. See `skills/shared-references/loop-budget-resolution.md` for
the canonical resolver and configuration.

```bash
cd "$(git rev-parse --show-toplevel 2>/dev/null || pwd)" || exit 1
if [ -z "${ARIS_REPO:-}" ] && [ -f .aris/installed-skills.txt ]; then
    ARIS_REPO=$(awk -F'\t' '$1=="repo_root"{print $2; exit}' .aris/installed-skills.txt 2>/dev/null) || true
fi
LOOP_BUDGET_SCRIPT=".aris/tools/loop_budget.py"
[ -f "$LOOP_BUDGET_SCRIPT" ] || LOOP_BUDGET_SCRIPT="tools/loop_budget.py"
[ -f "$LOOP_BUDGET_SCRIPT" ] || { [ -n "${ARIS_REPO:-}" ] && LOOP_BUDGET_SCRIPT="$ARIS_REPO/tools/loop_budget.py"; }
[ -f "$LOOP_BUDGET_SCRIPT" ] || LOOP_BUDGET_SCRIPT=""

[ -n "$LOOP_BUDGET_SCRIPT" ] || {
  echo "ERROR: loop_budget.py not resolved (Policy A — gate)." >&2
  echo "       Fix: rerun bash tools/install_aris.sh, export ARIS_REPO, or copy the helper to tools/." >&2
  exit 1
}
```

**Per-iteration usage (mandatory):**

- **Before Phase A (reviewer call):** `python3 "$LOOP_BUDGET_SCRIPT" check --side codex` — if exit code is non-zero, write the round's pending state to `review-stage/REVIEW_STATE.json` and stop the loop with the message the tool printed.
- **After a successful reviewer call:** `python3 "$LOOP_BUDGET_SCRIPT" record --side codex --skill auto-review-loop`.
- **Before Phase C (executor implements fixes):** `python3 "$LOOP_BUDGET_SCRIPT" check --side claude` — same stop semantics.
- **After a successful executor turn:** `python3 "$LOOP_BUDGET_SCRIPT" record --side claude --skill auto-review-loop`.

A stop here is a normal, expected outcome — not a failure. Run
`python3 "$LOOP_BUDGET_SCRIPT" status` later to see when the next slot frees,
then re-invoke the skill to resume from the saved state.

````

- [ ] **Step 3: Verify the insert lands in the right place**

Run: `grep -n "Subscription Budget Guard\|### Loop (repeat" skills/auto-review-loop/SKILL.md`
Expected: two lines, `Subscription Budget Guard` immediately preceding `### Loop (repeat up to MAX_ROUNDS)`.

- [ ] **Step 4: Commit**

```bash
git add skills/auto-review-loop/SKILL.md
git commit -m "feat(auto-review-loop): add subscription budget guard"
```

---

## Task 11: Patch `auto-review-loop-llm` SKILL.md

**Files:**
- Modify: `skills/auto-review-loop-llm/SKILL.md`

- [ ] **Step 1: Locate the Loop boundary**

Find the line `### Loop (up to MAX_ROUNDS)` (around line 112).

- [ ] **Step 2: Insert the budget guard section**

Insert this block immediately before `### Loop (up to MAX_ROUNDS)`:

````markdown
### Subscription Budget Guard

Before entering the loop, resolve the budget helper and refuse to start if it
cannot be found. See `skills/shared-references/loop-budget-resolution.md`.

```bash
cd "$(git rev-parse --show-toplevel 2>/dev/null || pwd)" || exit 1
if [ -z "${ARIS_REPO:-}" ] && [ -f .aris/installed-skills.txt ]; then
    ARIS_REPO=$(awk -F'\t' '$1=="repo_root"{print $2; exit}' .aris/installed-skills.txt 2>/dev/null) || true
fi
LOOP_BUDGET_SCRIPT=".aris/tools/loop_budget.py"
[ -f "$LOOP_BUDGET_SCRIPT" ] || LOOP_BUDGET_SCRIPT="tools/loop_budget.py"
[ -f "$LOOP_BUDGET_SCRIPT" ] || { [ -n "${ARIS_REPO:-}" ] && LOOP_BUDGET_SCRIPT="$ARIS_REPO/tools/loop_budget.py"; }
[ -f "$LOOP_BUDGET_SCRIPT" ] || LOOP_BUDGET_SCRIPT=""

[ -n "$LOOP_BUDGET_SCRIPT" ] || {
  echo "ERROR: loop_budget.py not resolved (Policy A — gate)." >&2
  echo "       Fix: rerun bash tools/install_aris.sh, export ARIS_REPO, or copy the helper to tools/." >&2
  exit 1
}
```

**Per-iteration usage (mandatory):**

- **Before Phase A (reviewer call):** `python3 "$LOOP_BUDGET_SCRIPT" check --side codex` — if exit code is non-zero, persist round state to `review-stage/REVIEW_STATE.json` and stop the loop with the message the tool printed.
- **After a successful reviewer call:** `python3 "$LOOP_BUDGET_SCRIPT" record --side codex --skill auto-review-loop-llm`.
- **Before Phase C (executor implements fixes):** `python3 "$LOOP_BUDGET_SCRIPT" check --side claude` — same stop semantics.
- **After a successful executor turn:** `python3 "$LOOP_BUDGET_SCRIPT" record --side claude --skill auto-review-loop-llm`.

> **Reviewer-side note:** `auto-review-loop-llm` can target any
> OpenAI-compatible reviewer, but for v1 the budget is always recorded as
> `--side codex` regardless of backend. If you use a third-party
> non-Codex-OAuth reviewer and want to disable that side's cap, set
> `CODEX_LOOP_MAX_ITERATIONS=999999`.

A stop here is a normal, expected outcome — not a failure. Run
`python3 "$LOOP_BUDGET_SCRIPT" status` to see when the next slot frees.
````

- [ ] **Step 3: Verify**

Run: `grep -n "Subscription Budget Guard\|### Loop (up to" skills/auto-review-loop-llm/SKILL.md`
Expected: two lines, guard immediately preceding the Loop heading.

- [ ] **Step 4: Commit**

```bash
git add skills/auto-review-loop-llm/SKILL.md
git commit -m "feat(auto-review-loop-llm): add subscription budget guard"
```

---

## Task 12: Patch `auto-review-loop-minimax` SKILL.md

**Files:**
- Modify: `skills/auto-review-loop-minimax/SKILL.md`

- [ ] **Step 1: Locate the Loop boundary**

Find the line `### Loop (repeat up to MAX_ROUNDS)` (around line 98).

- [ ] **Step 2: Insert the budget guard section**

Insert this block immediately before `### Loop (repeat up to MAX_ROUNDS)`:

````markdown
### Subscription Budget Guard

Before entering the loop, resolve the budget helper and refuse to start if it
cannot be found. See `skills/shared-references/loop-budget-resolution.md`.

```bash
cd "$(git rev-parse --show-toplevel 2>/dev/null || pwd)" || exit 1
if [ -z "${ARIS_REPO:-}" ] && [ -f .aris/installed-skills.txt ]; then
    ARIS_REPO=$(awk -F'\t' '$1=="repo_root"{print $2; exit}' .aris/installed-skills.txt 2>/dev/null) || true
fi
LOOP_BUDGET_SCRIPT=".aris/tools/loop_budget.py"
[ -f "$LOOP_BUDGET_SCRIPT" ] || LOOP_BUDGET_SCRIPT="tools/loop_budget.py"
[ -f "$LOOP_BUDGET_SCRIPT" ] || { [ -n "${ARIS_REPO:-}" ] && LOOP_BUDGET_SCRIPT="$ARIS_REPO/tools/loop_budget.py"; }
[ -f "$LOOP_BUDGET_SCRIPT" ] || LOOP_BUDGET_SCRIPT=""

[ -n "$LOOP_BUDGET_SCRIPT" ] || {
  echo "ERROR: loop_budget.py not resolved (Policy A — gate)." >&2
  echo "       Fix: rerun bash tools/install_aris.sh, export ARIS_REPO, or copy the helper to tools/." >&2
  exit 1
}
```

**Per-iteration usage (mandatory):**

- **Before Phase A (reviewer call):** `python3 "$LOOP_BUDGET_SCRIPT" check --side codex` — if exit code is non-zero, persist round state to `review-stage/REVIEW_STATE.json` and stop the loop with the message the tool printed.
- **After a successful reviewer call:** `python3 "$LOOP_BUDGET_SCRIPT" record --side codex --skill auto-review-loop-minimax`.
- **Before Phase C (executor implements fixes):** `python3 "$LOOP_BUDGET_SCRIPT" check --side claude` — same stop semantics.
- **After a successful executor turn:** `python3 "$LOOP_BUDGET_SCRIPT" record --side claude --skill auto-review-loop-minimax`.

> **Reviewer-side note:** the MiniMax reviewer is not subject to Codex OAuth
> quota; v1 still records `--side codex` for accounting symmetry. If you want
> to disable that side's cap, set `CODEX_LOOP_MAX_ITERATIONS=999999`.

A stop here is a normal, expected outcome — not a failure. Run
`python3 "$LOOP_BUDGET_SCRIPT" status` to see when the next slot frees.
````

- [ ] **Step 3: Verify**

Run: `grep -n "Subscription Budget Guard\|### Loop (repeat" skills/auto-review-loop-minimax/SKILL.md`
Expected: two lines, guard immediately preceding the Loop heading.

- [ ] **Step 4: Commit**

```bash
git add skills/auto-review-loop-minimax/SKILL.md
git commit -m "feat(auto-review-loop-minimax): add subscription budget guard"
```

---

## Task 13: Final verification

**Files:** none modified.

- [ ] **Step 1: Run the test suite end-to-end**

Run: `python3 -m unittest tests.test_loop_budget -v`
Expected: 16 PASS.

- [ ] **Step 2: Confirm the three skills reference the helper**

Run:
```bash
grep -l "LOOP_BUDGET_SCRIPT" skills/auto-review-loop/SKILL.md skills/auto-review-loop-llm/SKILL.md skills/auto-review-loop-minimax/SKILL.md
```
Expected: all three filenames printed.

- [ ] **Step 3: Confirm policy table has the row**

Run: `grep "loop_budget.py.*A (gate)" skills/shared-references/integration-contract.md`
Expected: one matching line.

- [ ] **Step 4: Confirm resolver doc exists**

Run: `ls -l skills/shared-references/loop-budget-resolution.md`
Expected: file listed, non-empty.

- [ ] **Step 5: One-shot manual gate test**

```bash
export ARIS_USAGE_DIR=$(mktemp -d)
CLAUDE_LOOP_MAX_ITERATIONS=1 python3 tools/loop_budget.py record --side claude --skill manual
CLAUDE_LOOP_MAX_ITERATIONS=1 python3 tools/loop_budget.py check --side claude
echo "exit=$?"   # expect: STOP message + exit=2
unset ARIS_USAGE_DIR
```

Expected output ends with `exit=2`.

No commit (no file changes).

---

## Self-review notes

- **Spec coverage:** Each numbered §Components item maps to a task: `loop_budget.py` (Tasks 1–6, 7), `test_loop_budget.py` (Tasks 1–6), resolver doc (Task 8), `integration-contract.md` row (Task 9), three SKILL.md patches (Tasks 10–12). §Testing tests 1–10 are covered; test 11 (helper-resolution-failure smoke test) is covered manually in Task 13 step 5.
- **No placeholders:** every code block has runnable code, every command has expected output, every file path is exact.
- **Type/identifier consistency:** `usage_path`, `load_records`, `filter_window`, `_parse_ts`, `_config_for`, `_warn_threshold`, `cmd_record`, `cmd_check`, `cmd_status`, `build_parser`, `main` — names introduced in Task 1/2/3 are used unchanged in Tasks 3/4/5/6. Env var names (`CLAUDE_LOOP_MAX_ITERATIONS`, `CLAUDE_LOOP_WINDOW_HOURS`, `CODEX_LOOP_MAX_ITERATIONS`, `CODEX_LOOP_WINDOW_HOURS`, `CLAUDE_LOOP_WARN_AT`, `ARIS_USAGE_DIR`) match across tasks, the spec, and the resolver doc.
- **DRY:** the resolver block is duplicated across three SKILL.md files because skills are markdown instructions consumed verbatim — they cannot `[include]` a shared block. The canonical version lives in the resolver doc (Task 8) and is the source of truth for future skill additions.
- **YAGNI:** no token accounting, no auto-resume, no provider-API calls, no file locking. All deferred to v2 per the spec.
