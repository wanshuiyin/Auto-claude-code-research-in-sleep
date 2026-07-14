#!/usr/bin/env python3
"""Interactive checkbox picker for ARIS selective install (#366).

Reads the skill catalog (tools/skill-groups.tsv) plus the set of available
upstream skills, renders a curses checkbox tree (groups with their skills
indented below), and writes the confirmed selection to --out, one skill
name per line.

Keys:
  Up/Down, j/k   move cursor
  Space          toggle item under cursor — on a group row this toggles
                 ALL of the group's skills (all-on -> all-off, else all-on)
  a / n          select all / select none
  PgUp/PgDn      page
  Enter          confirm selection
  q / Esc        abort

Exit codes:
  0  confirmed (--out written)
  1  user aborted
  2  environment unusable (no curses/tty) — caller should fall back to the
     classic per-group prompts

The selection model is pure-python and unit-tested in
tests/test_skill_picker.py; only run_picker() touches curses.
"""
import argparse
import sys

UNGROUPED = ("ungrouped", "未分组", "上游存在但 catalog 尚未归组的 skill")


def parse_catalog(path):
    """Return (groups, skills): groups = [(gid, display, desc)] in file order;
    skills = {name: (group, requires_list, desc)}."""
    groups, skills = [], {}
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.rstrip("\n")
            if not line or line.startswith("#"):
                continue
            fields = line.split("\t")
            if fields[0] == "group" and len(fields) >= 4:
                groups.append((fields[1], fields[2], fields[3]))
            elif fields[0] == "skill" and len(fields) >= 4:
                requires = [] if fields[3] == "-" else fields[3].split(",")
                desc = fields[4] if len(fields) >= 5 else ""
                skills[fields[1]] = (fields[2], requires, desc)
    return groups, skills


class Row:
    __slots__ = ("kind", "name", "display", "desc", "group", "has_deps")

    def __init__(self, kind, name, display, desc, group=None, has_deps=False):
        self.kind = kind  # "group" | "skill"
        self.name = name
        self.display = display
        self.desc = desc
        self.group = group  # group id for skill rows
        self.has_deps = has_deps


def build_rows(groups, skills, available):
    """Flatten catalog + available set into display rows. Available skills the
    catalog doesn't know land in a trailing pseudo-group (never dropped)."""
    rows = []
    seen = set()
    for gid, display, desc in groups:
        members = [n for n in available if n in skills and skills[n][0] == gid]
        if not members:
            continue
        rows.append(Row("group", gid, display, desc))
        for name in members:
            _, requires, sdesc = skills[name]
            rows.append(Row("skill", name, name, sdesc, gid, bool(requires)))
            seen.add(name)
    orphans = [n for n in available if n not in seen]
    if orphans:
        gid, display, desc = UNGROUPED
        rows.append(Row("group", gid, display, desc))
        for name in orphans:
            rows.append(Row("skill", name, name, "", gid))
    return rows


def group_members(rows, gid):
    return [r.name for r in rows if r.kind == "skill" and r.group == gid]


def group_state(rows, gid, selected):
    """'all' | 'some' | 'none' for a group's selection state."""
    members = group_members(rows, gid)
    hit = sum(1 for m in members if m in selected)
    if hit == 0:
        return "none"
    return "all" if hit == len(members) else "some"


def toggle(rows, idx, selected):
    """Space semantics: skill toggles itself; group toggles all members
    (all-selected -> none, anything else -> all)."""
    row = rows[idx]
    if row.kind == "skill":
        if row.name in selected:
            selected.discard(row.name)
        else:
            selected.add(row.name)
        return
    members = group_members(rows, row.name)
    if group_state(rows, row.name, selected) == "all":
        selected.difference_update(members)
    else:
        selected.update(members)


def render_line(rows, idx, selected, width):
    """One display line (no curses dependency, unit-testable)."""
    row = rows[idx]
    if row.kind == "group":
        mark = {"all": "[*]", "some": "[~]", "none": "[ ]"}[
            group_state(rows, row.name, selected)
        ]
        members = group_members(rows, row.name)
        hit = sum(1 for m in members if m in selected)
        line = "%s %s %s — %s  (%d/%d)" % (
            mark, row.name, row.display, row.desc, hit, len(members))
    else:
        mark = "[x]" if row.name in selected else "[ ]"
        dep = "  (+依赖自动带入)" if row.has_deps else ""
        desc = ("  %s" % row.desc) if row.desc else ""
        line = "    %s %s%s%s" % (mark, row.display, desc, dep)
    return line[: max(1, width - 1)]


HEADER = "ARIS skill 选择 — Space 勾选(组行=整组) · a 全选 · n 清空 · Enter 确认 · q 退出"


def run_picker(rows, selected):  # pragma: no cover — curses UI, tested via pty
    import curses

    def main(stdscr):
        curses.curs_set(0)
        stdscr.keypad(True)
        cursor, offset = 0, 0
        while True:
            height, width = stdscr.getmaxyx()
            body = height - 3
            if cursor < offset:
                offset = cursor
            if cursor >= offset + body:
                offset = cursor - body + 1
            stdscr.erase()
            stdscr.addnstr(0, 0, HEADER, width - 1, curses.A_BOLD)
            for i in range(offset, min(len(rows), offset + body)):
                attr = curses.A_REVERSE if i == cursor else curses.A_NORMAL
                if rows[i].kind == "group" and i != cursor:
                    attr |= curses.A_BOLD
                stdscr.addnstr(2 + i - offset, 0,
                               render_line(rows, i, selected, width),
                               width - 1, attr)
            n_skills = sum(1 for r in rows if r.kind == "skill")
            stdscr.addnstr(height - 1, 0,
                           " 已选 %d / %d " % (len(selected), n_skills),
                           width - 1, curses.A_REVERSE)
            stdscr.refresh()
            key = stdscr.getch()
            if key in (curses.KEY_UP, ord("k")):
                cursor = max(0, cursor - 1)
            elif key in (curses.KEY_DOWN, ord("j")):
                cursor = min(len(rows) - 1, cursor + 1)
            elif key == curses.KEY_PPAGE:
                cursor = max(0, cursor - body)
            elif key == curses.KEY_NPAGE:
                cursor = min(len(rows) - 1, cursor + body)
            elif key == ord(" "):
                toggle(rows, cursor, selected)
            elif key == ord("a"):
                selected.update(r.name for r in rows if r.kind == "skill")
            elif key == ord("n"):
                selected.clear()
            elif key in (curses.KEY_ENTER, 10, 13):
                return True
            elif key in (ord("q"), 27):
                return False

    return curses.wrapper(main)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--catalog", required=True)
    ap.add_argument("--available", required=True,
                    help="file with one available upstream skill name per line")
    ap.add_argument("--out", required=True,
                    help="file to write the selected skill names to")
    ap.add_argument("--preselect",
                    help="optional file with names to pre-check")
    args = ap.parse_args(argv)

    groups, skills = parse_catalog(args.catalog)
    with open(args.available, encoding="utf-8") as fh:
        available = [l.strip() for l in fh if l.strip()]
    rows = build_rows(groups, skills, available)
    if not rows:
        print("skill_picker: nothing available to select", file=sys.stderr)
        return 2

    selected = set()
    if args.preselect:
        with open(args.preselect, encoding="utf-8") as fh:
            selected = {l.strip() for l in fh if l.strip()} & set(available)

    if not (sys.stdin.isatty() and sys.stdout.isatty()):
        print("skill_picker: no tty — falling back", file=sys.stderr)
        return 2
    try:
        confirmed = run_picker(rows, selected)
    except Exception as exc:  # curses import/terminal failures → fallback
        print("skill_picker: %s — falling back" % exc, file=sys.stderr)
        return 2

    if not confirmed:
        return 1
    order = [r.name for r in rows if r.kind == "skill"]
    with open(args.out, "w", encoding="utf-8") as fh:
        for name in order:
            if name in selected:
                fh.write(name + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
