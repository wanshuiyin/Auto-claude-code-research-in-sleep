#!/usr/bin/env python3
"""Validate repository skill frontmatter and tool declarations."""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

BASE_REQUIRED_FIELDS = ("name", "description")
NATIVE_REQUIRED_FIELDS = BASE_REQUIRED_FIELDS + ("allowed-tools",)
FIELD_RE = re.compile(r"^([A-Za-z0-9_-]+):\s*(.*)$")
BASH_RE = re.compile(r"^Bash\((.+)\)$")
MCP_RE = re.compile(r"^mcp__([A-Za-z0-9._*-]+)__([A-Za-z0-9._*-]+)$")
LEGACY_MCP_RE = re.compile(r"^mcp_[A-Za-z0-9.-]+(?:_[A-Za-z0-9.*-]+)+$")
VERSION_SUFFIX_RE = re.compile(r"^(?P<base>.+)-\d+\.\d+\.\d+$")
ALLOWED_SIMPLE_TOOLS = {
    "Agent",
    "Edit",
    "Glob",
    "Grep",
    "Read",
    "Skill",
    "WebFetch",
    "WebSearch",
    "Write",
}


@dataclass
class ValidationIssue:
    path: Path
    message: str

    def render(self) -> str:
        return f"{self.path.as_posix()}: {self.message}"


class FrontmatterError(Exception):
    """Raised when a SKILL.md file has invalid frontmatter."""


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate SKILL.md frontmatter and allowed-tools declarations."
    )
    parser.add_argument(
        "paths",
        nargs="*",
        default=["skills"],
        help="Skill files or directories to validate (defaults to skills/).",
    )
    return parser.parse_args(argv)


def iter_skill_files(paths: Sequence[str]) -> tuple[list[Path], list[ValidationIssue]]:
    skill_files: list[Path] = []
    issues: list[ValidationIssue] = []

    for raw_path in paths:
        path = Path(raw_path)
        if not path.exists():
            issues.append(ValidationIssue(path, "path does not exist"))
            continue
        if path.is_file():
            if path.name != "SKILL.md":
                issues.append(ValidationIssue(path, "expected a SKILL.md file"))
                continue
            skill_files.append(path)
            continue
        skill_files.extend(sorted(path.rglob("SKILL.md")))

    deduped = sorted({path.resolve() for path in skill_files})
    return deduped, issues


def load_frontmatter(path: Path) -> dict[str, str]:
    text = path.read_text(encoding="utf-8")
    normalized = text.replace("\r\n", "\n")
    lines = normalized.split("\n")

    if not lines or lines[0] != "---":
        raise FrontmatterError("missing starting YAML frontmatter delimiter '---'")

    try:
        closing_index = lines[1:].index("---") + 1
    except ValueError as exc:
        raise FrontmatterError("missing closing YAML frontmatter delimiter '---'") from exc

    frontmatter_lines = lines[1:closing_index]
    data: dict[str, str] = {}
    index = 0

    while index < len(frontmatter_lines):
        line = frontmatter_lines[index]
        line_number = index + 2

        if not line.strip():
            index += 1
            continue

        if line.startswith((" ", "\t")):
            raise FrontmatterError(
                f"invalid frontmatter syntax on line {line_number}: {line!r}"
            )

        match = FIELD_RE.match(line)
        if not match:
            raise FrontmatterError(
                f"invalid frontmatter syntax on line {line_number}: {line!r}"
            )

        key, raw_value = match.groups()
        if key in data:
            raise FrontmatterError(f"duplicate frontmatter field '{key}'")

        index += 1
        if raw_value.strip() in {"|", ">"}:
            data[key] = parse_block_value(frontmatter_lines, index)
            index = advance_past_indented_block(frontmatter_lines, index)
            continue

        continuation_lines: list[str] = []
        while index < len(frontmatter_lines):
            candidate = frontmatter_lines[index]
            if candidate and not candidate.startswith((" ", "\t")) and FIELD_RE.match(candidate):
                break
            continuation_lines.append(candidate)
            index += 1

        data[key] = build_scalar_value(raw_value, continuation_lines)

    return data


def unquote(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


def build_scalar_value(raw_value: str, continuation_lines: list[str]) -> str:
    parts: list[str] = []
    if raw_value.strip():
        parts.append(unquote(raw_value.strip()))

    for line in continuation_lines:
        if not line.strip():
            continue
        parts.append(line.lstrip())

    return "\n".join(parts).strip()


def parse_block_value(lines: list[str], start_index: int) -> str:
    parts: list[str] = []
    index = start_index
    while index < len(lines):
        candidate = lines[index]
        if candidate and not candidate.startswith((" ", "\t")) and FIELD_RE.match(candidate):
            break
        parts.append(candidate.lstrip())
        index += 1
    return "\n".join(part.rstrip() for part in parts).strip()


def advance_past_indented_block(lines: list[str], start_index: int) -> int:
    index = start_index
    while index < len(lines):
        candidate = lines[index]
        if candidate and not candidate.startswith((" ", "\t")) and FIELD_RE.match(candidate):
            break
        index += 1
    return index


def is_versioned_directory_name(directory_name: str) -> bool:
    return VERSION_SUFFIX_RE.fullmatch(directory_name) is not None


def strip_version_suffix(directory_name: str) -> str:
    match = VERSION_SUFFIX_RE.fullmatch(directory_name)
    return match.group("base") if match else directory_name


def normalize_skill_name(name: str) -> str:
    normalized = name.strip().lower().replace("_", "-").replace(" ", "-")
    normalized = re.sub(r"[^a-z0-9-]+", "-", normalized)
    normalized = re.sub(r"-+", "-", normalized).strip("-")
    return normalized


def validate_skill(path: Path) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []

    try:
        frontmatter = load_frontmatter(path)
    except (FrontmatterError, UnicodeDecodeError) as exc:
        return [ValidationIssue(path, str(exc))]

    required_fields = (
        BASE_REQUIRED_FIELDS
        if is_versioned_directory_name(path.parent.name)
        else NATIVE_REQUIRED_FIELDS
    )
    missing = [field for field in required_fields if not frontmatter.get(field)]
    for field in missing:
        issues.append(ValidationIssue(path, f"missing required field '{field}'"))

    name = frontmatter.get("name", "")
    if name:
        expected_name = strip_version_suffix(path.parent.name)
        normalized_name = normalize_skill_name(name)
        if normalized_name and normalized_name != expected_name:
            issues.append(
                ValidationIssue(
                    path,
                    f"name '{name}' does not match directory '{path.parent.name}'",
                )
            )

    if "allowed-tools" in frontmatter:
        issues.extend(validate_allowed_tools(path, frontmatter["allowed-tools"]))

    return issues


def validate_allowed_tools(path: Path, raw_value: str) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    tools = [token.strip() for token in re.split(r"[\n,]", raw_value) if token.strip()]

    seen: set[str] = set()
    for tool in tools:
        if tool in seen:
            issues.append(ValidationIssue(path, f"allowed-tools contains duplicate '{tool}'"))
            continue
        seen.add(tool)

        if tool in ALLOWED_SIMPLE_TOOLS:
            continue

        bash_match = BASH_RE.fullmatch(tool)
        if bash_match:
            command_pattern = bash_match.group(1).strip()
            if not command_pattern:
                issues.append(ValidationIssue(path, "Bash(...) must not be empty"))
            continue

        if tool.startswith("mcp__"):
            issues.extend(validate_mcp_tool(path, tool))
            continue

        if tool.startswith("mcp_"):
            issues.extend(validate_legacy_mcp_tool(path, tool))
            continue

        if "*" in tool:
            issues.append(
                ValidationIssue(
                    path,
                    f"tool '{tool}' is too broad; use a specific capability name",
                )
            )
            continue

        issues.append(ValidationIssue(path, f"unsupported tool declaration '{tool}'"))

    return issues


def validate_mcp_tool(path: Path, tool: str) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    match = MCP_RE.fullmatch(tool)
    if not match:
        return [ValidationIssue(path, f"invalid MCP tool declaration '{tool}'")]

    server_name, tool_name = match.groups()
    if "*" in server_name:
        issues.append(
            ValidationIssue(
                path,
                f"MCP server wildcard is not allowed in '{tool}'",
            )
        )

    if tool_name == "*":
        return issues

    if "*" in tool_name and not tool_name.endswith("*"):
        issues.append(
            ValidationIssue(
                path,
                f"MCP tool wildcard must only appear as a suffix in '{tool}'",
            )
        )

    return issues


def validate_legacy_mcp_tool(path: Path, tool: str) -> list[ValidationIssue]:
    if tool == "mcp_*":
        return [ValidationIssue(path, f"MCP tool wildcard is too broad in '{tool}'")]
    if not LEGACY_MCP_RE.fullmatch(tool):
        return [ValidationIssue(path, f"invalid MCP tool declaration '{tool}'")]
    return []


def run(paths: Sequence[str]) -> int:
    skill_files, preflight_issues = iter_skill_files(paths)
    issues = list(preflight_issues)

    for skill_file in skill_files:
        issues.extend(validate_skill(skill_file))

    if issues:
        for issue in issues:
            print(issue.render(), file=sys.stderr)
        print(
            f"Skill validation failed: {len(issues)} issue(s) across {len(skill_files)} file(s).",
            file=sys.stderr,
        )
        return 1

    print(f"Validated {len(skill_files)} skill file(s) successfully.")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    return run(args.paths)


if __name__ == "__main__":
    sys.exit(main())
