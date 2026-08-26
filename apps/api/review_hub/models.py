from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import (
    JSON,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def uuid_string() -> str:
    return str(uuid4())


def utcnow() -> datetime:
    return datetime.now().astimezone()


class Repository(Base):
    __tablename__ = "repositories"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_string)
    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )

    findings: Mapped[list[Finding]] = relationship(back_populates="repository")


class ReviewGuideline(Base):
    __tablename__ = "review_guidelines"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_string)
    sequence: Mapped[int] = mapped_column(Integer, unique=True, nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    content_markdown: Mapped[str] = mapped_column(Text, nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )

    @property
    def display_id(self) -> str:
        return f"RVG-{self.sequence:06d}"


class ReviewRun(Base):
    __tablename__ = "review_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_string)
    repository_id: Mapped[str] = mapped_column(
        ForeignKey("repositories.id"), nullable=False, index=True
    )
    idempotency_key: Mapped[str] = mapped_column(
        String(512), unique=True, nullable=False
    )
    base_branch: Mapped[str] = mapped_column(String(255), nullable=False)
    target_branch: Mapped[str] = mapped_column(String(255), nullable=False)
    commit_sha: Mapped[str] = mapped_column(String(128), nullable=False)
    review_source: Mapped[str] = mapped_column(String(32), nullable=False)
    detected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    reviewed_file_count: Mapped[int] = mapped_column(Integer, nullable=False)
    review_guideline_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    review_guideline_display_id: Mapped[str | None] = mapped_column(
        String(32), nullable=True
    )
    review_guideline_title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    review_guideline_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    review_guideline_markdown: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="running", nullable=False)
    summary: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )

    repository: Mapped[Repository] = relationship()
    results: Mapped[list[ReviewRunResult]] = relationship(
        back_populates="review_run", cascade="all, delete-orphan"
    )


class Finding(Base):
    __tablename__ = "findings"
    __table_args__ = (
        Index(
            "uq_findings_repository_fingerprint",
            "repository_id",
            "fingerprint",
            unique=True,
            sqlite_where=text("fingerprint IS NOT NULL"),
        ),
        Index(
            "ix_findings_duplicate_candidates",
            "repository_id",
            "rule_id",
            "file_path",
            "symbol",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_string)
    sequence: Mapped[int] = mapped_column(Integer, unique=True, nullable=False)
    repository_id: Mapped[str] = mapped_column(
        ForeignKey("repositories.id"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description_markdown: Mapped[str] = mapped_column(Text, nullable=False)
    remediation_markdown: Mapped[str] = mapped_column(Text, nullable=False)
    severity: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    category: Mapped[str] = mapped_column(String(128), nullable=False)
    rule_id: Mapped[str] = mapped_column(String(255), nullable=False)
    file_path: Mapped[str] = mapped_column(String(1000), nullable=False)
    symbol: Mapped[str] = mapped_column(String(500), nullable=False)
    line_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    fingerprint: Mapped[str | None] = mapped_column(String(64), nullable=True)
    fingerprint_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    review_source: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    code_excerpt: Mapped[str | None] = mapped_column(Text, nullable=True)
    code_language: Mapped[str | None] = mapped_column(String(64), nullable=True)
    first_detected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    last_detected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    last_detected_commit: Mapped[str] = mapped_column(String(128), nullable=False)
    detection_count: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    recurrence_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    ai_confidence: Mapped[int | None] = mapped_column(Integer, nullable=True)
    codex_fix_requested_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    codex_fix_request_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[str] = mapped_column(String(255), nullable=False)
    updated_by: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )

    repository: Mapped[Repository] = relationship(back_populates="findings")
    occurrences: Mapped[list[FindingOccurrence]] = relationship(
        back_populates="finding", cascade="all, delete-orphan"
    )

    @property
    def display_id(self) -> str:
        return f"FND-{self.sequence:06d}"


class ReviewRunResult(Base):
    __tablename__ = "review_run_results"
    __table_args__ = (UniqueConstraint("review_run_id", "finding_index"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_string)
    review_run_id: Mapped[str] = mapped_column(
        ForeignKey("review_runs.id", ondelete="CASCADE"), nullable=False
    )
    finding_index: Mapped[int] = mapped_column(Integer, nullable=False)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    finding_id: Mapped[str | None] = mapped_column(
        ForeignKey("findings.id"), nullable=True
    )
    fingerprint: Mapped[str | None] = mapped_column(String(64), nullable=True)
    details: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)

    review_run: Mapped[ReviewRun] = relationship(back_populates="results")


class FindingOccurrence(Base):
    __tablename__ = "finding_occurrences"
    __table_args__ = (
        UniqueConstraint("finding_id", "review_run_id", name="uq_occurrence_run"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_string)
    finding_id: Mapped[str] = mapped_column(
        ForeignKey("findings.id", ondelete="CASCADE"), nullable=False, index=True
    )
    review_run_id: Mapped[str] = mapped_column(
        ForeignKey("review_runs.id", ondelete="CASCADE"), nullable=False
    )
    commit_sha: Mapped[str] = mapped_column(String(128), nullable=False)
    line_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    detected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    code_context_hash: Mapped[str] = mapped_column(String(64), nullable=False)

    finding: Mapped[Finding] = relationship(back_populates="occurrences")


class FindingRelation(Base):
    __tablename__ = "finding_relations"
    __table_args__ = (
        UniqueConstraint(
            "source_finding_id", "target_finding_id", "relation_type"
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_string)
    source_finding_id: Mapped[str] = mapped_column(
        ForeignKey("findings.id", ondelete="CASCADE"), nullable=False, index=True
    )
    target_finding_id: Mapped[str] = mapped_column(
        ForeignKey("findings.id", ondelete="CASCADE"), nullable=False, index=True
    )
    relation_type: Mapped[str] = mapped_column(String(32), nullable=False)
    created_by: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_string)
    finding_id: Mapped[str | None] = mapped_column(
        ForeignKey("findings.id", ondelete="CASCADE"), nullable=True, index=True
    )
    review_run_id: Mapped[str | None] = mapped_column(
        ForeignKey("review_runs.id", ondelete="CASCADE"), nullable=True
    )
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    actor_type: Mapped[str] = mapped_column(String(32), nullable=False)
    actor_label: Mapped[str] = mapped_column(String(255), nullable=False)
    previous_values: Mapped[dict[str, Any]] = mapped_column(
        JSON, default=dict, nullable=False
    )
    resulting_values: Mapped[dict[str, Any]] = mapped_column(
        JSON, default=dict, nullable=False
    )
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
