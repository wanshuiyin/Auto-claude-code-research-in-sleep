"""kill_screen must quit only the screen named exactly like the job.

`screen -S <name>` matches session names by prefix, so cleaning up a job whose
screen already exited would otherwise quit a live job whose id extends it
(`s42_N384_n50000` vs `s42_N384_n500000` in the build_manifest.py example).
"""

import importlib.util
from pathlib import Path

MODULE_PATH = (
    Path(__file__).resolve().parents[1]
    / "skills" / "experiment-queue" / "scripts" / "queue_manager.py"
)
SPEC = importlib.util.spec_from_file_location("queue_manager", MODULE_PATH)
queue_manager = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(queue_manager)

SCREEN_LS = (
    "There are screens on:\n"
    "\t4242.EQ_s42_N384_n500000\t(11/27/26 16:57:25)\t(Detached)\n"
    "\t4300.EQ_s42_N384_n150000\t(11/27/26 16:57:25)\t(Detached)\n"
    "2 Sockets in /run/screen/S-user.\n"
)


def _fake_run(listing, calls):
    def run(cmd, check=False, capture=True):
        calls.append(cmd)
        if cmd == "screen -ls":
            return listing, 0
        return "", 0
    return run


def test_kill_screen_leaves_a_longer_name_alone(monkeypatch):
    calls = []
    monkeypatch.setattr(queue_manager, "run", _fake_run(SCREEN_LS, calls))

    queue_manager.kill_screen("EQ_s42_N384_n50000")

    assert [c for c in calls if "-X quit" in c] == []


def test_kill_screen_quits_the_exact_session(monkeypatch):
    listing = SCREEN_LS.replace(
        "2 Sockets", "\t4100.EQ_s42_N384_n50000\t(11/27/26 16:57:25)\t(Detached)\n3 Sockets"
    )
    calls = []
    monkeypatch.setattr(queue_manager, "run", _fake_run(listing, calls))

    queue_manager.kill_screen("EQ_s42_N384_n50000")

    assert [c for c in calls if "-X quit" in c] == ["screen -S 4100.EQ_s42_N384_n50000 -X quit"]
