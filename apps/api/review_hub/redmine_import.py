"""One-time Redmine to Review Hub migration.

Run this command while the API container is stopped.
"""

from __future__ import annotations

import argparse
import json
import os
import stat
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from .database import SessionLocal
from .domain import STATUSES
from .models import AuditEvent, Finding, FindingRelation, Repository
from .service import get_or_create_repository, next_sequence


class ImportFailure(RuntimeError):
    pass


class RedmineReader:
    def __init__(self, url: str, api_key: str):
        self.url = url.rstrip("/")
        self.api_key = api_key

    def get(self, path: str, query: dict[str, Any] | None = None) -> dict:
        url = f"{self.url}{path}"
        if query:
            url += "?" + urllib.parse.urlencode(query)
        request = urllib.request.Request(
            url,
            headers={
                "Accept": "application/json",
                "X-Redmine-API-Key": self.api_key,
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                return json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, json.JSONDecodeError) as exc:
            raise ImportFailure(f"Redmine API read failed: {path}: {exc}") from exc

    def issues(self, project: str) -> list[dict]:
        offset = 0
        output: list[dict] = []
        while True:
            result = self.get(
                "/issues.json",
                {
                    "project_id": project,
                    "status_id": "*",
                    "limit": 100,
                    "offset": offset,
                },
            )
            page = result.get("issues", [])
            output.extend(page)
            offset += len(page)
            if not page or offset >= int(result.get("total_count", len(output))):
                return output

    def issue_detail(self, issue_id: int) -> dict:
        return self.get(
            f"/issues/{issue_id}.json",
            {"include": "relations,journals"},
        )["issue"]


def load_config(path: str) -> dict:
    config_path = Path(path)
    config = json.loads(config_path.read_text(encoding="utf-8"))
    if config.get("api_key") and os.name != "nt":
        mode = stat.S_IMODE(config_path.stat().st_mode)
        if mode & 0o077:
            raise ImportFailure("APIキーを含む設定ファイルの権限は600にしてください")
    return config


def custom_values(issue: dict) -> dict[int, Any]:
    return {
        int(field["id"]): field.get("value")
        for field in issue.get("custom_fields", [])
        if field.get("id") is not None
    }


def split_description(value: str) -> tuple[str, str]:
    marker = "\n\n修正案:\n"
    if marker not in value:
        return value or "(説明なし)", "(修正案なし)"
    description, remediation = value.split(marker, 1)
    remediation = remediation.split("\n\n重複候補:", 1)[0]
    return description or "(説明なし)", remediation or "(修正案なし)"


def parse_time(value: str | None) -> datetime:
    if not value:
        return datetime.now().astimezone()
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def prepare_issues(config: dict, reader: RedmineReader) -> list[dict]:
    fields = config["custom_fields"]
    field_ids = {name: int(item["id"]) for name, item in fields.items()}
    prepared: list[dict] = []
    seen_fingerprints: dict[tuple[str, str], int] = {}
    errors: list[str] = []
    for summary in reader.issues(str(config["project"])):
        detail = reader.issue_detail(int(summary["id"]))
        values = custom_values(detail)
        repository = str(values.get(field_ids["repository"]) or "").strip()
        fingerprint = str(values.get(field_ids["fingerprint"]) or "").strip() or None
        status = detail.get("status", {}).get("name")
        if not repository:
            errors.append(f"#{detail['id']}: repository is missing")
        if status not in STATUSES:
            errors.append(f"#{detail['id']}: unknown status: {status}")
        if fingerprint:
            key = (repository, fingerprint)
            if key in seen_fingerprints:
                errors.append(
                    f"#{detail['id']}: fingerprint collision with "
                    f"#{seen_fingerprints[key]}"
                )
            seen_fingerprints[key] = int(detail["id"])
        description, remediation = split_description(detail.get("description", ""))
        prepared.append(
            {
                "issue": detail,
                "repository": repository,
                "fingerprint": fingerprint,
                "description": description,
                "remediation": remediation,
                "values": values,
                "field_ids": field_ids,
            }
        )
    if errors:
        raise ImportFailure("Migration prerequisites failed:\n- " + "\n- ".join(errors))
    return prepared


def apply_import(config: dict, prepared: list[dict]) -> dict:
    priority_to_severity = {
        remote: severity for severity, remote in config.get("priority_map", {}).items()
    }
    imported = 0
    skipped = 0
    legacy_to_finding: dict[int, str] = {}
    with SessionLocal() as session, session.begin():
        for item in prepared:
            issue = item["issue"]
            issue_id = int(issue["id"])
            existing = session.scalar(
                select(Finding).where(Finding.legacy_redmine_issue_id == issue_id)
            )
            if existing:
                legacy_to_finding[issue_id] = existing.id
                skipped += 1
                continue
            values = item["values"]
            ids = item["field_ids"]
            repository = get_or_create_repository(session, item["repository"])
            detected_at = parse_time(
                values.get(ids["first_detected_at"]) or issue.get("created_on")
            )
            last_detected_at = parse_time(
                values.get(ids["last_detected_at"]) or issue.get("updated_on")
            )
            finding = Finding(
                sequence=next_sequence(session),
                repository_id=repository.id,
                title=issue.get("subject") or f"Redmine #{issue_id}",
                description_markdown=item["description"],
                remediation_markdown=item["remediation"],
                severity=priority_to_severity.get(
                    issue.get("priority", {}).get("name"), "Medium"
                ),
                category=issue.get("category", {}).get("name", "Uncategorized"),
                rule_id=str(values.get(ids["rule_id"]) or f"REDMINE-{issue_id}"),
                file_path=str(values.get(ids["file_path"]) or "<unknown>"),
                symbol=str(values.get(ids["symbol"]) or "<global>"),
                line_number=int(values.get(ids["line_number"]) or 1),
                fingerprint=item["fingerprint"],
                status=issue["status"]["name"],
                review_source=str(values.get(ids["review_source"]) or "有識者"),
                code_excerpt=None,
                code_language=None,
                first_detected_at=detected_at,
                last_detected_at=last_detected_at,
                last_detected_commit=str(
                    values.get(ids["last_detected_commit"])
                    or values.get(ids["commit_sha"])
                    or "<imported>"
                ),
                detection_count=int(values.get(ids["detection_count"]) or 1),
                recurrence_count=int(values.get(ids["recurrence_count"]) or 0),
                ai_confidence=(
                    int(values[ids["ai_confidence"]])
                    if values.get(ids["ai_confidence"]) not in (None, "")
                    else None
                ),
                legacy_redmine_issue_id=issue_id,
                created_by="redmine-import",
                updated_by="redmine-import",
                created_at=parse_time(issue.get("created_on")),
                updated_at=parse_time(issue.get("updated_on")),
            )
            session.add(finding)
            session.flush()
            legacy_to_finding[issue_id] = finding.id
            session.add(
                AuditEvent(
                    finding_id=finding.id,
                    event_type="imported",
                    actor_type="migration",
                    actor_label="redmine-import",
                    previous_values={},
                    resulting_values={
                        "legacy_redmine_issue_id": issue_id,
                        "status": finding.status,
                    },
                    reason="Redmineから移行しました",
                )
            )
            for journal in issue.get("journals", []):
                notes = str(journal.get("notes") or "").strip()
                if notes:
                    session.add(
                        AuditEvent(
                            finding_id=finding.id,
                            event_type="legacy_note",
                            actor_type="migration",
                            actor_label=journal.get("user", {}).get(
                                "name", "redmine-user"
                            ),
                            previous_values={},
                            resulting_values={},
                            reason=notes,
                            created_at=parse_time(journal.get("created_on")),
                        )
                    )
            imported += 1

        unresolved: list[str] = []
        for item in prepared:
            issue = item["issue"]
            source_id = legacy_to_finding[int(issue["id"])]
            for relation in issue.get("relations", []):
                if relation.get("relation_type") != "duplicates":
                    continue
                if int(relation.get("issue_id", 0)) != int(issue["id"]):
                    continue
                target_legacy = int(relation.get("issue_to_id", 0))
                target_id = legacy_to_finding.get(target_legacy)
                if not target_id:
                    unresolved.append(f"#{issue['id']} -> #{target_legacy}")
                    continue
                exists = session.scalar(
                    select(FindingRelation).where(
                        FindingRelation.source_finding_id == source_id,
                        FindingRelation.target_finding_id == target_id,
                        FindingRelation.relation_type == "duplicate_of",
                    )
                )
                if not exists:
                    session.add(
                        FindingRelation(
                            source_finding_id=source_id,
                            target_finding_id=target_id,
                            relation_type="duplicate_of",
                            created_by="redmine-import",
                        )
                    )
        if unresolved:
            raise ImportFailure(
                "Unresolved duplicate sources:\n- " + "\n- ".join(unresolved)
            )
    return {"status": "ok", "imported": imported, "skipped": skipped}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    try:
        config = load_config(args.config)
        api_key = os.environ.get("REDMINE_API_KEY") or config.get("api_key")
        if not api_key:
            raise ImportFailure("REDMINE_API_KEYまたはapi_keyが必要です")
        reader = RedmineReader(config["redmine_url"], api_key)
        prepared = prepare_issues(config, reader)
        if args.dry_run:
            output = {"status": "ok", "dry_run": True, "issues": len(prepared)}
        else:
            output = {**apply_import(config, prepared), "dry_run": False}
        print(json.dumps(output, ensure_ascii=False, indent=2))
        return 0
    except (
        ImportFailure,
        KeyError,
        OSError,
        SQLAlchemyError,
        ValueError,
        json.JSONDecodeError,
    ) as exc:
        print(json.dumps({"status": "error", "error": str(exc)}, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
