#!/usr/bin/env python3
"""Reconcile structured review findings with Redmine."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from redmine_common import (
    DEFAULT_STATUS_NAMES,
    RedmineClient,
    ResolvedSetup,
    ReviewFindingError,
    custom_field_values,
    field_id,
    field_payload,
    integer_value,
    load_config,
    load_json,
    make_fingerprint,
    normalize_file_path,
    resolve_setup,
    status_action,
    validate_config,
    validate_findings_input,
)


def issue_query(
    setup: ResolvedSetup, config: dict[str, Any], fields: dict[str, Any]
) -> dict[str, Any]:
    query: dict[str, Any] = {
        "project_id": setup.project_id,
        "tracker_id": setup.tracker_id,
        "status_id": "*",
    }
    for key, value in fields.items():
        query[f"cf_{field_id(config, key)}"] = value
    return query


def is_human(issue: dict[str, Any], config: dict[str, Any]) -> bool:
    fields = custom_field_values(issue)
    return fields.get(field_id(config, "review_source")) == "有識者"


def duplicate_source(
    client: RedmineClient, issue: dict[str, Any]
) -> dict[str, Any] | None:
    detailed = client.get_issue(int(issue["id"]))
    current_id = int(issue["id"])
    for relation in detailed.get("relations", []):
        issue_id = int(relation.get("issue_id", 0))
        issue_to_id = int(relation.get("issue_to_id", 0))
        relation_type = relation.get("relation_type")
        if relation_type == "duplicates" and issue_id == current_id and issue_to_id:
            return client.get_issue(issue_to_id)
        if relation_type == "duplicated" and issue_to_id == current_id and issue_id:
            return client.get_issue(issue_id)
    return None


def notes_for_candidates(candidate_ids: list[int]) -> str:
    if not candidate_ids:
        return ""
    joined = ", ".join(f"#{issue_id}" for issue_id in candidate_ids)
    return f"\n\n重複候補: {joined}"


def description_for(finding: dict[str, Any], candidate_ids: list[int]) -> str:
    return (
        f"{finding['description']}\n\n"
        f"修正案:\n{finding['remediation']}"
        f"{notes_for_candidates(candidate_ids)}"
    )


def update_existing(
    *,
    client: RedmineClient,
    config: dict[str, Any],
    setup: ResolvedSetup,
    payload: dict[str, Any],
    issue: dict[str, Any],
    dry_run: bool,
    recursion_depth: int = 0,
) -> dict[str, Any]:
    if recursion_depth > 2:
        raise ReviewFindingError("重複チケットの参照が循環しています")
    if is_human(issue, config):
        return {"action": "suppressed_human", "issue_id": int(issue["id"])}

    status_name = issue["status"]["name"]
    names = {**DEFAULT_STATUS_NAMES, **config.get("status_names", {})}
    action = status_action(status_name, names)
    if action.get("duplicate"):
        source = duplicate_source(client, issue)
        if not source:
            return {
                "action": "skipped",
                "issue_id": int(issue["id"]),
                "reason": "重複元チケットを特定できません",
            }
        return update_existing(
            client=client,
            config=config,
            setup=setup,
            payload=payload,
            issue=source,
            dry_run=dry_run,
            recursion_depth=recursion_depth + 1,
        )

    current_fields = custom_field_values(issue)
    detection_count = integer_value(
        current_fields.get(field_id(config, "detection_count"))
    )
    recurrence_count = integer_value(
        current_fields.get(field_id(config, "recurrence_count"))
    )
    updates: dict[str, Any] = {
        "last_detected_at": payload["detected_at"],
        "last_detected_commit": payload["commit_sha"],
    }
    if action["increment_detection"]:
        updates["detection_count"] = detection_count + 1
    if action["increment_recurrence"]:
        updates["recurrence_count"] = recurrence_count + 1

    issue_update: dict[str, Any] = {"custom_fields": field_payload(config, updates)}
    result_action = "updated"
    if action.get("status"):
        status_key = next(
            key for key, name in names.items() if name == action["status"]
        )
        issue_update["status_id"] = setup.status_ids[status_key]
        issue_update["notes"] = "同じ指摘を再検出したため、確認中へ戻しました。"
        result_action = "reopened"
    if not dry_run:
        client.update_issue(int(issue["id"]), issue_update)
    return {"action": result_action, "issue_id": int(issue["id"])}


def create_new(
    *,
    client: RedmineClient,
    config: dict[str, Any],
    setup: ResolvedSetup,
    payload: dict[str, Any],
    finding: dict[str, Any],
    fingerprint: str,
    candidate_ids: list[int],
    dry_run: bool,
) -> dict[str, Any]:
    severity = str(finding["severity"])
    if severity not in setup.priority_ids:
        raise ReviewFindingError(f"重要度の対応が設定されていません: {severity}")
    category = finding.get("category")
    if category and category not in setup.category_ids:
        raise ReviewFindingError(f"チケットカテゴリが見つかりません: {category}")

    values = {
        "rule_id": finding["rule_id"],
        "repository": payload["repository"],
        "base_branch": payload["base_branch"],
        "target_branch": payload["target_branch"],
        "commit_sha": payload["commit_sha"],
        "file_path": normalize_file_path(str(finding["file_path"])),
        "symbol": finding.get("symbol") or "<global>",
        "line_number": finding["line_number"],
        "fingerprint": fingerprint,
        "review_source": payload["review_source"],
        "first_detected_at": payload["detected_at"],
        "last_detected_at": payload["detected_at"],
        "last_detected_commit": payload["commit_sha"],
        "detection_count": 1,
        "recurrence_count": 0,
        "ai_confidence": finding.get("ai_confidence", ""),
    }
    issue: dict[str, Any] = {
        "project_id": setup.project_id,
        "tracker_id": setup.tracker_id,
        "status_id": setup.status_ids["new"],
        "priority_id": setup.priority_ids[severity],
        "subject": finding["title"],
        "description": description_for(finding, candidate_ids),
        "custom_fields": field_payload(config, values),
    }
    if category:
        issue["category_id"] = setup.category_ids[category]
    if dry_run:
        return {"action": "would_create", "candidate_issue_ids": candidate_ids}
    concurrent = client.find_issues(
        issue_query(setup, config, {"fingerprint": fingerprint})
    )
    if concurrent:
        human_matches = [item for item in concurrent if is_human(item, config)]
        if human_matches:
            return {
                "action": "suppressed_human",
                "issue_ids": sorted(int(item["id"]) for item in human_matches),
            }
        return update_existing(
            client=client,
            config=config,
            setup=setup,
            payload=payload,
            issue=min(concurrent, key=lambda item: int(item["id"])),
            dry_run=False,
        )
    created = client.create_issue(issue)
    return {
        "action": "created",
        "issue_id": int(created["id"]),
        "candidate_issue_ids": candidate_ids,
    }


def process_finding(
    *,
    client: RedmineClient,
    config: dict[str, Any],
    setup: ResolvedSetup,
    payload: dict[str, Any],
    finding: dict[str, Any],
    dry_run: bool,
) -> dict[str, Any]:
    fingerprint = make_fingerprint(payload["repository"], finding)
    exact = client.find_issues(
        issue_query(setup, config, {"fingerprint": fingerprint})
    )
    if exact:
        human_matches = [item for item in exact if is_human(item, config)]
        if human_matches:
            return {
                "action": "suppressed_human",
                "issue_ids": sorted(int(item["id"]) for item in human_matches),
                "fingerprint": fingerprint,
            }
        issue = min(exact, key=lambda item: int(item["id"]))
        result = update_existing(
            client=client,
            config=config,
            setup=setup,
            payload=payload,
            issue=issue,
            dry_run=dry_run,
        )
        result["fingerprint"] = fingerprint
        return result

    candidate_fields = {
        "rule_id": finding["rule_id"],
        "file_path": normalize_file_path(str(finding["file_path"])),
        "symbol": finding.get("symbol") or "<global>",
    }
    candidates = client.find_issues(issue_query(setup, config, candidate_fields))
    human_candidates = [issue for issue in candidates if is_human(issue, config)]
    if human_candidates:
        return {
            "action": "suppressed_human",
            "issue_ids": sorted(int(issue["id"]) for issue in human_candidates),
            "fingerprint": fingerprint,
        }

    candidate_ids = sorted(int(issue["id"]) for issue in candidates)
    result = create_new(
        client=client,
        config=config,
        setup=setup,
        payload=payload,
        finding=finding,
        fingerprint=fingerprint,
        candidate_ids=candidate_ids,
        dry_run=dry_run,
    )
    result["fingerprint"] = fingerprint
    return result


def summarize(results: list[dict[str, Any]], payload: dict[str, Any]) -> dict[str, Any]:
    counts = {
        "detected": len(payload["findings"]),
        "created": 0,
        "would_create": 0,
        "updated": 0,
        "reopened": 0,
        "suppressed_human": 0,
        "skipped": 0,
        "errors": 0,
        "duplicate_candidates": 0,
    }
    for result in results:
        action = result["action"]
        if action in counts:
            counts[action] += 1
        counts["duplicate_candidates"] += len(result.get("candidate_issue_ids", []))
    return {
        "repository": payload["repository"],
        "base_branch": payload["base_branch"],
        "target_branch": payload["target_branch"],
        "commit_sha": payload["commit_sha"],
        "reviewed_file_count": payload["reviewed_file_count"],
        **counts,
    }


def main() -> int:
    default_config = Path(__file__).resolve().parents[1] / "config" / "redmine.json"
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--config",
        default=str(default_config),
        help="Redmine JSON configuration",
    )
    parser.add_argument("--input", required=True, help="Review findings JSON")
    parser.add_argument("--dry-run", action="store_true", help="Do not write to Redmine")
    args = parser.parse_args()

    try:
        config = load_config(args.config)
        payload = load_json(args.input)
        validate_config(config)
        validate_findings_input(payload)
        client = RedmineClient.from_config(config)
        setup = resolve_setup(client, config)
    except ReviewFindingError as exc:
        print(
            json.dumps({"status": "error", "error": str(exc)}, ensure_ascii=False),
            file=sys.stderr,
        )
        return 1

    results: list[dict[str, Any]] = []
    for index, finding in enumerate(payload["findings"]):
        try:
            result = process_finding(
                client=client,
                config=config,
                setup=setup,
                payload=payload,
                finding=finding,
                dry_run=args.dry_run,
            )
        except ReviewFindingError as exc:
            result = {"action": "errors", "index": index, "error": str(exc)}
        result["index"] = index
        results.append(result)

    output = {
        "status": "partial_error" if any(r["action"] == "errors" for r in results) else "ok",
        "dry_run": args.dry_run,
        "warnings": setup.warnings,
        "summary": summarize(results, payload),
        "results": results,
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 1 if output["status"] == "partial_error" else 0


if __name__ == "__main__":
    raise SystemExit(main())
