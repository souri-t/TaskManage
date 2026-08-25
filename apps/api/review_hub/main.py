from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import func, or_, select, text
from sqlalchemy.orm import Session

from .database import SessionLocal, get_session, write_lock
from .domain import ALLOWED_TRANSITIONS, HUMAN_SOURCE
from .models import (
    AuditEvent,
    Finding,
    FindingRelation,
    Repository,
    ReviewRun,
    ReviewRunResult,
)
from .schemas import (
    DuplicateInput,
    ManualFindingInput,
    ReconciliationInput,
    TransitionInput,
)
from .service import (
    add_audit,
    apply_reconciliation,
    create_manual_finding,
    dry_run,
)


app = FastAPI(
    title="Review Hub API",
    version="0.1.0",
    description="Codex review finding reconciliation and tracking",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:8080", "http://localhost:8080"],
    allow_methods=["*"],
    allow_headers=["*"],
)

DBSession = Annotated[Session, Depends(get_session)]


def finding_dict(finding: Finding, repository_name: str) -> dict:
    return {
        "id": finding.id,
        "display_id": finding.display_id,
        "repository": repository_name,
        "title": finding.title,
        "description_markdown": finding.description_markdown,
        "remediation_markdown": finding.remediation_markdown,
        "severity": finding.severity,
        "category": finding.category,
        "rule_id": finding.rule_id,
        "file_path": finding.file_path,
        "symbol": finding.symbol,
        "line_number": finding.line_number,
        "fingerprint": finding.fingerprint,
        "status": finding.status,
        "review_source": finding.review_source,
        "code_excerpt": finding.code_excerpt,
        "code_language": finding.code_language,
        "first_detected_at": finding.first_detected_at,
        "last_detected_at": finding.last_detected_at,
        "last_detected_commit": finding.last_detected_commit,
        "detection_count": finding.detection_count,
        "recurrence_count": finding.recurrence_count,
        "ai_confidence": finding.ai_confidence,
    }


@app.get("/healthz")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/readyz")
def ready(session: DBSession) -> dict[str, str]:
    try:
        session.execute(text("SELECT 1"))
        integrity = session.execute(text("PRAGMA quick_check")).scalar_one()
    except Exception as exc:
        raise HTTPException(status_code=503, detail="database unavailable") from exc
    if integrity != "ok":
        raise HTTPException(status_code=503, detail="database integrity check failed")
    return {"status": "ok", "database": "sqlite"}


@app.post("/api/v1/reconciliations/dry-run")
def reconciliation_dry_run(
    payload: ReconciliationInput, session: DBSession
) -> dict:
    return dry_run(session, payload)


@app.post("/api/v1/reconciliations")
def reconciliation_apply(
    payload: ReconciliationInput,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> dict:
    if not idempotency_key:
        raise HTTPException(status_code=400, detail="Idempotency-Key header is required")
    if len(idempotency_key) > 512:
        raise HTTPException(status_code=400, detail="Idempotency-Key is too long")
    with write_lock:
        return apply_reconciliation(SessionLocal, payload, idempotency_key)


@app.get("/api/v1/findings")
def list_findings(
    session: DBSession,
    repository: str | None = None,
    status: str | None = None,
    severity: str | None = None,
    review_source: str | None = None,
    recurring: bool | None = None,
    search: str | None = None,
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=25, ge=1, le=100),
) -> dict:
    conditions = []
    if repository:
        conditions.append(Repository.name == repository)
    if status:
        conditions.append(Finding.status == status)
    if severity:
        conditions.append(Finding.severity == severity)
    if review_source:
        conditions.append(Finding.review_source == review_source)
    if recurring is True:
        conditions.append(Finding.recurrence_count > 0)
    if search:
        pattern = f"%{search}%"
        conditions.append(
            or_(
                Finding.title.like(pattern),
                Finding.file_path.like(pattern),
                Finding.rule_id.like(pattern),
                Finding.symbol.like(pattern),
            )
        )
    base = select(Finding, Repository.name).join(Repository)
    count_query = select(func.count(Finding.id)).join(Repository)
    if conditions:
        base = base.where(*conditions)
        count_query = count_query.where(*conditions)
    total = int(session.scalar(count_query) or 0)
    rows = session.execute(
        base.order_by(Finding.last_detected_at.desc())
        .offset((page - 1) * per_page)
        .limit(per_page)
    ).all()
    return {
        "items": [finding_dict(finding, repository_name) for finding, repository_name in rows],
        "page": page,
        "per_page": per_page,
        "total": total,
    }


@app.get("/api/v1/repositories")
def list_repositories(session: DBSession) -> dict:
    rows = session.execute(
        select(
            Repository.id,
            Repository.name,
            Repository.display_name,
            func.count(Finding.id).label("finding_count"),
        )
        .outerjoin(Finding, Finding.repository_id == Repository.id)
        .group_by(Repository.id, Repository.name, Repository.display_name)
        .order_by(Repository.name)
    ).all()
    return {
        "items": [
            {
                "id": repository_id,
                "name": name,
                "display_name": display_name,
                "finding_count": finding_count,
            }
            for repository_id, name, display_name, finding_count in rows
        ]
    }


def get_finding_or_404(session: Session, finding_id: str) -> Finding:
    finding = session.get(Finding, finding_id)
    if not finding:
        raise HTTPException(status_code=404, detail="finding not found")
    return finding


@app.get("/api/v1/findings/{finding_id}")
def get_finding(finding_id: str, session: DBSession) -> dict:
    finding = get_finding_or_404(session, finding_id)
    repository = session.get(Repository, finding.repository_id)
    assert repository is not None
    return finding_dict(finding, repository.name)


@app.get("/api/v1/findings/{finding_id}/timeline")
def finding_timeline(finding_id: str, session: DBSession) -> dict:
    get_finding_or_404(session, finding_id)
    events = list(
        session.scalars(
            select(AuditEvent)
            .where(AuditEvent.finding_id == finding_id)
            .order_by(AuditEvent.created_at.desc())
        )
    )
    return {
        "items": [
            {
                "id": event.id,
                "event_type": event.event_type,
                "actor_type": event.actor_type,
                "actor_label": event.actor_label,
                "previous_values": event.previous_values,
                "resulting_values": event.resulting_values,
                "reason": event.reason,
                "created_at": event.created_at,
            }
            for event in events
        ]
    }


@app.post("/api/v1/findings", status_code=201)
def create_human_finding(data: ManualFindingInput) -> dict:
    with write_lock, SessionLocal() as session, session.begin():
        finding = create_manual_finding(session, data)
        repository = session.get(Repository, finding.repository_id)
        assert repository is not None
        result = finding_dict(finding, repository.name)
    return result


@app.post("/api/v1/findings/{finding_id}/transitions")
def transition_finding(
    finding_id: str, data: TransitionInput
) -> dict:
    with write_lock, SessionLocal() as session, session.begin():
        finding = get_finding_or_404(session, finding_id)
        if data.status == "重複":
            raise HTTPException(
                status_code=409, detail="重複設定にはduplicate endpointを使用してください"
            )
        allowed = ALLOWED_TRANSITIONS.get(finding.status, set())
        if data.status not in allowed:
            raise HTTPException(
                status_code=409,
                detail=f"{finding.status}から{data.status}へは遷移できません",
            )
        previous = finding.status
        finding.status = data.status
        finding.updated_by = HUMAN_SOURCE
        add_audit(
            session,
            finding_id=finding.id,
            review_run_id=None,
            event_type="status_changed",
            actor_type="human",
            actor_label=HUMAN_SOURCE,
            previous={"status": previous},
            resulting={"status": data.status},
            reason=data.reason,
        )
        repository = session.get(Repository, finding.repository_id)
        assert repository is not None
        result = finding_dict(finding, repository.name)
    return result


def would_create_cycle(
    session: Session, source_id: str, target_id: str
) -> bool:
    current = target_id
    visited = {source_id}
    for _ in range(100):
        if current in visited:
            return True
        visited.add(current)
        relation = session.scalar(
            select(FindingRelation).where(
                FindingRelation.source_finding_id == current,
                FindingRelation.relation_type == "duplicate_of",
            )
        )
        if not relation:
            return False
        current = relation.target_finding_id
    return True


@app.post("/api/v1/findings/{finding_id}/duplicate")
def mark_duplicate(finding_id: str, data: DuplicateInput) -> dict:
    with write_lock, SessionLocal() as session, session.begin():
        source = get_finding_or_404(session, finding_id)
        target = get_finding_or_404(session, data.target_finding_id)
        if source.id == target.id or source.repository_id != target.repository_id:
            raise HTTPException(status_code=409, detail="不正な重複元です")
        if would_create_cycle(session, source.id, target.id):
            raise HTTPException(status_code=409, detail="重複関係が循環します")
        previous_relation = session.scalar(
            select(FindingRelation).where(
                FindingRelation.source_finding_id == source.id,
                FindingRelation.relation_type == "duplicate_of",
            )
        )
        if previous_relation:
            session.delete(previous_relation)
        session.add(
            FindingRelation(
                source_finding_id=source.id,
                target_finding_id=target.id,
                relation_type="duplicate_of",
                created_by=HUMAN_SOURCE,
            )
        )
        previous_status = source.status
        source.status = "重複"
        source.updated_by = HUMAN_SOURCE
        add_audit(
            session,
            finding_id=source.id,
            review_run_id=None,
            event_type="marked_duplicate",
            actor_type="human",
            actor_label=HUMAN_SOURCE,
            previous={"status": previous_status},
            resulting={"status": "重複", "target_finding_id": target.id},
            reason=data.reason,
        )
    return {"status": "ok", "source_finding_id": source.id, "target_finding_id": target.id}


@app.get("/api/v1/review-runs")
def list_review_runs(
    session: DBSession,
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=25, ge=1, le=100),
) -> dict:
    total = int(session.scalar(select(func.count(ReviewRun.id))) or 0)
    runs = list(
        session.scalars(
            select(ReviewRun)
            .order_by(ReviewRun.created_at.desc())
            .offset((page - 1) * per_page)
            .limit(per_page)
        )
    )
    repository_ids = {run.repository_id for run in runs}
    repositories = {
        item.id: item.name
        for item in session.scalars(
            select(Repository).where(Repository.id.in_(repository_ids))
        )
    } if repository_ids else {}
    return {
        "items": [
            {
                "id": run.id,
                "repository": repositories.get(run.repository_id, ""),
                "base_branch": run.base_branch,
                "target_branch": run.target_branch,
                "commit_sha": run.commit_sha,
                "review_source": run.review_source,
                "detected_at": run.detected_at,
                "reviewed_file_count": run.reviewed_file_count,
                "status": run.status,
                "summary": run.summary,
            }
            for run in runs
        ],
        "page": page,
        "per_page": per_page,
        "total": total,
    }


@app.get("/api/v1/review-runs/{run_id}")
def get_review_run(run_id: str, session: DBSession) -> dict:
    run = session.get(ReviewRun, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="review run not found")
    results = list(
        session.scalars(
            select(ReviewRunResult)
            .where(ReviewRunResult.review_run_id == run.id)
            .order_by(ReviewRunResult.finding_index)
        )
    )
    return {
        "id": run.id,
        "status": run.status,
        "summary": run.summary,
        "results": [{**item.details, "index": item.finding_index} for item in results],
    }


@app.get("/api/v1/dashboard/summary")
def dashboard_summary(session: DBSession) -> dict:
    open_statuses = ("新規", "確認中", "対応対象", "対応中", "修正確認中", "保留")
    counts = {
        "open": int(
            session.scalar(
                select(func.count(Finding.id)).where(Finding.status.in_(open_statuses))
            )
            or 0
        ),
        "critical_high": int(
            session.scalar(
                select(func.count(Finding.id)).where(
                    Finding.status.in_(open_statuses),
                    Finding.severity.in_(("Critical", "High")),
                )
            )
            or 0
        ),
        "recurring": int(
            session.scalar(
                select(func.count(Finding.id)).where(Finding.recurrence_count > 0)
            )
            or 0
        ),
        "verification": int(
            session.scalar(
                select(func.count(Finding.id)).where(Finding.status == "修正確認中")
            )
            or 0
        ),
    }
    status_rows = session.execute(
        select(Finding.status, func.count(Finding.id)).group_by(Finding.status)
    ).all()
    return {
        **counts,
        "by_status": {status: count for status, count in status_rows},
    }
