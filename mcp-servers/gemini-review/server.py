#!/usr/bin/env python3
"""Gemini review MCP server for Codex-first workflows.

This server mirrors the narrow review-only interface used by the existing
review bridges, but defaults to the direct Gemini API so Codex can reuse the
original ARIS review-heavy skill structure with minimal changes. Gemini CLI is
kept only as an optional fallback. It is intentionally self-contained so it can
be copied into `~/.codex/mcp-servers/gemini-review/` without depending on this
repository.
"""

from __future__ import annotations

import base64
import json
import mimetypes
import os
import re
import signal
import shutil
import stat
import subprocess
import sys
import tempfile
import time
import traceback
import urllib.error
import urllib.parse
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


_stdio_initialized = False


def _init_stdio() -> None:
    """Rebind stdio to raw unbuffered binary streams for MCP framing.

    Deferred into a function (called at the top of main()) so that merely
    IMPORTING this module has no stdio side effects. os.fdopen(fileno) defaults
    to closefd=True and thus seizes ownership of the fd; doing that at import
    time under a test harness that captures stdio (pytest fd-capture) closes the
    harness's capture fd and corrupts capture for every subsequent test. Real
    server launch (python server.py) still calls this first via main(), so
    runtime behavior is unchanged. Idempotent."""
    global _stdio_initialized
    if _stdio_initialized:
        return
    sys.stdout = os.fdopen(sys.stdout.fileno(), "wb", buffering=0)
    sys.stdin = os.fdopen(sys.stdin.fileno(), "rb", buffering=0)
    _stdio_initialized = True


SERVER_NAME = os.environ.get("GEMINI_REVIEW_SERVER_NAME", "gemini-review")
GEMINI_BIN = os.environ.get("GEMINI_BIN", "gemini")
AGY_BIN = os.environ.get("AGY_BIN", "agy")
DEFAULT_MODEL = os.environ.get("GEMINI_REVIEW_MODEL", "")
DEFAULT_SYSTEM = os.environ.get("GEMINI_REVIEW_SYSTEM", "")
DEFAULT_BACKEND = os.environ.get("GEMINI_REVIEW_BACKEND", "api")
DEFAULT_TIMEOUT_SEC = int(os.environ.get("GEMINI_REVIEW_TIMEOUT_SEC", "600"))
DEFAULT_API_MODEL = os.environ.get("GEMINI_REVIEW_API_MODEL", "gemini-2.5-flash")
DEFAULT_AGY_PRINT_TIMEOUT = os.environ.get("GEMINI_REVIEW_AGY_PRINT_TIMEOUT", f"{DEFAULT_TIMEOUT_SEC}s")
MAX_STATUS_WAIT_SECONDS = int(os.environ.get("GEMINI_REVIEW_MAX_STATUS_WAIT_SECONDS", "30"))
AGY_APP_DATA_DIR = Path(
    os.environ.get(
        "GEMINI_REVIEW_AGY_APP_DATA_DIR",
        str(Path.home() / ".gemini" / "antigravity-cli"),
    )
).expanduser()
AGY_ARTIFACT_MAX_CHARS = int(os.environ.get("GEMINI_REVIEW_AGY_ARTIFACT_MAX_CHARS", "200000"))
WORKSPACE_ROOT = Path(os.environ.get("GEMINI_REVIEW_WORKSPACE_ROOT", os.getcwd())).expanduser()
STATE_DIR = Path(
    os.environ.get(
        "GEMINI_REVIEW_STATE_DIR",
        str(Path.home() / ".codex" / "state" / SERVER_NAME),
    )
).expanduser()
DEBUG_LOG = Path(os.environ.get("GEMINI_REVIEW_DEBUG_LOG", str(STATE_DIR / "debug.log"))).expanduser()
JOBS_DIR = STATE_DIR / "jobs"
THREADS_DIR = STATE_DIR / "threads"

_use_ndjson = False
TERMINAL_JOB_STATES = {"completed", "failed"}
SHARED_TEMP_DIRS = {Path("/tmp"), Path("/var/tmp")}
SAFE_ID_MAX_LEN = 128
SAFE_ID_RE = re.compile(r"^[0-9A-Za-z_-]+$")
GEMINI_MODEL_RE = re.compile(
    r"^(?:gemini-[A-Za-z0-9][A-Za-z0-9_.:+-]*|models/gemini-[A-Za-z0-9][A-Za-z0-9_.:+-]*|publishers/google/models/gemini-[A-Za-z0-9][A-Za-z0-9_.:+-]*)$",
    re.IGNORECASE,
)
GEMINI_LABEL_RE = re.compile(
    r"^Gemini\s+[0-9][A-Za-z0-9 ._-]*(?:\s+\([A-Za-z0-9 ._-]+\))?$",
    re.IGNORECASE,
)
MODEL_KEY_RE = re.compile(r"[^a-z0-9]+")
MODEL_KEY_NAMES = {
    "model",
    "modelid",
    "modelname",
    "selectedmodel",
    "currentmodel",
    "reviewermodel",
}
PRIVATE_ENV_KEYS = {"GEMINI_API_KEY", "GOOGLE_API_KEY"}
DEBUG_REDACT_KEYS = {"prompt", "system", "content", "text", "history", "imagePaths", "image_paths"}
MODEL_UNTRUSTED_CONTAINER_KEYS = {
    "content",
    "contents",
    "history",
    "message",
    "messages",
    "parts",
    "prompt",
    "response",
    "result",
    "stderr",
    "stdout",
    "text",
    "transcript",
}
AGY_CONVERSATION_RE = re.compile(
    r"(?m)^[IWEF]\d{4}\s+\S+\s+\d+\s+printmode\.go:\d+\] "
    r"Print mode: conversation=([0-9A-Za-z_-]+), sending message$"
)
AGY_MODEL_LABEL_RE = re.compile(
    r'(?m)^[IWEF]\d{4}\s+\S+\s+\d+\s+model_config_manager\.go:\d+\] '
    r'Propagating selected model override to backend: label="([^"]+)"$'
)


def debug_log(message: str) -> None:
    try:
        state_root = resolve_path(STATE_DIR)
        debug_path = resolve_path(DEBUG_LOG)
        if not path_is_relative_to(debug_path, state_root):
            return
        ensure_private_dir(debug_path.parent)
        append_private_text(debug_path, f"{message}\n")
    except OSError:
        pass


def append_private_text(path: Path, text: str) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_APPEND
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(path, flags, 0o600)
    try:
        os.write(fd, text.encode("utf-8"))
        try:
            os.fchmod(fd, 0o600)
        except (OSError, AttributeError):
            pass
    finally:
        os.close(fd)


def redact_for_debug(value: Any) -> Any:
    if isinstance(value, dict):
        redacted: dict[str, Any] = {}
        for key, item in value.items():
            if str(key) in DEBUG_REDACT_KEYS:
                redacted[str(key)] = "[redacted]"
            else:
                redacted[str(key)] = redact_for_debug(item)
        return redacted
    if isinstance(value, list):
        return [redact_for_debug(item) for item in value]
    return value


def send_response(response: dict[str, Any]) -> None:
    global _use_ndjson

    payload = json.dumps(response, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    debug_log(f"SEND id={response.get('id')!r} has_error={bool(response.get('error') or response.get('result', {}).get('isError'))}")
    if _use_ndjson:
        sys.stdout.write(payload + b"\n")
    else:
        header = f"Content-Length: {len(payload)}\r\n\r\n".encode("utf-8")
        sys.stdout.write(header + payload)
    sys.stdout.flush()


def read_message() -> dict[str, Any] | None:
    global _use_ndjson

    line = sys.stdin.readline()
    if not line:
        return None

    line_text = line.decode("utf-8").rstrip("\r\n")
    if line_text.lower().startswith("content-length:"):
        try:
            content_length = int(line_text.split(":", 1)[1].strip())
        except ValueError:
            return None

        while True:
            header_line = sys.stdin.readline()
            if not header_line:
                return None
            if header_line in {b"\r\n", b"\n"}:
                break

        body = sys.stdin.read(content_length)
        try:
            return json.loads(body.decode("utf-8"))
        except json.JSONDecodeError:
            return None

    if line_text.startswith("{") or line_text.startswith("["):
        _use_ndjson = True
        try:
            return json.loads(line_text)
        except json.JSONDecodeError:
            return None

    return None


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def path_is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def resolve_path(path: Path) -> Path:
    return path.expanduser().resolve(strict=False)


def ensure_private_dir(path: Path) -> None:
    resolved = resolve_path(path)
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    if resolved in SHARED_TEMP_DIRS or resolved == resolved.parent:
        return
    try:
        os.chmod(path, 0o700)
    except OSError:
        pass


def normalize_safe_id(raw_value: Any, field_name: str) -> tuple[str | None, str | None]:
    value = str(raw_value or "").strip()
    if not value:
        return None, f"{field_name} is required"
    if len(value) > SAFE_ID_MAX_LEN:
        return None, f"{field_name} must be at most {SAFE_ID_MAX_LEN} characters"
    if not SAFE_ID_RE.fullmatch(value):
        return None, f"{field_name} must match ^[0-9A-Za-z_-]+$"
    return value, None


def confined_state_file(base_dir: Path, identifier: str, field_name: str) -> Path:
    safe_id, error = normalize_safe_id(identifier, field_name)
    if error or safe_id is None:
        raise ValueError(error or f"invalid {field_name}")

    base = resolve_path(base_dir)
    path = resolve_path(base / f"{safe_id}.json")
    if not path_is_relative_to(path, base):
        raise ValueError(f"{field_name} escapes the state directory")
    return path


def open_confined_read_fd(path: Path, root: Path) -> int | None:
    resolved_root = resolve_path(root)
    resolved_path = resolve_path(path)
    if not path_is_relative_to(resolved_path, resolved_root):
        return None
    flags = os.O_RDONLY
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        fd = os.open(resolved_path, flags)
    except OSError:
        return None
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            os.close(fd)
            return None
        fd_path = resolved_fd_path(fd)
        if fd_path is None or not path_is_relative_to(fd_path, resolved_root):
            os.close(fd)
            return None
        return fd
    except OSError:
        os.close(fd)
        return None


def resolved_fd_path(fd: int) -> Path | None:
    for fd_root in (Path("/proc/self/fd"), Path("/dev/fd")):
        fd_link = fd_root / str(fd)
        if fd_link.exists():
            try:
                return resolve_path(Path(os.readlink(fd_link)))
            except OSError:
                return None
    try:
        import fcntl  # type: ignore[import-not-found]
    except ImportError:
        return None
    f_getpath = getattr(fcntl, "F_GETPATH", None)
    if f_getpath is None:
        return None
    try:
        raw_path = fcntl.fcntl(fd, f_getpath, b"\0" * 4096)
    except OSError:
        return None
    if isinstance(raw_path, bytes):
        path_text = raw_path.split(b"\0", 1)[0].decode("utf-8", errors="replace")
    else:
        path_text = str(raw_path).split("\0", 1)[0]
    return resolve_path(Path(path_text)) if path_text else None


def read_text_confined(path: Path, root: Path) -> str | None:
    result = read_text_confined_with_stat(path, root)
    return result[0] if result is not None else None


def read_text_confined_with_stat(path: Path, root: Path) -> tuple[str, os.stat_result] | None:
    fd = open_confined_read_fd(path, root)
    if fd is None:
        return None
    with os.fdopen(fd, "r", encoding="utf-8", errors="replace") as fh:
        file_stat = os.fstat(fh.fileno())
        return fh.read(), file_stat


def read_bytes_confined(path: Path, root: Path) -> bytes | None:
    fd = open_confined_read_fd(path, root)
    if fd is None:
        return None
    with os.fdopen(fd, "rb") as fh:
        return fh.read()


def normalize_model_name(raw_value: Any, field_name: str = "model") -> tuple[str | None, str | None]:
    if raw_value is None:
        return None, None
    value = str(raw_value).strip()
    if not value:
        return None, None
    if "\x00" in value:
        return None, f"{field_name} must not contain NUL bytes"
    if value.startswith("-"):
        return None, f"{field_name} must not start with '-'"
    return value, None


def ensure_no_nul(value: str, field_name: str) -> str | None:
    if "\x00" in value:
        return f"{field_name} must not contain NUL bytes"
    return None


def select_model_name(*values: Any) -> tuple[str | None, str | None]:
    for value in values:
        selected, error = normalize_model_name(value)
        if error:
            return None, error
        if selected:
            return selected, None
    return None, None


def is_gemini_model_name(model_name: str | None) -> bool:
    if not model_name:
        return False
    normalized = model_name.strip()
    return bool(GEMINI_MODEL_RE.fullmatch(normalized) or GEMINI_LABEL_RE.fullmatch(normalized))


def require_gemini_model(model_name: str | None, backend_name: str) -> str | None:
    if not is_gemini_model_name(model_name):
        shown = model_name or "unknown"
        return f"{backend_name} reviewer model must be a Gemini family model, got: {shown}"
    return None


def gemini_api_model_path(model_name: str) -> str:
    if model_name.startswith(("models/", "publishers/")):
        return model_name
    return f"models/{model_name}"


def write_json(path: Path, payload: dict[str, Any]) -> None:
    ensure_private_dir(path.parent)
    temp_path = path.with_suffix(path.suffix + ".tmp")
    temp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    try:
        os.chmod(temp_path, 0o600)
    except OSError:
        pass
    temp_path.replace(path)


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_private_env_file(env_file: Path | None = None) -> list[str]:
    target = env_file or (Path.home() / ".gemini" / ".env")
    lines = read_private_env_lines(target)
    if lines is None:
        return []

    loaded: list[str] = []
    for raw_line in lines:
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].strip()
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if key not in PRIVATE_ENV_KEYS:
            continue
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]
        if key not in os.environ:
            os.environ[key] = value
            loaded.append(key)
    return loaded


def read_private_env_lines(path: Path) -> list[str] | None:
    target = path.expanduser()
    flags = os.O_RDONLY
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        stat_before = os.lstat(target)
        if stat.S_ISLNK(stat_before.st_mode) or not stat.S_ISREG(stat_before.st_mode):
            return None
        if stat_before.st_mode & 0o022:
            return None
        if hasattr(os, "getuid") and stat_before.st_uid != os.getuid():
            return None
        fd = os.open(target, flags)
    except OSError:
        return None
    try:
        stat_after = os.fstat(fd)
        if not stat.S_ISREG(stat_after.st_mode) or stat_after.st_mode & 0o022:
            return None
        if hasattr(os, "getuid") and stat_after.st_uid != os.getuid():
            return None
        if (stat_before.st_dev, stat_before.st_ino) != (stat_after.st_dev, stat_after.st_ino):
            return None
        with os.fdopen(fd, "r", encoding="utf-8", errors="replace") as fh:
            fd = -1
            return fh.read().splitlines()
    finally:
        if fd >= 0:
            os.close(fd)


def normalize_image_paths(raw_value: Any) -> tuple[list[str], str | None]:
    if raw_value is None:
        return [], None
    if isinstance(raw_value, str):
        candidate = raw_value.strip()
        return ([candidate] if candidate else []), None
    if not isinstance(raw_value, list):
        return [], "imagePaths must be a string or an array of strings"

    image_paths: list[str] = []
    for item in raw_value:
        if not isinstance(item, str):
            return [], "imagePaths entries must be strings"
        candidate = item.strip()
        if candidate:
            image_paths.append(candidate)
    return image_paths, None


def build_inline_image_parts(image_paths: list[str]) -> tuple[list[dict[str, Any]], str | None]:
    parts: list[dict[str, Any]] = []
    workspace_root = resolve_path(WORKSPACE_ROOT)
    for raw_path in image_paths:
        path = Path(raw_path).expanduser()
        if not path.is_absolute():
            path = workspace_root / path
        resolved_path = resolve_path(path)
        if not path_is_relative_to(resolved_path, workspace_root):
            return [], f"image file must stay under workspace root: {raw_path}"
        mime_type, _ = mimetypes.guess_type(resolved_path.name)
        if not mime_type or not mime_type.startswith("image/"):
            return [], f"unsupported image type for Gemini review: {raw_path}"
        data = read_bytes_confined(resolved_path, workspace_root)
        if data is None:
            return [], f"image file not found or not confined to workspace root: {raw_path}"
        encoded = base64.b64encode(data).decode("ascii")
        parts.append({"inlineData": {"mimeType": mime_type, "data": encoded}})
    return parts, None


def find_gemini_bin() -> str | None:
    if Path(GEMINI_BIN).is_file():
        return GEMINI_BIN
    return shutil.which(GEMINI_BIN)


def find_agy_bin() -> str | None:
    if Path(AGY_BIN).is_file():
        return AGY_BIN
    return shutil.which(AGY_BIN)


def resolve_backend(preferred_backend: str | None) -> str:
    backend = preferred_backend or DEFAULT_BACKEND
    if backend not in {"auto", "api", "cli", "agy"}:
        raise ValueError(f"unsupported Gemini backend: {backend}")
    if backend == "auto":
        return "api" if get_api_key() else "cli"
    return backend


def get_api_key() -> str | None:
    return os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")


def parse_gemini_json(raw_stdout: str) -> tuple[dict[str, Any] | None, str | None]:
    lines = [line.strip() for line in raw_stdout.splitlines() if line.strip()]
    if not lines:
        return None, "Gemini CLI returned empty output"

    for candidate in reversed(lines):
        try:
            payload = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            return payload, None

    return None, "Gemini CLI did not return JSON output"


def extract_cli_error_message(raw_stdout: str, raw_stderr: str) -> str:
    for text in (raw_stdout, raw_stderr):
        stripped = text.strip()
        if not stripped:
            continue
        try:
            payload = json.loads(stripped)
        except json.JSONDecodeError:
            return stripped
        if not isinstance(payload, dict):
            return stripped
        error = payload.get("error")
        if isinstance(error, dict):
            message = error.get("message")
            if isinstance(message, str) and message.strip():
                return message.strip()
        response = payload.get("response")
        if isinstance(response, str) and response.strip():
            return response.strip()
        return stripped
    return "unknown error"


def agy_output_is_error(text: str) -> bool:
    stripped = text.strip()
    return stripped == "Error: timed out waiting for response" or stripped.startswith("Error: timed out waiting for response")


def extract_agy_conversation_id_from_log(log_path: Path) -> str | None:
    conversation_ids = extract_agy_conversation_ids_from_log(log_path)
    return conversation_ids[-1] if conversation_ids else None


def extract_agy_conversation_ids_from_log(log_path: Path) -> list[str]:
    try:
        text = log_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    matches = [match.group(1) for match in AGY_CONVERSATION_RE.finditer(text)]
    conversation_ids: list[str] = []
    for match in matches:
        conversation_id, error = normalize_safe_id(match, "conversationId")
        if not error and conversation_id and conversation_id not in conversation_ids:
            conversation_ids.append(conversation_id)
    return conversation_ids


def agy_conversation_position(log_text: str, conversation_id: str) -> int | None:
    position: int | None = None
    for match in AGY_CONVERSATION_RE.finditer(log_text):
        if match.group(1) == conversation_id:
            position = match.start()
    return position


def agy_conversation_root(conversation_id: str) -> Path | None:
    safe_id, error = normalize_safe_id(conversation_id, "conversationId")
    if error or safe_id is None:
        return None
    brain_root = resolve_path(AGY_APP_DATA_DIR / "brain")
    conversation_root = resolve_path(brain_root / safe_id)
    if not path_is_relative_to(conversation_root, brain_root):
        return None
    return conversation_root


def agy_transcript_paths(conversation_id: str) -> list[Path]:
    conversation_root = agy_conversation_root(conversation_id)
    if conversation_root is None:
        return []
    logs_dir = conversation_root / ".system_generated" / "logs"
    return [logs_dir / "transcript_full.jsonl", logs_dir / "transcript.jsonl"]


def agy_artifact_text(
    path: Path,
    *,
    conversation_root: Path,
    artifact_min_mtime: float | None = None,
) -> str | None:
    if path.suffix.lower() not in {".md", ".markdown", ".txt", ".json", ".yaml", ".yml"}:
        return None
    result = read_text_confined_with_stat(path, conversation_root)
    if result is None:
        return None
    text, file_stat = result
    if artifact_min_mtime is not None and file_stat.st_mtime < artifact_min_mtime - 1.0:
        return None
    text = text.strip()
    if not text:
        return None
    if len(text) > AGY_ARTIFACT_MAX_CHARS:
        return text[:AGY_ARTIFACT_MAX_CHARS] + "\n\n[truncated by gemini-review agy artifact fallback]"
    return text


def extract_file_uri_paths(text: str) -> list[Path]:
    paths: list[Path] = []
    for match in re.finditer(r"file://[^\s)>\]]+", text):
        parsed = urllib.parse.urlparse(match.group(0))
        if parsed.scheme != "file" or not parsed.path:
            continue
        paths.append(Path(urllib.parse.unquote(parsed.path)))
    return paths


def strip_file_uri_refs(text: str) -> str:
    return re.sub(r"file://[^\s)>\]]+", "", text).strip(" \t\r\n.,:;()[]<>")


def collect_model_candidates(value: Any, candidates: list[str], *, under_untrusted_text: bool = False) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            normalized_key = MODEL_KEY_RE.sub("", str(key).lower())
            next_under_untrusted = under_untrusted_text or normalized_key in MODEL_UNTRUSTED_CONTAINER_KEYS
            if (
                not under_untrusted_text
                and normalized_key in MODEL_KEY_NAMES
                and isinstance(item, str)
                and item.strip()
            ):
                candidates.append(item.strip())
            collect_model_candidates(item, candidates, under_untrusted_text=next_under_untrusted)
    elif isinstance(value, list):
        for item in value:
            collect_model_candidates(item, candidates, under_untrusted_text=under_untrusted_text)


def select_model_candidate(candidates: list[str]) -> tuple[str | None, str | None]:
    cleaned = [candidate.strip().strip('",') for candidate in candidates if candidate.strip()]
    if not cleaned:
        return None, None
    normalized = {candidate.lower() for candidate in cleaned}
    if len(normalized) > 1:
        return None, f"conflicting Antigravity model candidates: {', '.join(cleaned)}"
    return cleaned[-1], None


def collect_model_candidates_from_agy_log(text: str, candidates: list[str]) -> None:
    matches = [match.group(1) for match in AGY_MODEL_LABEL_RE.finditer(text)]
    candidates.extend(match.strip() for match in matches if match.strip())


def transcript_step_is_user_event(step: dict[str, Any]) -> bool:
    source = str(step.get("source", "")).upper()
    role = str(step.get("role", "")).lower()
    step_type = str(step.get("type", "")).upper()
    author = str(step.get("author", "")).lower()
    return (
        source in {"USER", "USER_EXPLICIT", "USER_IMPLICIT"}
        or role == "user"
        or author == "user"
        or step_type in {"USER_INPUT", "USER_MESSAGE"}
    )


def transcript_step_contains_nonce(step: dict[str, Any], invocation_nonce: str) -> bool:
    content = step.get("content")
    if isinstance(content, str):
        return invocation_nonce in content
    if isinstance(content, list):
        return any(isinstance(item, str) and invocation_nonce in item for item in content)
    if isinstance(content, dict):
        return invocation_nonce in json.dumps(content, ensure_ascii=False)
    return False


def transcript_lines_at_or_after_nonce(transcript_text: str, invocation_nonce: str | None) -> list[str] | None:
    if not invocation_nonce:
        return None
    lines = transcript_text.splitlines()
    for index, line in enumerate(lines):
        try:
            step = json.loads(line)
        except json.JSONDecodeError:
            continue
        if (
            isinstance(step, dict)
            and transcript_step_is_user_event(step)
            and transcript_step_contains_nonce(step, invocation_nonce)
        ):
            return lines[index:]
    return None


def transcript_contains_nonce(transcript_text: str, invocation_nonce: str) -> bool:
    return transcript_lines_at_or_after_nonce(transcript_text, invocation_nonce) is not None


def agy_conversation_has_nonce(conversation_id: str, invocation_nonce: str) -> bool:
    conversation_root = agy_conversation_root(conversation_id)
    if conversation_root is None:
        return False
    for transcript_path in agy_transcript_paths(conversation_id):
        transcript_text = read_text_confined(transcript_path, conversation_root)
        if transcript_text is not None and transcript_contains_nonce(transcript_text, invocation_nonce):
            return True
    return False


def select_agy_conversation_id_from_state(
    log_path: Path,
    *,
    invocation_nonce: str | None = None,
) -> tuple[str | None, str | None]:
    if not invocation_nonce:
        return None, "invocation_nonce is required for Antigravity transcript recovery"
    conversation_ids = extract_agy_conversation_ids_from_log(log_path)
    if not conversation_ids:
        return None, "could not locate Antigravity conversation id in this invocation's log"
    for conversation_id in reversed(conversation_ids):
        if agy_conversation_has_nonce(conversation_id, invocation_nonce):
            return conversation_id, None
    return None, f"Antigravity transcript is not bound to this invocation: {conversation_ids[-1]}"


def extract_agy_model_from_state(
    log_path: Path,
    *,
    conversation_id: str,
    invocation_nonce: str | None = None,
) -> tuple[str | None, str | None]:
    if not invocation_nonce:
        return None, "invocation_nonce is required for Antigravity model provenance"
    candidates: list[str] = []
    try:
        log_text = log_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        log_text = ""
    conversation_position = agy_conversation_position(log_text, conversation_id)
    if conversation_position is not None:
        collect_model_candidates_from_agy_log(log_text[:conversation_position], candidates)

    conversation_root = agy_conversation_root(conversation_id)
    if conversation_root is not None:
        for transcript_path in agy_transcript_paths(conversation_id):
            transcript_text = read_text_confined(transcript_path, conversation_root)
            if transcript_text is None:
                continue
            scoped_lines = transcript_lines_at_or_after_nonce(transcript_text, invocation_nonce)
            if scoped_lines is None:
                continue
            for line in scoped_lines:
                try:
                    step = json.loads(line)
                except json.JSONDecodeError:
                    continue
                collect_model_candidates(step, candidates)

    return select_model_candidate(candidates)


def extract_agy_response_from_transcript(
    conversation_id: str,
    *,
    invocation_nonce: str | None = None,
    artifact_min_mtime: float | None = None,
) -> str | None:
    if not invocation_nonce:
        return None
    conversation_root = agy_conversation_root(conversation_id)
    if conversation_root is None:
        return None
    for transcript_path in agy_transcript_paths(conversation_id):
        transcript_text = read_text_confined(transcript_path, conversation_root)
        if transcript_text is None:
            continue
        scoped_lines = transcript_lines_at_or_after_nonce(transcript_text, invocation_nonce)
        if scoped_lines is None:
            continue
        final_response: str | None = None
        artifact_paths: list[Path] = []
        for line in scoped_lines:
            try:
                step = json.loads(line)
            except json.JSONDecodeError:
                continue
            if step.get("source") != "MODEL":
                continue
            step_type = step.get("type")
            content = step.get("content")
            if step_type == "PLANNER_RESPONSE" and isinstance(content, str) and content.strip():
                final_response = content.strip()
                artifact_paths = extract_file_uri_paths(content)

        if final_response:
            if strip_file_uri_refs(final_response):
                return final_response
            for path in reversed(artifact_paths):
                artifact = agy_artifact_text(
                    path,
                    conversation_root=conversation_root,
                    artifact_min_mtime=artifact_min_mtime,
                )
                if artifact:
                    return artifact
            return None
    return None


def extract_agy_response_from_state(
    log_path: Path,
    *,
    invocation_nonce: str | None = None,
    artifact_min_mtime: float | None = None,
) -> tuple[str | None, str | None, str | None]:
    if not invocation_nonce:
        return None, "invocation_nonce is required for Antigravity transcript recovery", None
    conversation_id, conversation_error = select_agy_conversation_id_from_state(
        log_path,
        invocation_nonce=invocation_nonce,
    )
    if conversation_error or conversation_id is None:
        return None, conversation_error or "could not locate Antigravity conversation id", None
    response = extract_agy_response_from_transcript(
        conversation_id,
        invocation_nonce=invocation_nonce,
        artifact_min_mtime=artifact_min_mtime,
    )
    if response:
        debug_log(f"AGY_TRANSCRIPT_RECOVERED conversation={conversation_id}")
        return response, None, conversation_id
    return None, f"Antigravity transcript has no final response yet: {conversation_id}", None


def extract_api_response_text(payload: dict[str, Any]) -> str:
    candidates = payload.get("candidates")
    if isinstance(candidates, list):
        for candidate in candidates:
            if not isinstance(candidate, dict):
                continue
            content = candidate.get("content")
            if not isinstance(content, dict):
                continue
            parts = content.get("parts")
            if not isinstance(parts, list):
                continue
            texts: list[str] = []
            for part in parts:
                if isinstance(part, dict):
                    text = part.get("text")
                    if isinstance(text, str):
                        texts.append(text)
            if texts:
                return "\n".join(texts).strip()

    prompt_feedback = payload.get("promptFeedback")
    if isinstance(prompt_feedback, dict):
        block_reason = prompt_feedback.get("blockReason")
        if isinstance(block_reason, str) and block_reason:
            raise ValueError(f"Gemini API response blocked: {block_reason}")

    raise ValueError("Gemini API response does not contain candidate text")


def job_state_path(job_id: str) -> Path:
    return confined_state_file(JOBS_DIR, job_id, "jobId")


def thread_state_path(thread_id: str) -> Path:
    return confined_state_file(THREADS_DIR, thread_id, "threadId")


def is_pid_alive(pid: int | None) -> bool:
    if not pid or pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def kill_process_tree(process: subprocess.Popen[str]) -> None:
    try:
        if os.name == "nt":
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(process.pid)],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=5,
                check=False,
            )
            if process.poll() is None:
                process.kill()
        else:
            os.killpg(process.pid, signal.SIGKILL)
    except OSError:
        try:
            process.kill()
        except OSError:
            pass


def run_process_tree(
    cmd: list[str],
    *,
    timeout_sec: int,
) -> tuple[subprocess.CompletedProcess[str] | None, str | None, int]:
    started = time.monotonic()
    popen_kwargs: dict[str, Any] = {
        "stdout": subprocess.PIPE,
        "stderr": subprocess.PIPE,
        "text": True,
        "stdin": subprocess.DEVNULL,
        "close_fds": True,
    }
    if os.name == "nt":
        popen_kwargs["creationflags"] = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    else:
        popen_kwargs["start_new_session"] = True

    process = subprocess.Popen(cmd, **popen_kwargs)
    try:
        stdout, stderr = process.communicate(timeout=timeout_sec)
    except subprocess.TimeoutExpired:
        kill_process_tree(process)
        try:
            stdout, stderr = process.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            return None, f"process tree did not exit after timeout ({timeout_sec} seconds)", int(
                (time.monotonic() - started) * 1000
            )
        return None, f"timed out after {timeout_sec} seconds", int((time.monotonic() - started) * 1000)

    return subprocess.CompletedProcess(cmd, process.returncode, stdout, stderr), None, int(
        (time.monotonic() - started) * 1000
    )


def serialize_job(job: dict[str, Any]) -> dict[str, Any]:
    result = job.get("result") or {}
    payload = {
        "jobId": job.get("jobId"),
        "status": job.get("status"),
        "done": job.get("status") in TERMINAL_JOB_STATES,
        "threadId": result.get("threadId"),
        "response": result.get("response"),
        "model": result.get("model"),
        "backend": result.get("backend"),
        "duration_ms": result.get("duration_ms"),
        "stop_reason": result.get("stop_reason"),
        "error": job.get("error"),
        "createdAt": job.get("createdAt"),
        "startedAt": job.get("startedAt"),
        "completedAt": job.get("completedAt"),
        "updatedAt": job.get("updatedAt"),
        "resumeHint": "Call review_status with this jobId until done=true.",
    }
    for optional_key in ("model_provenance", "requested_model", "warning"):
        if optional_key in result:
            payload[optional_key] = result.get(optional_key)
    return payload


def load_thread_history(thread_id: str) -> list[dict[str, str]]:
    path = thread_state_path(thread_id)
    if not path.exists():
        return []
    payload = read_json(path)
    history = payload.get("history")
    if not isinstance(history, list):
        return []
    result: list[dict[str, str]] = []
    for item in history:
        if not isinstance(item, dict):
            continue
        role = str(item.get("role", "")).strip()
        text = str(item.get("text", "")).strip()
        if role in {"user", "model"} and text:
            result.append({"role": role, "text": text})
    return result


def save_thread_history(
    *,
    thread_id: str,
    history: list[dict[str, str]],
    model: str,
    backend: str,
) -> None:
    now = utc_now()
    path = thread_state_path(thread_id)
    created_at = now
    if path.exists():
        existing = read_json(path)
        created_at = str(existing.get("createdAt") or now)
    write_json(
        path,
        {
            "threadId": thread_id,
            "createdAt": created_at,
            "updatedAt": now,
            "model": model,
            "backend": backend,
            "history": history,
        },
    )


def build_cli_prompt(
    prompt: str,
    *,
    history: list[dict[str, str]],
    system: str | None,
) -> str:
    selected_system = (system or DEFAULT_SYSTEM).strip()
    if not history and not selected_system:
        return prompt

    sections: list[str] = []
    if selected_system:
        sections.extend(["## System Instructions", selected_system, ""])
    if history:
        sections.append("## Previous Review Conversation")
        for item in history:
            role = "User" if item["role"] == "user" else "Reviewer"
            sections.append(f"### {role}")
            sections.append(item["text"])
            sections.append("")
    sections.extend(["## New User Prompt", prompt])
    return "\n".join(sections).strip()


def run_gemini_cli_review(
    prompt: str,
    *,
    history: list[dict[str, str]],
    model: str | None,
    system: str | None,
    image_paths: list[str],
) -> tuple[dict[str, Any] | None, str | None]:
    if image_paths:
        return None, "Gemini CLI backend in this bridge does not support imagePaths; use backend=api"

    bin_path = find_gemini_bin()
    if not bin_path:
        return None, f"Gemini CLI not found: {GEMINI_BIN}"

    effective_prompt = build_cli_prompt(prompt, history=history, system=system)
    nul_error = ensure_no_nul(effective_prompt, "prompt")
    if nul_error:
        return None, nul_error
    cmd = [bin_path, "-p", effective_prompt, "--output-format", "json"]
    selected_model, model_error = select_model_name(model, DEFAULT_MODEL)
    if model_error:
        return None, model_error
    if selected_model:
        model_family_error = require_gemini_model(selected_model, "Gemini CLI")
        if model_family_error:
            return None, model_family_error
        cmd.extend(["-m", selected_model])

    debug_log(f"RUN gemini-cli model={selected_model or 'default'} output_format=json")
    try:
        result, process_error, duration_ms = run_process_tree(
            cmd,
            timeout_sec=DEFAULT_TIMEOUT_SEC,
        )
    except (OSError, ValueError) as exc:
        return None, f"failed to launch Gemini CLI: {exc}"
    if process_error:
        return None, f"Gemini review {process_error}"
    if result is None:
        return None, "Gemini review failed without process details"

    payload, parse_error = parse_gemini_json(result.stdout)
    if parse_error:
        stderr = result.stderr.strip()
        message = parse_error if not stderr else f"{parse_error}. stderr: {stderr}"
        return None, message

    if payload is None:
        return None, "Failed to parse Gemini CLI output"
    if result.returncode != 0:
        return None, f"Gemini review failed: {extract_cli_error_message(result.stdout, result.stderr)}"

    response_text = str(payload.get("response", "")).strip()
    if not response_text:
        return None, "Gemini CLI JSON payload does not contain a non-empty response field"

    reported_model = str(payload.get("model", "") or selected_model or "gemini-cli")
    model_family_error = require_gemini_model(reported_model, "Gemini CLI")
    if model_family_error:
        return None, model_family_error

    return {
        "response": response_text,
        "model": reported_model,
        "duration_ms": duration_ms,
        "stop_reason": payload.get("stop_reason"),
        "backend": "cli",
    }, None


def run_agy_cli_review(
    prompt: str,
    *,
    history: list[dict[str, str]],
    model: str | None,
    system: str | None,
    image_paths: list[str],
) -> tuple[dict[str, Any] | None, str | None]:
    if image_paths:
        return None, "Antigravity CLI backend in this bridge does not support imagePaths; use backend=api"

    bin_path = find_agy_bin()
    if not bin_path:
        return None, f"Antigravity CLI not found: {AGY_BIN}"
    requested_model, model_error = select_model_name(model)
    if model_error:
        return None, model_error

    invocation_nonce = uuid.uuid4().hex
    effective_prompt = build_cli_prompt(prompt, history=history, system=system)
    effective_prompt = (
        f"{effective_prompt}\n\n"
        f"## Invocation Binding\n"
        f"gemini-review nonce: {invocation_nonce}"
    )
    nul_error = ensure_no_nul(effective_prompt, "prompt") or ensure_no_nul(DEFAULT_AGY_PRINT_TIMEOUT, "GEMINI_REVIEW_AGY_PRINT_TIMEOUT")
    if nul_error:
        return None, nul_error
    agy_log_dir = STATE_DIR / "agy-logs"
    try:
        ensure_private_dir(agy_log_dir)
    except OSError as exc:
        return None, f"failed to create private Antigravity log directory: {exc}"

    with tempfile.TemporaryDirectory(prefix="agy-", dir=str(agy_log_dir)) as temp_dir:
        temp_path = Path(temp_dir)
        try:
            os.chmod(temp_path, 0o700)
        except OSError:
            pass
        agy_log_path = temp_path / "agy.log"
        cmd = [
            bin_path,
            "--log-file",
            str(agy_log_path),
            "--print",
            effective_prompt,
            "--print-timeout",
            DEFAULT_AGY_PRINT_TIMEOUT,
        ]

        debug_log(f"RUN agy-cli timeout={DEFAULT_AGY_PRINT_TIMEOUT} log={agy_log_path}")
        try:
            invocation_started_at = time.time()
            result, process_error, duration_ms = run_process_tree(
                cmd,
                timeout_sec=DEFAULT_TIMEOUT_SEC + 15,
            )
        except (OSError, ValueError) as exc:
            return None, f"failed to launch Antigravity CLI: {exc}"
        if process_error:
            return None, f"Antigravity review {process_error}"
        if result is None:
            return None, "Antigravity review failed without process details"

        response_text = result.stdout.strip()
        recovered_conversation_id: str | None = None
        if result.returncode != 0:
            message = result.stderr.strip() or response_text or "unknown error"
            return None, f"Antigravity review failed: {message}"
        if response_text and agy_output_is_error(response_text):
            recovered_text, recovered_error, recovered_conversation_id = extract_agy_response_from_state(
                agy_log_path,
                invocation_nonce=invocation_nonce,
                artifact_min_mtime=invocation_started_at,
            )
            if recovered_text:
                response_text = recovered_text
            elif response_text:
                suffix = f"; {recovered_error}" if recovered_error else ""
                return None, f"Antigravity CLI did not print a final response: {response_text}{suffix}"
        if not response_text:
            stderr = result.stderr.strip()
            recovered_text, recovered_error, recovered_conversation_id = extract_agy_response_from_state(
                agy_log_path,
                invocation_nonce=invocation_nonce,
                artifact_min_mtime=invocation_started_at,
            )
            if recovered_text:
                response_text = recovered_text
            else:
                message = "Antigravity CLI returned empty output" if not stderr else f"Antigravity CLI returned empty output. stderr: {stderr}"
                if recovered_error:
                    message = f"{message}; {recovered_error}"
                return None, message

        conversation_id = recovered_conversation_id
        if not conversation_id:
            conversation_id, conversation_error = select_agy_conversation_id_from_state(
                agy_log_path,
                invocation_nonce=invocation_nonce,
            )
            if conversation_error or not conversation_id:
                return None, conversation_error or "could not bind Antigravity transcript to this invocation"
        agy_model, agy_model_error = extract_agy_model_from_state(
            agy_log_path,
            conversation_id=conversation_id,
            invocation_nonce=invocation_nonce,
        )
        if agy_model_error:
            return None, agy_model_error
        model_family_error = require_gemini_model(agy_model, "Antigravity CLI")
        if model_family_error:
            return None, (
                f"{model_family_error}. The agy backend must expose the actual reviewer model "
                "in this invocation's log/transcript so ARIS can audit the cross-model invariant."
            )

        payload: dict[str, Any] = {
            "response": response_text,
            "model": agy_model,
            "model_provenance": "agy-log-or-transcript",
            "duration_ms": duration_ms,
            "stop_reason": None,
            "backend": "agy",
        }
        if requested_model:
            payload["requested_model"] = requested_model
            payload["warning"] = (
                "Antigravity CLI does not support per-call model selection in this bridge; "
                "requested_model is recorded for provenance only. "
                f"Actual model was recovered as {agy_model!r}."
            )
        return payload, None


def run_gemini_api_review(
    prompt: str,
    *,
    history: list[dict[str, str]],
    model: str | None,
    system: str | None,
    image_paths: list[str],
) -> tuple[dict[str, Any] | None, str | None]:
    api_key = get_api_key()
    if not api_key:
        return None, "Gemini API backend requires GEMINI_API_KEY or GOOGLE_API_KEY"

    selected_model, model_error = select_model_name(model, DEFAULT_MODEL, DEFAULT_API_MODEL)
    if model_error:
        return None, model_error
    model_family_error = require_gemini_model(selected_model, "Gemini API")
    if model_family_error:
        return None, model_family_error
    request_payload: dict[str, Any] = {
        "contents": [],
        "generationConfig": {"temperature": 0.2},
    }
    selected_system = (system or DEFAULT_SYSTEM).strip()
    if selected_system:
        request_payload["systemInstruction"] = {"parts": [{"text": selected_system}]}
    for item in history:
        request_payload["contents"].append(
            {
                "role": item["role"],
                "parts": [{"text": item["text"]}],
            }
        )
    user_parts: list[dict[str, Any]] = [{"text": prompt}]
    inline_parts, image_error = build_inline_image_parts(image_paths)
    if image_error:
        return None, image_error
    user_parts.extend(inline_parts)
    request_payload["contents"].append({"role": "user", "parts": user_parts})

    model_path = gemini_api_model_path(selected_model)
    url = f"https://generativelanguage.googleapis.com/v1beta/{model_path}:generateContent"
    request = urllib.request.Request(
        url,
        data=json.dumps(request_payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "x-goog-api-key": api_key,
        },
        method="POST",
    )

    debug_log(f"RUN gemini-api {selected_model}")
    try:
        started = time.monotonic()
        with urllib.request.urlopen(request, timeout=DEFAULT_TIMEOUT_SEC) as response:
            raw_stdout = response.read().decode("utf-8")
        duration_ms = int((time.monotonic() - started) * 1000)
    except urllib.error.HTTPError as exc:
        raw_text = exc.read().decode("utf-8", errors="replace")
        message = raw_text.strip()
        try:
            error_payload = json.loads(raw_text)
            if isinstance(error_payload, dict):
                error = error_payload.get("error")
                if isinstance(error, dict):
                    api_message = error.get("message")
                    if isinstance(api_message, str) and api_message.strip():
                        message = api_message.strip()
        except json.JSONDecodeError:
            pass
        return None, f"Gemini API failed with HTTP {exc.code}: {message or 'unknown error'}"
    except urllib.error.URLError as exc:
        return None, f"Gemini API request failed: {exc.reason}"

    try:
        api_payload = json.loads(raw_stdout)
    except json.JSONDecodeError:
        return None, "Gemini API response is not valid JSON"
    if not isinstance(api_payload, dict):
        return None, "Gemini API response JSON must be an object"

    try:
        response_text = extract_api_response_text(api_payload)
    except ValueError as exc:
        return None, str(exc)

    return {
        "response": response_text,
        "model": selected_model,
        "duration_ms": duration_ms,
        "stop_reason": None,
        "backend": "api",
    }, None


def run_gemini_review(
    prompt: str,
    *,
    session_id: str | None = None,
    model: str | None = None,
    system: str | None = None,
    tools: str | None = None,
    backend: str | None = None,
    image_paths: Any = None,
) -> tuple[dict[str, Any] | None, str | None]:
    del tools

    load_private_env_file()

    normalized_image_paths, image_error = normalize_image_paths(image_paths)
    if image_error:
        return None, image_error

    if session_id:
        thread_id, thread_error = normalize_safe_id(session_id, "threadId")
        if thread_error or thread_id is None:
            return None, thread_error or "invalid threadId"
    else:
        thread_id = uuid.uuid4().hex
    history = load_thread_history(thread_id) if session_id else []
    try:
        selected_backend = resolve_backend(backend)
    except ValueError as exc:
        return None, str(exc)

    if selected_backend == "api":
        payload, error = run_gemini_api_review(
            prompt,
            history=history,
            model=model,
            system=system,
            image_paths=normalized_image_paths,
        )
    elif selected_backend == "agy":
        payload, error = run_agy_cli_review(
            prompt,
            history=history,
            model=model,
            system=system,
            image_paths=normalized_image_paths,
        )
    else:
        payload, error = run_gemini_cli_review(
            prompt,
            history=history,
            model=model,
            system=system,
            image_paths=normalized_image_paths,
        )
    if error:
        return None, error

    if payload is None:
        return None, "Failed to parse reviewer output"
    updated_history = list(history)
    updated_history.append({"role": "user", "text": prompt})
    updated_history.append({"role": "model", "text": str(payload["response"])})
    save_thread_history(
        thread_id=thread_id,
        history=updated_history,
        model=str(payload["model"]),
        backend=str(payload["backend"]),
    )
    payload["threadId"] = thread_id
    return payload, None


def start_async_review(
    prompt: str,
    *,
    session_id: str | None = None,
    model: str | None = None,
    system: str | None = None,
    tools: str | None = None,
    backend: str | None = None,
    image_paths: Any = None,
) -> tuple[dict[str, Any] | None, str | None]:
    normalized_image_paths, image_error = normalize_image_paths(image_paths)
    if image_error:
        return None, image_error
    if session_id:
        safe_session_id, thread_error = normalize_safe_id(session_id, "threadId")
        if thread_error or safe_session_id is None:
            return None, thread_error or "invalid threadId"
        session_id = safe_session_id
    _, model_error = normalize_model_name(model)
    if model_error:
        return None, model_error

    job_id = uuid.uuid4().hex
    created_at = utc_now()
    job = {
        "jobId": job_id,
        "status": "queued",
        "createdAt": created_at,
        "startedAt": None,
        "completedAt": None,
        "updatedAt": created_at,
        "error": None,
        "result": None,
        "workerPid": None,
        "request": {
            "prompt": prompt,
            "threadId": session_id,
            "model": model,
            "system": system,
            "tools": tools,
            "backend": backend,
            "imagePaths": normalized_image_paths,
        },
    }

    job_path = job_state_path(job_id)
    write_json(job_path, job)

    try:
        worker = subprocess.Popen(
            [sys.executable, str(Path(__file__).resolve()), "--run-job", job_id],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            close_fds=True,
            start_new_session=True,
        )
    except OSError as exc:
        job["status"] = "failed"
        job["completedAt"] = utc_now()
        job["updatedAt"] = job["completedAt"]
        job["error"] = f"Failed to launch background review worker: {exc}"
        write_json(job_path, job)
        return None, job["error"]

    job["workerPid"] = worker.pid
    job["updatedAt"] = utc_now()
    write_json(job_path, job)
    debug_log(f"JOB_START job_id={job_id} worker_pid={worker.pid}")
    return serialize_job(job), None


def get_review_status(job_id: str, *, wait_seconds: int = 0) -> tuple[dict[str, Any] | None, str | None]:
    safe_job_id, job_error = normalize_safe_id(job_id, "jobId")
    if job_error or safe_job_id is None:
        return None, job_error or "invalid jobId"
    if wait_seconds < 0 or wait_seconds > MAX_STATUS_WAIT_SECONDS:
        return None, f"waitSeconds must be between 0 and {MAX_STATUS_WAIT_SECONDS}"
    job_path = job_state_path(safe_job_id)
    if not job_path.exists():
        return None, f"Unknown jobId: {safe_job_id}"

    deadline = time.monotonic() + wait_seconds
    while True:
        job = read_json(job_path)
        if job.get("status") in {"queued", "running"} and not is_pid_alive(job.get("workerPid")):
            job["status"] = "failed"
            job["error"] = "Background review worker exited before writing a final result"
            job["completedAt"] = utc_now()
            job["updatedAt"] = job["completedAt"]
            write_json(job_path, job)
        if job.get("status") in TERMINAL_JOB_STATES:
            return serialize_job(job), None
        if time.monotonic() >= deadline:
            return serialize_job(job), None
        time.sleep(min(0.5, max(deadline - time.monotonic(), 0.0)))


def run_async_job(job_id: str) -> int:
    safe_job_id, job_error = normalize_safe_id(job_id, "jobId")
    if job_error or safe_job_id is None:
        debug_log(f"JOB_INVALID job_id={job_id!r} error={job_error}")
        return 1
    job_id = safe_job_id
    job_path = job_state_path(job_id)
    if not job_path.exists():
        debug_log(f"JOB_MISSING job_id={job_id}")
        return 1

    job = read_json(job_path)
    job["status"] = "running"
    job["startedAt"] = utc_now()
    job["updatedAt"] = job["startedAt"]
    job["workerPid"] = os.getpid()
    write_json(job_path, job)
    debug_log(f"JOB_RUNNING job_id={job_id} worker_pid={os.getpid()}")

    request = job.get("request") or {}
    try:
        payload, error = run_gemini_review(
            str(request.get("prompt", "")),
            session_id=request.get("threadId"),
            model=request.get("model"),
            system=request.get("system"),
            tools=request.get("tools"),
            backend=request.get("backend"),
            image_paths=request.get("imagePaths"),
        )
    except Exception as exc:
        payload = None
        error = f"Background review crashed: {exc}"
        debug_log(traceback.format_exc())

    finished_at = utc_now()
    job = read_json(job_path)
    job["updatedAt"] = finished_at
    job["completedAt"] = finished_at
    if error:
        job["status"] = "failed"
        job["error"] = error
        job["result"] = None
        debug_log(f"JOB_FAILED job_id={job_id} error={error}")
        write_json(job_path, job)
        return 1

    job["status"] = "completed"
    job["error"] = None
    job["result"] = payload
    debug_log(f"JOB_COMPLETED job_id={job_id} thread_id={(payload or {}).get('threadId')}")
    write_json(job_path, job)
    return 0


def tool_success(request_id: Any, payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "result": {
            "content": [{"type": "text", "text": json.dumps(payload, ensure_ascii=False)}],
        },
    }


def tool_error(request_id: Any, message: str) -> dict[str, Any]:
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "result": {
            "content": [{"type": "text", "text": json.dumps({"error": message}, ensure_ascii=False)}],
            "isError": True,
        },
    }


def handle_request(request: dict[str, Any]) -> dict[str, Any] | None:
    request_id = request.get("id")
    method = request.get("method", "")
    params = request.get("params", {})
    debug_log(
        f"REQUEST id={request_id!r} method={method} "
        f"params={json.dumps(redact_for_debug(params), ensure_ascii=False)}"
    )

    if request_id is None:
        if method in {"notifications/initialized", "initialized"}:
            return None
        return None

    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": SERVER_NAME, "version": "1.0.0"},
            },
        }

    if method == "ping":
        return {"jsonrpc": "2.0", "id": request_id, "result": {}}

    if method == "resources/list":
        return {"jsonrpc": "2.0", "id": request_id, "result": {"resources": []}}

    if method == "resources/templates/list":
        return {"jsonrpc": "2.0", "id": request_id, "result": {"resourceTemplates": []}}

    if method in {"notifications/initialized", "initialized"}:
        return {"jsonrpc": "2.0", "id": request_id, "result": {}}

    if method == "tools/list":
        common_properties = {
            "prompt": {"type": "string", "description": "Reviewer prompt"},
            "system": {"type": "string", "description": "Optional system prompt"},
            "model": {"type": "string", "description": "Optional Gemini model override"},
            "backend": {"type": "string", "description": "Optional Gemini backend override: auto, api, cli, or agy"},
            "tools": {"type": "string", "description": "Accepted for compatibility but ignored by Gemini review"},
            "imagePaths": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Optional local image paths for Gemini API multimodal review",
            },
            "image_paths": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Alias of imagePaths",
            },
        }
        reply_properties = {
            "threadId": {"type": "string", "description": "Gemini thread id from a previous review call"},
            "thread_id": {"type": "string", "description": "Alias of threadId"},
            **common_properties,
        }
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {
                "tools": [
                    {
                        "name": "review",
                        "description": "Run a fresh Gemini review and return JSON containing threadId and response.",
                        "inputSchema": {
                            "type": "object",
                            "properties": common_properties,
                            "required": ["prompt"],
                        },
                    },
                    {
                        "name": "review_reply",
                        "description": "Continue a previous Gemini review session using threadId.",
                        "inputSchema": {
                            "type": "object",
                            "properties": reply_properties,
                            "required": ["prompt", "threadId"],
                        },
                    },
                    {
                        "name": "review_start",
                        "description": "Start a background Gemini review job and return a resumable jobId immediately.",
                        "inputSchema": {
                            "type": "object",
                            "properties": common_properties,
                            "required": ["prompt"],
                        },
                    },
                    {
                        "name": "review_reply_start",
                        "description": "Start a background follow-up review job in an existing Gemini thread and return a resumable jobId immediately.",
                        "inputSchema": {
                            "type": "object",
                            "properties": reply_properties,
                            "required": ["prompt", "threadId"],
                        },
                    },
                    {
                        "name": "review_status",
                        "description": "Check whether a background review job has finished and fetch the final result when available.",
                        "inputSchema": {
                            "type": "object",
                            "properties": {
                                "jobId": {"type": "string", "description": "Background review job id"},
                                "job_id": {"type": "string", "description": "Alias of jobId"},
                                "waitSeconds": {
                                    "type": "integer",
                                    "minimum": 0,
                                    "maximum": MAX_STATUS_WAIT_SECONDS,
                                    "description": "Optional bounded wait before returning status",
                                },
                            },
                            "required": ["jobId"],
                        },
                    },
                ]
            },
        }

    if method == "tools/call":
        name = params.get("name", "")
        args = params.get("arguments", {}) or {}

        if name == "review":
            payload, error = run_gemini_review(
                str(args.get("prompt", "")),
                model=args.get("model"),
                system=args.get("system"),
                tools=args.get("tools"),
                backend=args.get("backend"),
                image_paths=args.get("imagePaths") or args.get("image_paths"),
            )
            return tool_error(request_id, error) if error else tool_success(request_id, payload or {})

        if name == "review_reply":
            thread_id = args.get("threadId") or args.get("thread_id")
            if not thread_id:
                return tool_error(request_id, "threadId or thread_id is required")
            payload, error = run_gemini_review(
                str(args.get("prompt", "")),
                session_id=str(thread_id),
                model=args.get("model"),
                system=args.get("system"),
                tools=args.get("tools"),
                backend=args.get("backend"),
                image_paths=args.get("imagePaths") or args.get("image_paths"),
            )
            return tool_error(request_id, error) if error else tool_success(request_id, payload or {})

        if name == "review_start":
            payload, error = start_async_review(
                str(args.get("prompt", "")),
                model=args.get("model"),
                system=args.get("system"),
                tools=args.get("tools"),
                backend=args.get("backend"),
                image_paths=args.get("imagePaths") or args.get("image_paths"),
            )
            return tool_error(request_id, error) if error else tool_success(request_id, payload or {})

        if name == "review_reply_start":
            thread_id = args.get("threadId") or args.get("thread_id")
            if not thread_id:
                return tool_error(request_id, "threadId or thread_id is required")
            payload, error = start_async_review(
                str(args.get("prompt", "")),
                session_id=str(thread_id),
                model=args.get("model"),
                system=args.get("system"),
                tools=args.get("tools"),
                backend=args.get("backend"),
                image_paths=args.get("imagePaths") or args.get("image_paths"),
            )
            return tool_error(request_id, error) if error else tool_success(request_id, payload or {})

        if name == "review_status":
            job_id = args.get("jobId") or args.get("job_id")
            if not job_id:
                return tool_error(request_id, "jobId or job_id is required")
            wait_seconds_raw = args.get("waitSeconds", 0)
            try:
                wait_seconds = int(wait_seconds_raw)
            except (TypeError, ValueError):
                return tool_error(request_id, "waitSeconds must be an integer")
            payload, error = get_review_status(str(job_id), wait_seconds=wait_seconds)
            return tool_error(request_id, error) if error else tool_success(request_id, payload or {})

        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {"code": -32601, "message": f"Unknown tool: {name}"},
        }

    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "error": {"code": -32601, "message": f"Unknown method: {method}"},
    }


def main() -> None:
    _init_stdio()
    if len(sys.argv) == 3 and sys.argv[1] == "--run-job":
        raise SystemExit(run_async_job(sys.argv[2]))

    debug_log(f"=== {SERVER_NAME} starting ===")
    while True:
        try:
            request = read_message()
            if request is None:
                debug_log("EOF")
                break
            response = handle_request(request)
            if response is not None:
                send_response(response)
        except Exception:
            debug_log(traceback.format_exc())
            break


if __name__ == "__main__":
    main()
