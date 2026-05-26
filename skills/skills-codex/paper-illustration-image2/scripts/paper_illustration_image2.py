#!/usr/bin/env python3
"""Integration helper for the paper-illustration-image2 workflow."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def resolve_workspace(raw_workspace: str | None) -> Path:
    workspace = Path(raw_workspace).expanduser() if raw_workspace else Path.cwd()
    return workspace.resolve()


def output_dir(workspace: Path) -> Path:
    return (workspace / "figures" / "ai_generated").resolve()


def ensure_png_file(path: Path) -> None:
    if not path.is_file():
        raise FileNotFoundError(f"missing PNG file: {path}")
    if not path.read_bytes().startswith(PNG_SIGNATURE):
        raise ValueError(f"expected a PNG file: {path}")


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def emit_json(payload: dict, *, json_out: Path | None = None) -> int:
    if json_out is not None:
        write_json(json_out, payload)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if payload.get("ok", False) else 1


def run_preflight(workspace: Path, *, json_out: Path | None = None) -> int:
    figures_dir = output_dir(workspace)
    figures_dir.mkdir(parents=True, exist_ok=True)
    codex_bin = shutil.which("codex")
    payload = {
        "ok": False,
        "workspace": str(workspace),
        "outputDir": str(figures_dir),
        "codexBin": codex_bin,
        "checkedAt": utc_now(),
    }
    if codex_bin is None:
        payload["error"] = "codex CLI not found on PATH"
        return emit_json(payload, json_out=json_out)

    try:
        result = subprocess.run(
            [codex_bin, "debug", "app-server", "send-message-v2", "ping"],
            cwd=str(workspace),
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
    except subprocess.TimeoutExpired:
        payload["error"] = "codex app-server ping timed out"
        return emit_json(payload, json_out=json_out)

    payload["returncode"] = result.returncode
    payload["ok"] = result.returncode == 0
    if result.returncode != 0:
        payload["error"] = (result.stderr or result.stdout or "codex app-server ping failed").strip()
    return emit_json(payload, json_out=json_out)


def build_latex_include(caption: str, label: str) -> str:
    return "\n".join(
        [
            r"\begin{figure*}[t]",
            r"    \centering",
            r"    \includegraphics[width=0.95\textwidth]{figures/ai_generated/figure_final.png}",
            f"    \\caption{{{caption}}}",
            f"    \\label{{{label}}}",
            r"\end{figure*}",
            "",
        ]
    )


def run_finalize(
    workspace: Path,
    *,
    best_image: Path,
    caption: str,
    label: str,
    score: float | None,
    review_summary: str | None,
    json_out: Path | None = None,
) -> int:
    figures_dir = output_dir(workspace)
    figures_dir.mkdir(parents=True, exist_ok=True)
    best_image = best_image.expanduser().resolve()
    ensure_png_file(best_image)

    final_image = figures_dir / "figure_final.png"
    latex_include = figures_dir / "latex_include.tex"
    review_log = figures_dir / "review_log.json"

    shutil.copy2(best_image, final_image)
    latex_include.write_text(build_latex_include(caption, label), encoding="utf-8")

    review_payload = {
        "ok": True,
        "finalizedAt": utc_now(),
        "workspace": str(workspace),
        "bestImage": str(best_image),
        "finalImage": str(final_image),
        "score": score,
        "reviewSummary": review_summary,
        "caption": caption,
        "label": label,
    }
    write_json(review_log, review_payload)

    payload = {
        "ok": True,
        "workspace": str(workspace),
        "artifacts": {
            "figureFinal": str(final_image),
            "latexInclude": str(latex_include),
            "reviewLog": str(review_log),
        },
        "score": score,
        "reviewSummary": review_summary,
        "finalizedAt": review_payload["finalizedAt"],
    }
    return emit_json(payload, json_out=json_out)


def run_verify(workspace: Path, *, json_out: Path | None = None) -> int:
    figures_dir = output_dir(workspace)
    final_image = figures_dir / "figure_final.png"
    latex_include = figures_dir / "latex_include.tex"
    review_log = figures_dir / "review_log.json"

    errors: list[str] = []
    artifacts = {
        "figureFinal": {"path": str(final_image), "exists": final_image.is_file()},
        "latexInclude": {"path": str(latex_include), "exists": latex_include.is_file()},
        "reviewLog": {"path": str(review_log), "exists": review_log.is_file()},
    }

    if final_image.is_file():
        try:
            ensure_png_file(final_image)
        except (FileNotFoundError, ValueError) as exc:
            errors.append(str(exc))
    else:
        errors.append(f"missing artifact: {final_image}")

    if latex_include.is_file():
        latex_text = latex_include.read_text(encoding="utf-8")
        if "figure_final.png" not in latex_text:
            errors.append("latex_include.tex does not reference figures/ai_generated/figure_final.png")
    else:
        errors.append(f"missing artifact: {latex_include}")

    if review_log.is_file():
        try:
            review_payload = json.loads(review_log.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            errors.append(f"review_log.json is not valid JSON: {exc}")
        else:
            if str(review_payload.get("finalImage")) != str(final_image):
                errors.append("review_log.json does not point at figure_final.png")
    else:
        errors.append(f"missing artifact: {review_log}")

    payload = {
        "ok": not errors,
        "workspace": str(workspace),
        "checkedAt": utc_now(),
        "artifacts": artifacts,
        "errors": errors,
    }
    return emit_json(payload, json_out=json_out)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    preflight = subparsers.add_parser("preflight", help="Check that Codex image generation is available")
    preflight.add_argument("--workspace", help="Paper or project workspace root")
    preflight.add_argument("--json-out", help="Optional path to save the JSON result")

    finalize = subparsers.add_parser("finalize", help="Finalize the accepted figure artifacts")
    finalize.add_argument("--workspace", help="Paper or project workspace root")
    finalize.add_argument("--best-image", required=True, help="Accepted PNG to promote to figure_final.png")
    finalize.add_argument(
        "--caption",
        default="[Replace with a paper-ready caption].",
        help="Caption text to place in latex_include.tex",
    )
    finalize.add_argument("--label", default="fig:replace-me", help="LaTeX figure label")
    finalize.add_argument("--score", type=float, help="Final review score")
    finalize.add_argument("--review-summary", help="Short review summary for review_log.json")
    finalize.add_argument("--json-out", help="Optional path to save the JSON result")

    verify = subparsers.add_parser("verify", help="Verify that final artifacts were emitted correctly")
    verify.add_argument("--workspace", help="Paper or project workspace root")
    verify.add_argument("--json-out", help="Optional path to save the JSON result")

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    workspace = resolve_workspace(getattr(args, "workspace", None))
    json_out = Path(args.json_out).expanduser().resolve() if getattr(args, "json_out", None) else None

    if args.command == "preflight":
        return run_preflight(workspace, json_out=json_out)

    if args.command == "finalize":
        return run_finalize(
            workspace,
            best_image=Path(args.best_image),
            caption=args.caption,
            label=args.label,
            score=args.score,
            review_summary=args.review_summary,
            json_out=json_out,
        )

    if args.command == "verify":
        return run_verify(workspace, json_out=json_out)

    parser.error(f"unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
