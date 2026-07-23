#!/usr/bin/env python3
"""Shared Redmine review-finding functions using only the Python standard library."""

from __future__ import annotations

import hashlib
import json
import os
import posixpath
import stat
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


DEFAULT_STATUS_NAMES = {
    "new": "新規",
    "reviewing": "確認中",
    "accepted": "対応対象",
    "in_progress": "対応中",
    "verification": "修正確認中",
    "fixed": "修正済み",
    "not_actionable": "対応不要",
    "risk_accepted": "リスク受容",
    "on_hold": "保留",
    "duplicate": "重複",
    "withdrawn": "取下げ",
}

REQUIRED_CUSTOM_FIELDS = {
    "rule_id",
    "repository",
    "base_branch",
    "target_branch",
    "commit_sha",
    "file_path",
    "symbol",
    "line_number",
    "fingerprint",
    "review_source",
    "first_detected_at",
    "last_detected_at",
    "last_detected_commit",
    "detection_count",
    "recurrence_count",
    "ai_confidence",
}

REQUIRED_FINDING_FIELDS = {
    "title",
    "description",
    "remediation",
    "severity",
    "category",
    "rule_id",
    "file_path",
    "symbol",
    "line_number",
    "code_context",
}

REQUIRED_INPUT_FIELDS = {
    "repository",
    "base_branch",
    "target_branch",
    "commit_sha",
    "reviewed_file_count",
    "review_source",
    "detected_at",
    "findings",
}


class ReviewFindingError(RuntimeError):
    """A safe-to-display configuration, input, or Redmine error."""


def load_json(path: str | Path) -> dict[str, Any]:
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ReviewFindingError(f"JSONを読み込めません: {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ReviewFindingError(f"JSONのルートはオブジェクトである必要があります: {path}")
    return value


def load_config(path: str | Path) -> dict[str, Any]:
    config_path = Path(path)
    config = load_json(config_path)
    if config.get("api_key") and os.name != "nt":
        mode = stat.S_IMODE(config_path.stat().st_mode)
        if mode & 0o077:
            raise ReviewFindingError(
                f"APIキーを含む設定ファイルの権限は600にしてください: {config_path}"
            )
    return config


def validate_config(config: dict[str, Any]) -> None:
    missing = sorted({"project", "tracker", "custom_fields", "priority_map"} - config.keys())
    if missing:
        raise ReviewFindingError(f"設定に必須項目がありません: {', '.join(missing)}")
    if not config.get("redmine_url") and not os.environ.get("REDMINE_URL"):
        raise ReviewFindingError("redmine_urlまたはREDMINE_URLが必要です")
    custom_fields = config.get("custom_fields")
    if not isinstance(custom_fields, dict):
        raise ReviewFindingError("custom_fieldsはオブジェクトである必要があります")
    missing_fields = sorted(REQUIRED_CUSTOM_FIELDS - custom_fields.keys())
    if missing_fields:
        raise ReviewFindingError(
            f"custom_fieldsに必須項目がありません: {', '.join(missing_fields)}"
        )
    for key in REQUIRED_CUSTOM_FIELDS:
        field = custom_fields[key]
        if (
            not isinstance(field, dict)
            or not isinstance(field.get("id"), int)
            or field["id"] <= 0
            or not isinstance(field.get("name"), str)
            or not field["name"]
        ):
            raise ReviewFindingError(
                f"custom_fields.{key}には正の整数idとnameが必要です"
            )
    if not isinstance(config.get("priority_map"), dict) or not config["priority_map"]:
        raise ReviewFindingError("priority_mapには1件以上の対応関係が必要です")
    if "api_key" in config and (
        not isinstance(config["api_key"], str) or not config["api_key"].strip()
    ):
        raise ReviewFindingError("api_keyは空でない文字列にしてください")


def validate_findings_input(payload: dict[str, Any]) -> None:
    missing = sorted(REQUIRED_INPUT_FIELDS - payload.keys())
    if missing:
        raise ReviewFindingError(f"入力に必須項目がありません: {', '.join(missing)}")
    findings = payload.get("findings")
    if not isinstance(findings, list):
        raise ReviewFindingError("findingsは配列である必要があります")
    if not isinstance(payload.get("reviewed_file_count"), int) or payload["reviewed_file_count"] < 0:
        raise ReviewFindingError("reviewed_file_countは0以上の整数である必要があります")
    if payload.get("review_source") not in {"Codex", "静的解析"}:
        raise ReviewFindingError("自動処理のreview_sourceはCodexまたは静的解析にしてください")
    try:
        datetime.fromisoformat(str(payload["detected_at"]))
    except ValueError as exc:
        raise ReviewFindingError("detected_atはISO 8601形式にしてください") from exc
    for index, finding in enumerate(findings):
        if not isinstance(finding, dict):
            raise ReviewFindingError(f"findings[{index}]はオブジェクトである必要があります")
        missing_finding = sorted(REQUIRED_FINDING_FIELDS - finding.keys())
        if missing_finding:
            raise ReviewFindingError(
                f"findings[{index}]に必須項目がありません: {', '.join(missing_finding)}"
            )
        if not isinstance(finding["line_number"], int) or finding["line_number"] < 1:
            raise ReviewFindingError(
                f"findings[{index}].line_numberは1以上の整数にしてください"
            )
        for key in REQUIRED_FINDING_FIELDS - {"line_number"}:
            if not isinstance(finding[key], str) or not finding[key].strip():
                raise ReviewFindingError(
                    f"findings[{index}].{key}は空でない文字列にしてください"
                )
        confidence = finding.get("ai_confidence")
        if payload["review_source"] == "Codex" and confidence is None:
            raise ReviewFindingError(
                f"findings[{index}].ai_confidenceはCodexレビューで必須です"
            )
        if confidence is not None and (
            not isinstance(confidence, int) or not 0 <= confidence <= 100
        ):
            raise ReviewFindingError(
                f"findings[{index}].ai_confidenceは0から100の整数にしてください"
            )


def normalize_file_path(value: str) -> str:
    normalized = posixpath.normpath(str(value).replace("\\", "/"))
    if normalized == "." or normalized.startswith("../") or normalized.startswith("/"):
        raise ReviewFindingError("file_pathはリポジトリルートからの相対パスにしてください")
    return normalized


def normalize_context(value: str) -> str:
    lines = str(value).replace("\r\n", "\n").replace("\r", "\n").split("\n")
    lines = [line.rstrip() for line in lines]
    while lines and not lines[0]:
        lines.pop(0)
    while lines and not lines[-1]:
        lines.pop()
    return "\n".join(lines)


def make_fingerprint(repository: str, finding: dict[str, Any]) -> str:
    canonical = {
        "repository": str(repository).strip(),
        "rule_id": str(finding["rule_id"]).strip(),
        "file_path": normalize_file_path(str(finding["file_path"])),
        "symbol": str(finding.get("symbol") or "<global>").strip(),
        "code_context": normalize_context(str(finding["code_context"])),
    }
    encoded = json.dumps(
        canonical, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def custom_field_values(issue: dict[str, Any]) -> dict[int, Any]:
    return {
        int(field["id"]): field.get("value")
        for field in issue.get("custom_fields", [])
        if "id" in field
    }


def integer_value(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def status_action(status_name: str, names: dict[str, str]) -> dict[str, Any]:
    if status_name == names["fixed"]:
        return {"status": names["reviewing"], "increment_detection": True, "increment_recurrence": True}
    if status_name == names["on_hold"]:
        return {"status": None, "increment_detection": False, "increment_recurrence": False}
    if status_name == names["duplicate"]:
        return {"duplicate": True}
    return {"status": None, "increment_detection": True, "increment_recurrence": False}


@dataclass
class ResolvedSetup:
    project_id: int
    tracker_id: int
    status_ids: dict[str, int]
    priority_ids: dict[str, int]
    category_ids: dict[str, int]
    warnings: list[str]


class RedmineClient:
    def __init__(self, base_url: str, api_key: str, timeout: int = 30):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout

    @classmethod
    def from_config(cls, config: dict[str, Any]) -> "RedmineClient":
        api_key = os.environ.get("REDMINE_API_KEY") or config.get("api_key")
        if not api_key:
            raise ReviewFindingError(
                "REDMINE_API_KEYまたはconfig/redmine.jsonのapi_keyが必要です"
            )
        base_url = config.get("redmine_url") or os.environ.get("REDMINE_URL")
        return cls(str(base_url), api_key, int(config.get("timeout_seconds", 30)))

    def request(
        self,
        method: str,
        path: str,
        *,
        query: dict[str, Any] | None = None,
        body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        url = f"{self.base_url}{path}"
        if query:
            url += "?" + urllib.parse.urlencode(query)
        data = None
        headers = {
            "Accept": "application/json",
            "X-Redmine-API-Key": self.api_key,
        }
        if body is not None:
            data = json.dumps(body, ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                raw = response.read()
                return json.loads(raw.decode("utf-8")) if raw else {}
        except urllib.error.HTTPError as exc:
            safe_body = exc.read().decode("utf-8", errors="replace")[:500]
            raise ReviewFindingError(
                f"Redmine API {exc.code}: {method} {path}: {safe_body}"
            ) from exc
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise ReviewFindingError(f"Redmine API接続エラー: {method} {path}: {exc}") from exc

    def find_issues(self, query: dict[str, Any]) -> list[dict[str, Any]]:
        offset = 0
        issues: list[dict[str, Any]] = []
        while True:
            page_query = {**query, "limit": 100, "offset": offset}
            result = self.request("GET", "/issues.json", query=page_query)
            page = result.get("issues", [])
            issues.extend(page)
            total = int(result.get("total_count", len(issues)))
            offset += len(page)
            if not page or offset >= total:
                return issues

    def get_issue(self, issue_id: int) -> dict[str, Any]:
        return self.request(
            "GET", f"/issues/{issue_id}.json", query={"include": "relations"}
        )["issue"]

    def create_issue(self, issue: dict[str, Any]) -> dict[str, Any]:
        return self.request("POST", "/issues.json", body={"issue": issue})["issue"]

    def update_issue(self, issue_id: int, issue: dict[str, Any]) -> None:
        self.request("PUT", f"/issues/{issue_id}.json", body={"issue": issue})


def resolve_setup(
    client: RedmineClient, config: dict[str, Any], *, verify_custom_fields: bool = True
) -> ResolvedSetup:
    project_key = str(config["project"])
    project_result = client.request(
        "GET",
        f"/projects/{urllib.parse.quote(project_key, safe='')}.json",
        query={"include": "trackers,issue_categories,issue_custom_fields"},
    )
    project = project_result["project"]
    trackers = project.get("trackers") or client.request("GET", "/trackers.json").get("trackers", [])
    tracker = next((item for item in trackers if item.get("name") == config["tracker"]), None)
    if not tracker:
        raise ReviewFindingError(f"トラッカーが見つかりません: {config['tracker']}")

    status_names = {**DEFAULT_STATUS_NAMES, **config.get("status_names", {})}
    statuses = client.request("GET", "/issue_statuses.json").get("issue_statuses", [])
    by_status_name = {item["name"]: int(item["id"]) for item in statuses}
    missing_statuses = sorted(set(status_names.values()) - by_status_name.keys())
    if missing_statuses:
        raise ReviewFindingError(f"ステータスが見つかりません: {', '.join(missing_statuses)}")

    priorities = client.request(
        "GET", "/enumerations/issue_priorities.json"
    ).get("issue_priorities", [])
    by_priority_name = {item["name"]: int(item["id"]) for item in priorities}
    missing_priorities = sorted(set(config["priority_map"].values()) - by_priority_name.keys())
    if missing_priorities:
        raise ReviewFindingError(f"優先度が見つかりません: {', '.join(missing_priorities)}")

    categories = project.get("issue_categories", [])
    category_ids = {item["name"]: int(item["id"]) for item in categories}
    warnings: list[str] = []

    if verify_custom_fields:
        try:
            remote_fields = project.get("issue_custom_fields")
            if remote_fields is None:
                remote_fields = client.request("GET", "/custom_fields.json").get(
                    "custom_fields", []
                )
            by_field_id = {int(item["id"]): item["name"] for item in remote_fields}
            for key, configured in config["custom_fields"].items():
                field_metadata = next(
                    (
                        item
                        for item in remote_fields
                        if int(item["id"]) == int(configured["id"])
                    ),
                    None,
                )
                actual = by_field_id.get(int(configured["id"]))
                if field_metadata is None or actual is None:
                    raise ReviewFindingError(
                        f"カスタムフィールドIDが見つかりません: {key}={configured['id']}"
                    )
                if actual != configured["name"]:
                    raise ReviewFindingError(
                        f"カスタムフィールド名が一致しません: {key}: "
                        f"{configured['name']} != {actual}"
                    )
                if (
                    key in {"fingerprint", "rule_id", "file_path", "symbol"}
                    and field_metadata.get("is_filter") is False
                ):
                    raise ReviewFindingError(
                        f"カスタムフィールドで「フィルタとして使用」が無効です: {actual}"
                    )
        except ReviewFindingError as exc:
            if "Redmine API 403" in str(exc) or "Redmine API 404" in str(exc):
                warnings.append(
                    "APIユーザーにカスタムフィールド一覧権限がないため、IDと名称を検証できません"
                )
            else:
                raise

    return ResolvedSetup(
        project_id=int(project["id"]),
        tracker_id=int(tracker["id"]),
        status_ids={key: by_status_name[name] for key, name in status_names.items()},
        priority_ids={
            severity: by_priority_name[name]
            for severity, name in config["priority_map"].items()
        },
        category_ids=category_ids,
        warnings=warnings,
    )


def field_id(config: dict[str, Any], name: str) -> int:
    return int(config["custom_fields"][name]["id"])


def field_payload(config: dict[str, Any], values: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {"id": field_id(config, key), "value": "" if value is None else str(value)}
        for key, value in values.items()
    ]
