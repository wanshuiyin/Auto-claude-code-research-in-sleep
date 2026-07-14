#!/usr/bin/env python3
"""tools/skill_picker.py — checkbox TUI for selective install (#366).

Model tests exercise the pure-python selection logic directly; the two
end-to-end tests drive the real curses UI through a pty via expect
(skipped where /usr/bin/expect is unavailable).
"""
import importlib.util
import subprocess
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PICKER = REPO_ROOT / "tools" / "skill_picker.py"

spec = importlib.util.spec_from_file_location("skill_picker", PICKER)
sp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sp)

CATALOG = """\
# comment
group\tg1\tGroup One\tfirst group
group\tg2\tGroup Two\tsecond group
skill\talpha\tg1\t-\talpha desc
skill\tbeta\tg1\talpha\tbeta desc
skill\tgamma\tg2\t-\tgamma desc
"""


class ModelTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="picker-"))
        self.catalog = self.tmp / "skill-groups.tsv"
        self.catalog.write_text(CATALOG)
        self.groups, self.skills = sp.parse_catalog(self.catalog)

    def tearDown(self):
        import shutil

        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_parse_catalog(self):
        self.assertEqual([g[0] for g in self.groups], ["g1", "g2"])
        self.assertEqual(self.skills["beta"], ("g1", ["alpha"], "beta desc"))

    def test_build_rows_keeps_uncataloged_skills(self):
        rows = sp.build_rows(self.groups, self.skills,
                             ["alpha", "beta", "gamma", "orphan"])
        kinds = [(r.kind, r.name) for r in rows]
        self.assertIn(("group", "ungrouped"), kinds)
        self.assertIn(("skill", "orphan"), kinds)

    def test_build_rows_skips_empty_groups(self):
        rows = sp.build_rows(self.groups, self.skills, ["gamma"])
        self.assertEqual([(r.kind, r.name) for r in rows],
                         [("group", "g2"), ("skill", "gamma")])

    def test_group_toggle_all_none(self):
        rows = sp.build_rows(self.groups, self.skills, ["alpha", "beta", "gamma"])
        selected = set()
        g1 = next(i for i, r in enumerate(rows) if r.name == "g1")
        sp.toggle(rows, g1, selected)  # none -> all
        self.assertEqual(selected, {"alpha", "beta"})
        sp.toggle(rows, g1, selected)  # all -> none
        self.assertEqual(selected, set())

    def test_group_toggle_partial_selects_all(self):
        rows = sp.build_rows(self.groups, self.skills, ["alpha", "beta", "gamma"])
        selected = {"alpha"}
        g1 = next(i for i, r in enumerate(rows) if r.name == "g1")
        self.assertEqual(sp.group_state(rows, "g1", selected), "some")
        sp.toggle(rows, g1, selected)  # partial -> all
        self.assertEqual(selected, {"alpha", "beta"})

    def test_skill_toggle(self):
        rows = sp.build_rows(self.groups, self.skills, ["alpha", "beta", "gamma"])
        selected = set()
        i = next(i for i, r in enumerate(rows) if r.name == "alpha")
        sp.toggle(rows, i, selected)
        self.assertEqual(selected, {"alpha"})
        sp.toggle(rows, i, selected)
        self.assertEqual(selected, set())

    def test_render_line_marks(self):
        rows = sp.build_rows(self.groups, self.skills, ["alpha", "beta", "gamma"])
        selected = {"alpha"}
        g1 = next(i for i, r in enumerate(rows) if r.name == "g1")
        a = next(i for i, r in enumerate(rows) if r.name == "alpha")
        b = next(i for i, r in enumerate(rows) if r.name == "beta")
        self.assertIn("[~]", sp.render_line(rows, g1, selected, 200))
        self.assertIn("(1/2)", sp.render_line(rows, g1, selected, 200))
        self.assertIn("[x]", sp.render_line(rows, a, selected, 200))
        self.assertIn("[ ]", sp.render_line(rows, b, selected, 200))
        self.assertIn("依赖", sp.render_line(rows, b, selected, 200))

    def test_no_tty_exits_2(self):
        avail = self.tmp / "avail.txt"
        avail.write_text("alpha\n")
        out = self.tmp / "out.txt"
        result = subprocess.run(
            ["python3", str(PICKER), "--catalog", str(self.catalog),
             "--available", str(avail), "--out", str(out)],
            capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 2)
        self.assertFalse(out.exists())


@unittest.skipUnless(Path("/usr/bin/expect").exists(), "expect not available")
class CursesE2ETest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="picker-e2e-"))
        (self.tmp / "skill-groups.tsv").write_text(CATALOG)
        (self.tmp / "avail.txt").write_text("alpha\nbeta\ngamma\n")

    def tearDown(self):
        import shutil

        shutil.rmtree(self.tmp, ignore_errors=True)

    def _drive(self, keys_tcl):
        script = self.tmp / "drive.exp"
        script.write_text(
            "set timeout 15\n"
            'set env(TERM) "xterm"\n'
            f"spawn python3 {PICKER} --catalog {self.tmp}/skill-groups.tsv "
            f"--available {self.tmp}/avail.txt --out {self.tmp}/out.txt\n"
            "sleep 1\n"
            f"{keys_tcl}\n"
            "expect eof\n"
            "catch wait result\n"
            "exit [lindex $result 3]\n"
        )
        return subprocess.run(["/usr/bin/expect", str(script)],
                              capture_output=True, text=True)

    def test_select_all_and_confirm(self):
        result = self._drive('send "a"\nsleep 1\nsend "\\r"')
        self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)
        out = (self.tmp / "out.txt").read_text().split()
        self.assertEqual(sorted(out), ["alpha", "beta", "gamma"])

    def test_group_space_then_confirm(self):
        # cursor starts on group g1: space selects alpha+beta, enter confirms
        result = self._drive('send " "\nsleep 1\nsend "\\r"')
        self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)
        out = (self.tmp / "out.txt").read_text().split()
        self.assertEqual(sorted(out), ["alpha", "beta"])

    def test_abort_with_q(self):
        result = self._drive('send "q"')
        self.assertEqual(result.returncode, 1, msg=result.stdout + result.stderr)
        self.assertFalse((self.tmp / "out.txt").exists())


if __name__ == "__main__":
    unittest.main()
