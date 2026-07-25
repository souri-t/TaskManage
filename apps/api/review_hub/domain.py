from __future__ import annotations

import hashlib
import json
import posixpath
import re
from pathlib import PurePosixPath
from typing import Any


STATUSES = (
    "新規",
    "確認中",
    "対応対象",
    "対応中",
    "修正確認中",
    "保留",
    "修正済み",
    "対応不要",
    "リスク受容",
    "重複",
    "取下げ",
)
SEVERITIES = ("Critical", "High", "Medium", "Low")
AUTOMATION_SOURCES = ("Codex", "静的解析")
HUMAN_SOURCE = "有識者"

ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    "新規": {"確認中", "対応対象", "対応不要", "リスク受容", "保留", "取下げ"},
    "確認中": {"対応対象", "対応不要", "リスク受容", "保留", "取下げ"},
    "対応対象": {"対応中", "保留", "取下げ"},
    "対応中": {"修正確認中", "保留"},
    "修正確認中": {"修正済み", "対応中"},
    "保留": {"確認中", "対応対象", "取下げ"},
    "修正済み": {"確認中"},
    "対応不要": {"確認中"},
    "リスク受容": {"確認中"},
    "重複": set(),
    "取下げ": {"確認中"},
}

LANGUAGE_BY_SUFFIX = {
    ".py": "python",
    ".js": "javascript",
    ".jsx": "jsx",
    ".ts": "typescript",
    ".tsx": "tsx",
    ".java": "java",
    ".go": "go",
    ".rs": "rust",
    ".rb": "ruby",
    ".php": "php",
    ".cs": "csharp",
    ".cpp": "cpp",
    ".c": "c",
    ".h": "c",
    ".sh": "bash",
    ".sql": "sql",
    ".json": "json",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".xml": "xml",
    ".html": "html",
    ".css": "css",
    ".md": "markdown",
}

SECRET_PATTERNS = (
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----", re.S),
    re.compile(
        r"(?im)^(\s*(?:api[_-]?key|token|password|secret|client[_-]?secret)\s*[:=]\s*)"
        r"([\"']?)[^\s,\"']+([\"']?)"
    ),
    re.compile(r"\b(?:ghp|github_pat|sk_live|sk_test)_[A-Za-z0-9_=-]{12,}\b"),
)


class DomainError(ValueError):
    pass


def normalize_file_path(value: str) -> str:
    normalized = posixpath.normpath(value.replace("\\", "/"))
    if normalized == "." or normalized.startswith("../") or normalized.startswith("/"):
        raise DomainError("file_pathはリポジトリルートからの相対パスにしてください")
    return normalized


def normalize_context(value: str) -> str:
    lines = value.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    lines = [line.rstrip() for line in lines]
    while lines and not lines[0]:
        lines.pop(0)
    while lines and not lines[-1]:
        lines.pop()
    return "\n".join(lines)


def make_fingerprint(repository: str, finding: dict[str, Any]) -> str:
    canonical = {
        "repository": repository.strip(),
        "rule_id": str(finding["rule_id"]).strip(),
        "file_path": normalize_file_path(str(finding["file_path"])),
        "symbol": str(finding.get("symbol") or "<global>").strip(),
        "code_context": normalize_context(str(finding["code_context"])),
    }
    encoded = json.dumps(
        canonical, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def context_hash(code_context: str) -> str:
    return hashlib.sha256(normalize_context(code_context).encode("utf-8")).hexdigest()


def redact_code(value: str) -> str:
    redacted = value
    redacted = SECRET_PATTERNS[0].sub("[REDACTED PRIVATE KEY]", redacted)
    redacted = SECRET_PATTERNS[1].sub(r"\1[REDACTED]", redacted)
    redacted = SECRET_PATTERNS[2].sub("[REDACTED TOKEN]", redacted)
    return redacted


def stored_code_excerpt(value: str, max_lines: int, max_bytes: int) -> str:
    redacted = redact_code(value)
    by_lines = "\n".join(redacted.splitlines()[:max_lines])
    encoded = by_lines.encode("utf-8")
    if len(encoded) <= max_bytes:
        return by_lines
    return encoded[:max_bytes].decode("utf-8", errors="ignore")


def infer_language(file_path: str, requested: str | None) -> str:
    if requested:
        return requested.strip().lower()
    return LANGUAGE_BY_SUFFIX.get(PurePosixPath(file_path).suffix.lower(), "text")


def rediscovery_action(status: str) -> dict[str, Any]:
    if status == "修正済み":
        return {
            "status": "確認中",
            "increment_detection": True,
            "increment_recurrence": True,
            "action": "reopened",
        }
    if status == "保留":
        return {
            "status": None,
            "increment_detection": False,
            "increment_recurrence": False,
            "action": "updated",
        }
    if status == "重複":
        return {"duplicate": True, "action": "updated"}
    return {
        "status": None,
        "increment_detection": True,
        "increment_recurrence": False,
        "action": "updated",
    }
