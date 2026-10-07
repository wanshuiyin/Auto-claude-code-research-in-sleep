"""Run: python3 test_codex.py. Temporary databases; no real sessions modified."""
import os
import json
import sqlite3
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

import focus
import scanner


def main():
    now = int(time.time())
    with tempfile.TemporaryDirectory() as folder:
        home = Path(folder)
        state = sqlite3.connect(home / "state_5.sqlite")
        history = sqlite3.connect(home / "thread_history_1.sqlite")
        try:
            state.execute("PRAGMA journal_mode=WAL")
            state.execute("CREATE TABLE threads (id, name, title, cwd, updated_at, source, archived)")
            history.execute("CREATE TABLE thread_turns (thread_id, turn_id, status, started_at, completed_at, rollout_ordinal)")
            history.execute("CREATE TABLE thread_items (thread_id, turn_id, created_at_ms, started_at_ms, completed_at_ms)")
            cases = [("running", "inProgress", now, 0), ("quiet", "inProgress", now - 400, 0),
                     ("done", "completed", now - 40, 0), ("failed", "failed", now - 30, 0),
                     ("stopped", "interrupted", now - 20, 0), ("stale", "inProgress", now - 4000, 0),
                     ("archived", "inProgress", now, 1), ("unknown", "unexpected", now, 0)]
            for tid, status, timestamp, archived in cases:
                state.execute("INSERT INTO threads VALUES (?,?,?,?,?,?,?)", (tid, tid, "title", "/project", now, "vscode", archived))
                history.execute("INSERT INTO thread_turns VALUES (?,?,?,?,?,?)",
                                (tid, "turn", status, timestamp, None if status == "inProgress" else timestamp, 1))
            history.execute("INSERT INTO thread_turns VALUES (?,?,?,?,?,?)", ("done", "old", "inProgress", now - 500, None, 0))
            history.execute("INSERT INTO thread_items VALUES (?,?,?,?,?)", ("quiet", "turn", now * 1000, None, None))
            state.commit()
            history.commit()
            sessions_dir = home / ".claude" / "sessions"
            sessions_dir.mkdir(parents=True)
            (sessions_dir / "123.json").write_text(json.dumps({"pid": 123, "status": "waiting", "updatedAt": 1, "name": "Claude waiting"}))
            with patch.dict(os.environ, {"CODEX_HOME": folder}), patch.object(scanner, "SESSIONS_DIR", sessions_dir):
                rows = {s.name: s for s in scanner.scan() if s.source == "Codex"}
                assert rows["running"].triage == scanner.WORKING  # includes live WAL
                assert rows["quiet"].triage == scanner.WORKING  # fresh activity in long turn
                history.execute("DELETE FROM thread_items")
                history.commit()
                rows = {s.name: s for s in scanner.scan() if s.source == "Codex"}
                assert rows["quiet"].triage == scanner.UNKNOWN
                assert rows["done"].triage == scanner.IDLE_DONE  # newest turn wins
                assert rows["failed"].triage == scanner.NEEDS_ATTENTION
                assert scanner.display_label(rows["stopped"]) == "stopped"
                assert rows["stale"].triage == scanner.STALE_HIDDEN
                assert rows["unknown"].triage == scanner.UNKNOWN
                assert "archived" not in rows
                assert all(s.triage != scanner.NEEDS_APPROVAL for s in rows.values())
                assert scanner.scan()[0].source == "Claude"
                history.execute("DROP TABLE thread_turns")
                history.commit()
                rows = scanner.scan()
                assert any(s.source == "Codex" and s.triage == scanner.UNKNOWN for s in rows)
                assert any(s.source == "Claude" and s.triage == scanner.NEEDS_APPROVAL for s in rows)
            missing = home / "missing"
            with patch.dict(os.environ, {"CODEX_HOME": str(missing)}):
                assert scanner._scan_codex() == []
                assert not missing.exists()
            (home / "state_10.sqlite").touch()
            assert scanner._codex_store(home, "state").name == "state_10.sqlite"
        finally:
            state.close()
            history.close()
    with patch.object(focus.subprocess, "run") as run:
        assert not focus.focus_codex("invalid;open something")["ok"]
        run.assert_not_called()
        run.return_value.returncode = 0
        run.return_value.stderr = ""
        tid = "00000000-0000-4000-8000-000000000001"
        assert focus.focus_codex(tid)["ok"]
        assert run.call_args.args[0] == ["open", "codex://threads/" + tid]
    print("PASS: states, live WAL, activity, latest turn, archived, Claude coexistence, failures, safe navigation")


if __name__ == "__main__":
    main()
