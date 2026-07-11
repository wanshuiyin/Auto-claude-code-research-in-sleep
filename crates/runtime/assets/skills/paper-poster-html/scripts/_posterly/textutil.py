"""Make a string safe to print to a terminal / CI log / pasted issue.

Runtime output is otherwise all-ASCII (rounds 7-9), but USER-derived
fragments -- orphan text, an image src, a MathJax error, raw pdfinfo
output -- can re-inject Unicode that source-level grep can't catch.
Escape it at the output boundary so terminal output never mojibakes.
"""
from __future__ import annotations


def ascii_safe(s: object) -> str:
    r"""Backslash-escape any non-ASCII char.

    ``ascii_safe("1.18-1.30× ↑")`` -> ``"1.18-1.30\\xd7 \\u2191"``.
    """
    return str(s).encode("ascii", "backslashreplace").decode("ascii")
