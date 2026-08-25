from __future__ import annotations

from collections import Counter
from datetime import datetime
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .config import get_settings
from .domain import (
    HUMAN_SOURCE,
    DomainError,
    context_hash,
    infer_language,
    make_fingerprint,
    rediscovery_action,
    stored_code_excerpt,
)
from .models import (
    AuditEvent,
    Finding,
    FindingOccurrence,
    FindingRelation,
    Repository,
    ReviewRun,
    ReviewRunResult,
)
from .schemas import FindingInput, ManualFindingInput, ReconciliationInput


class ServiceError(RuntimeError):
    pass


def get_or_create_repository(session: Session, name: str) -> Repository:
    repository = session.scalar(select(Repository).where(Repository.name == name))
    if repository:
        return repository
    repository = Repository(name=name, display_name=name)
    session.add(repository)
    session.flush()
    return repository


def next_sequence(session: Session) -> int:
    return int(session.scalar(select(func.max(Finding.sequence))) or 0) + 1


def exact_finding(
    session: Session, repository_id: str, fingerprint: str
) -> Finding | None:
    return session.scalar(
        select(Finding).where(
            Finding.repository_id == repository_id,
            Finding.fingerprint == fingerprint,
        )
    )


def duplicate_candidates(
    session: Session,
    repository_id: str,
    finding: FindingInput,
) -> list[Finding]:
    return list(
        session.scalars(
            select(Finding)
            .where(
                Finding.repository_id == repository_id,
                Finding.rule_id == finding.rule_id,
                Finding.file_path == finding.file_path,
                Finding.symbol == (finding.symbol or "<global>"),
            )
            .order_by(Finding.sequence)
        )
    )


def duplicate_target(session: Session, finding_id: str) -> Finding | None:
    relation = session.scalar(
        select(FindingRelation).where(
            FindingRelation.source_finding_id == finding_id,
            FindingRelation.relation_type == "duplicate_of",
        )
    )
    return session.get(Finding, relation.target_finding_id) if relation else None


def resolve_update_target(
    session: Session, finding: Finding, max_depth: int = 3
) -> Finding | None:
    current = finding
    visited = {finding.id}
    for _ in range(max_depth):
        if current.status != "重複":
            return current
        target = duplicate_target(session, current.id)
        if not target or target.id in visited:
            return None
        visited.add(target.id)
        current = target
    return None


def prepared_code(finding: FindingInput) -> tuple[str, str]:
    settings = get_settings()
    return (
        stored_code_excerpt(
            finding.code_context,
            settings.code_excerpt_max_lines,
            settings.code_excerpt_max_bytes,
        ),
        infer_language(finding.file_path, finding.code_language),
    )


def evaluate_finding(
    session: Session,
    repository: Repository | None,
    payload: ReconciliationInput,
    finding: FindingInput,
) -> dict[str, Any]:
    fingerprint = make_fingerprint(payload.repository, finding.model_dump())
    if repository is not None:
        exact = exact_finding(session, repository.id, fingerprint)
        if exact:
            if exact.review_source == HUMAN_SOURCE:
                return {
                    "action": "suppressed_human",
                    "finding_id": exact.id,
                    "display_id": exact.display_id,
                    "fingerprint": fingerprint,
                }
            target = resolve_update_target(session, exact)
            if target is None:
                return {
                    "action": "skipped",
                    "finding_id": exact.id,
                    "display_id": exact.display_id,
                    "fingerprint": fingerprint,
                    "reason": "重複元を特定できないか循環しています",
                }
            action = rediscovery_action(target.status)["action"]
            return {
                "action": "would_reopen" if action == "reopened" else "would_update",
                "finding_id": target.id,
                "display_id": target.display_id,
                "fingerprint": fingerprint,
            }

        candidates = duplicate_candidates(session, repository.id, finding)
        humans = [item for item in candidates if item.review_source == HUMAN_SOURCE]
        if humans:
            return {
                "action": "suppressed_human",
                "finding_ids": [item.id for item in humans],
                "display_ids": [item.display_id for item in humans],
                "fingerprint": fingerprint,
            }
        candidate_ids = [item.id for item in candidates]
        candidate_display_ids = [item.display_id for item in candidates]
    else:
        candidate_ids = []
        candidate_display_ids = []

    return {
        "action": "would_create",
        "fingerprint": fingerprint,
        "candidate_finding_ids": candidate_ids,
        "candidate_display_ids": candidate_display_ids,
    }


def dry_run(session: Session, payload: ReconciliationInput) -> dict[str, Any]:
    repository = session.scalar(
        select(Repository).where(Repository.name == payload.repository)
    )
    results: list[dict[str, Any]] = []
    for index, finding in enumerate(payload.findings):
        try:
            result = evaluate_finding(session, repository, payload, finding)
        except (DomainError, ServiceError) as exc:
            result = {"action": "error", "error": str(exc)}
        result["index"] = index
        results.append(result)
    return build_response(payload, results, dry=True)


def add_audit(
    session: Session,
    *,
    finding_id: str | None,
    review_run_id: str | None,
    event_type: str,
    actor_type: str,
    actor_label: str,
    previous: dict[str, Any] | None = None,
    resulting: dict[str, Any] | None = None,
    reason: str | None = None,
) -> None:
    session.add(
        AuditEvent(
            finding_id=finding_id,
            review_run_id=review_run_id,
            event_type=event_type,
            actor_type=actor_type,
            actor_label=actor_label,
            previous_values=previous or {},
            resulting_values=resulting or {},
            reason=reason,
        )
    )


def add_occurrence(
    session: Session,
    finding: Finding,
    run: ReviewRun,
    payload: ReconciliationInput,
    item: FindingInput,
) -> None:
    session.add(
        FindingOccurrence(
            finding_id=finding.id,
            review_run_id=run.id,
            commit_sha=payload.commit_sha,
            line_number=item.line_number,
            detected_at=payload.detected_at,
            code_context_hash=context_hash(item.code_context),
        )
    )


def create_finding(
    session: Session,
    repository: Repository,
    run: ReviewRun,
    payload: ReconciliationInput,
    item: FindingInput,
    fingerprint: str,
    candidates: list[Finding],
) -> dict[str, Any]:
    code_excerpt, code_language = prepared_code(item)
    finding = Finding(
        sequence=next_sequence(session),
        repository_id=repository.id,
        title=item.title,
        description_markdown=item.description,
        remediation_markdown=item.remediation,
        severity=item.severity,
        category=item.category,
        rule_id=item.rule_id,
        file_path=item.file_path,
        symbol=item.symbol or "<global>",
        line_number=item.line_number,
        fingerprint=fingerprint,
        status="新規",
        review_source=payload.review_source,
        code_excerpt=code_excerpt,
        code_language=code_language,
        first_detected_at=payload.detected_at,
        last_detected_at=payload.detected_at,
        last_detected_commit=payload.commit_sha,
        detection_count=1,
        recurrence_count=0,
        ai_confidence=item.ai_confidence,
        created_by="automation",
        updated_by="automation",
    )
    session.add(finding)
    session.flush()
    add_occurrence(session, finding, run, payload, item)
    add_audit(
        session,
        finding_id=finding.id,
        review_run_id=run.id,
        event_type="created",
        actor_type="automation",
        actor_label=payload.review_source,
        resulting={"status": finding.status},
    )
    for candidate in candidates:
        session.add(
            FindingRelation(
                source_finding_id=finding.id,
                target_finding_id=candidate.id,
                relation_type="duplicate_candidate",
                created_by="automation",
            )
        )
    return {
        "action": "created",
        "finding_id": finding.id,
        "display_id": finding.display_id,
        "fingerprint": fingerprint,
        "candidate_finding_ids": [item.id for item in candidates],
    }


def update_finding(
    session: Session,
    finding: Finding,
    run: ReviewRun,
    payload: ReconciliationInput,
    item: FindingInput,
    fingerprint: str,
) -> dict[str, Any]:
    action = rediscovery_action(finding.status)
    previous = {
        "status": finding.status,
        "detection_count": finding.detection_count,
        "recurrence_count": finding.recurrence_count,
    }
    code_excerpt, code_language = prepared_code(item)
    finding.last_detected_at = payload.detected_at
    finding.last_detected_commit = payload.commit_sha
    finding.line_number = item.line_number
    finding.code_excerpt = code_excerpt
    finding.code_language = code_language
    finding.updated_by = "automation"
    if action.get("increment_detection"):
        finding.detection_count += 1
    if action.get("increment_recurrence"):
        finding.recurrence_count += 1
    if action.get("status"):
        finding.status = action["status"]
    add_occurrence(session, finding, run, payload, item)
    add_audit(
        session,
        finding_id=finding.id,
        review_run_id=run.id,
        event_type=action["action"],
        actor_type="automation",
        actor_label=payload.review_source,
        previous=previous,
        resulting={
            "status": finding.status,
            "detection_count": finding.detection_count,
            "recurrence_count": finding.recurrence_count,
        },
        reason="同じ指摘を再検出しました",
    )
    return {
        "action": action["action"],
        "finding_id": finding.id,
        "display_id": finding.display_id,
        "fingerprint": fingerprint,
    }


def apply_one(
    session: Session,
    repository: Repository,
    run: ReviewRun,
    payload: ReconciliationInput,
    item: FindingInput,
) -> dict[str, Any]:
    fingerprint = make_fingerprint(payload.repository, item.model_dump())
    exact = exact_finding(session, repository.id, fingerprint)
    if exact:
        if exact.review_source == HUMAN_SOURCE:
            return {
                "action": "suppressed_human",
                "finding_id": exact.id,
                "display_id": exact.display_id,
                "fingerprint": fingerprint,
            }
        target = resolve_update_target(session, exact)
        if target is None:
            return {
                "action": "skipped",
                "finding_id": exact.id,
                "display_id": exact.display_id,
                "fingerprint": fingerprint,
                "reason": "重複元を特定できないか循環しています",
            }
        return update_finding(session, target, run, payload, item, fingerprint)

    candidates = duplicate_candidates(session, repository.id, item)
    humans = [candidate for candidate in candidates if candidate.review_source == HUMAN_SOURCE]
    if humans:
        return {
            "action": "suppressed_human",
            "finding_ids": [candidate.id for candidate in humans],
            "display_ids": [candidate.display_id for candidate in humans],
            "fingerprint": fingerprint,
        }
    return create_finding(
        session, repository, run, payload, item, fingerprint, candidates
    )


def apply_reconciliation(
    session_factory,
    payload: ReconciliationInput,
    idempotency_key: str,
) -> dict[str, Any]:
    with session_factory() as session:
        with session.begin():
            existing = session.scalar(
                select(ReviewRun).where(ReviewRun.idempotency_key == idempotency_key)
            )
            if existing:
                stored = stored_run_response(session, existing)
            else:
                stored = None
        if stored is not None:
            return stored
        with session.begin():
            repository = get_or_create_repository(session, payload.repository)
            run = ReviewRun(
                repository_id=repository.id,
                idempotency_key=idempotency_key,
                base_branch=payload.base_branch,
                target_branch=payload.target_branch,
                commit_sha=payload.commit_sha,
                review_source=payload.review_source,
                detected_at=payload.detected_at,
                reviewed_file_count=payload.reviewed_file_count,
            )
            session.add(run)
            session.flush()
            run_id = run.id
            repository_id = repository.id

    results: list[dict[str, Any]] = []
    for index, item in enumerate(payload.findings):
        with session_factory() as item_session:
            try:
                with item_session.begin():
                    run = item_session.get(ReviewRun, run_id)
                    repository = item_session.get(Repository, repository_id)
                    assert run is not None and repository is not None
                    result = apply_one(item_session, repository, run, payload, item)
                    item_session.add(
                        ReviewRunResult(
                            review_run_id=run_id,
                            finding_index=index,
                            action=result["action"],
                            finding_id=result.get("finding_id"),
                            fingerprint=result.get("fingerprint"),
                            details=result,
                        )
                    )
            except (DomainError, ServiceError, IntegrityError) as exc:
                item_session.rollback()
                result = {"action": "error", "error": str(exc)}
                with item_session.begin():
                    item_session.add(
                        ReviewRunResult(
                            review_run_id=run_id,
                            finding_index=index,
                            action="error",
                            details=result,
                        )
                    )
        result["index"] = index
        results.append(result)

    response = build_response(payload, results, dry=False, review_run_id=run_id)
    with session_factory() as session:
        with session.begin():
            run = session.get(ReviewRun, run_id)
            assert run is not None
            run.status = response["status"]
            run.summary = response["summary"]
    return response


def stored_run_response(session: Session, run: ReviewRun) -> dict[str, Any]:
    results = list(
        session.scalars(
            select(ReviewRunResult)
            .where(ReviewRunResult.review_run_id == run.id)
            .order_by(ReviewRunResult.finding_index)
        )
    )
    return {
        "status": run.status,
        "dry_run": False,
        "review_run_id": run.id,
        "summary": run.summary,
        "results": [
            {**result.details, "index": result.finding_index} for result in results
        ],
    }


def build_response(
    payload: ReconciliationInput,
    results: list[dict[str, Any]],
    *,
    dry: bool,
    review_run_id: str | None = None,
) -> dict[str, Any]:
    counts = Counter(result["action"] for result in results)
    error_count = counts["error"]
    summary = {
        "repository": payload.repository,
        "base_branch": payload.base_branch,
        "target_branch": payload.target_branch,
        "commit_sha": payload.commit_sha,
        "reviewed_file_count": payload.reviewed_file_count,
        "detected": len(payload.findings),
        "created": counts["created"],
        "would_create": counts["would_create"],
        "updated": counts["updated"],
        "would_update": counts["would_update"],
        "reopened": counts["reopened"],
        "would_reopen": counts["would_reopen"],
        "suppressed_human": counts["suppressed_human"],
        "skipped": counts["skipped"],
        "errors": error_count,
        "duplicate_candidates": sum(
            len(result.get("candidate_finding_ids", [])) for result in results
        ),
    }
    return {
        "status": "partial_error" if error_count else "ok",
        "dry_run": dry,
        "review_run_id": review_run_id,
        "summary": summary,
        "results": results,
    }


def create_manual_finding(
    session: Session, data: ManualFindingInput
) -> Finding:
    repository = get_or_create_repository(session, data.repository)
    candidates = duplicate_candidates(session, repository.id, data)
    detected_at = data.detected_at or datetime.now().astimezone()
    code_excerpt, code_language = prepared_code(data)
    finding = Finding(
        sequence=next_sequence(session),
        repository_id=repository.id,
        title=data.title,
        description_markdown=data.description,
        remediation_markdown=data.remediation,
        severity=data.severity,
        category=data.category,
        rule_id=data.rule_id,
        file_path=data.file_path,
        symbol=data.symbol or "<global>",
        line_number=data.line_number,
        fingerprint=None,
        status="新規",
        review_source=HUMAN_SOURCE,
        code_excerpt=code_excerpt,
        code_language=code_language,
        first_detected_at=detected_at,
        last_detected_at=detected_at,
        last_detected_commit="<manual>",
        detection_count=1,
        recurrence_count=0,
        ai_confidence=None,
        created_by=HUMAN_SOURCE,
        updated_by=HUMAN_SOURCE,
    )
    session.add(finding)
    session.flush()
    add_audit(
        session,
        finding_id=finding.id,
        review_run_id=None,
        event_type="created",
        actor_type="human",
        actor_label=HUMAN_SOURCE,
        resulting={"status": finding.status},
    )
    for candidate in candidates:
        session.add(
            FindingRelation(
                source_finding_id=finding.id,
                target_finding_id=candidate.id,
                relation_type="duplicate_candidate",
                created_by=HUMAN_SOURCE,
            )
        )
    return finding
