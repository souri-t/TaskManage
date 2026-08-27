from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .domain import AUTOMATION_SOURCES, SEVERITIES, STATUSES, normalize_file_path


class FindingInput(BaseModel):
    title: str = Field(min_length=1, max_length=500)
    description: str = Field(min_length=1, max_length=100_000)
    remediation: str = Field(min_length=1, max_length=100_000)
    severity: Literal["Critical", "High", "Medium", "Low"]
    category: str = Field(min_length=1, max_length=128)
    rule_id: str = Field(min_length=1, max_length=255)
    file_path: str = Field(min_length=1, max_length=1000)
    symbol: str = Field(min_length=1, max_length=500)
    line_number: int | None = Field(default=None, ge=1)
    code_context: str = Field(min_length=1)
    code_language: str | None = Field(default=None, max_length=64)
    ai_confidence: int | None = Field(default=None, ge=0, le=100)

    @field_validator("file_path")
    @classmethod
    def valid_path(cls, value: str) -> str:
        return normalize_file_path(value)

    @field_validator("code_context")
    @classmethod
    def bounded_context(cls, value: str) -> str:
        if len(value.encode("utf-8")) > 1024 * 1024:
            raise ValueError("code_contextは1MiB以下にしてください")
        return value


class ReconciliationInput(BaseModel):
    repository: str = Field(min_length=1, max_length=255)
    base_branch: str = Field(min_length=1, max_length=255)
    target_branch: str = Field(min_length=1, max_length=255)
    commit_sha: str = Field(min_length=1, max_length=128)
    reviewed_file_count: int = Field(ge=0)
    review_source: Literal["Codex", "静的解析"]
    review_guideline_id: str = Field(min_length=4, max_length=32)
    detected_at: datetime
    findings: list[FindingInput]

    @model_validator(mode="after")
    def confidence_for_codex(self) -> ReconciliationInput:
        if self.review_source == "Codex":
            missing = [
                index
                for index, finding in enumerate(self.findings)
                if finding.ai_confidence is None
            ]
            if missing:
                raise ValueError(
                    "Codexレビューではai_confidenceが必須です: "
                    + ", ".join(map(str, missing))
                )
        return self


class ManualFindingInput(FindingInput):
    repository: str = Field(min_length=1, max_length=255)
    category: str | None = Field(default=None, min_length=1, max_length=128)
    rule_id: str | None = Field(default=None, min_length=1, max_length=255)
    detected_at: datetime | None = None


class TransitionInput(BaseModel):
    status: str
    reason: str | None = Field(default=None, max_length=5000)
    non_remediation_reason: Literal[
        "リスク受容",
        "指摘の誤り（取下げ）",
        "要件外",
        "他の修正で解消済み",
        "今回対応しない",
        "その他",
    ] | None = None

    @field_validator("status")
    @classmethod
    def known_status(cls, value: str) -> str:
        if value not in STATUSES:
            raise ValueError("未知のステータスです")
        return value

    @model_validator(mode="after")
    def reason_for_non_remediation(self) -> TransitionInput:
        if self.status == "対応不要" and self.non_remediation_reason is None:
            raise ValueError("対応不要の理由を選択してください")
        return self


class CodexFixRequestInput(BaseModel):
    note: str | None = Field(default=None, max_length=5000)

    @field_validator("note")
    @classmethod
    def normalize_note(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return value.strip() or None


class CodexFixCompletionInput(BaseModel):
    summary: str = Field(min_length=1, max_length=10_000)


class DuplicateInput(BaseModel):
    target_finding_id: str
    reason: str = Field(min_length=1, max_length=5000)


class ReviewGuidelineInput(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    content_markdown: str = Field(min_length=1, max_length=100_000)
    is_active: bool = True


class ReviewGuidelineUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    content_markdown: str | None = Field(default=None, min_length=1, max_length=100_000)
    is_active: bool | None = None

    @model_validator(mode="after")
    def has_change(self) -> ReviewGuidelineUpdate:
        if (
            self.title is None
            and self.content_markdown is None
            and self.is_active is None
        ):
            raise ValueError("更新する項目を指定してください")
        return self


class OrmModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class FindingSummary(OrmModel):
    id: str
    display_id: str
    repository: str
    title: str
    severity: str
    status: str
    review_source: str
    file_path: str
    symbol: str
    line_number: int | None
    recurrence_count: int
    last_detected_at: datetime


class FindingDetail(FindingSummary):
    description_markdown: str
    remediation_markdown: str
    category: str
    rule_id: str
    fingerprint: str | None
    code_excerpt: str | None
    code_language: str | None
    first_detected_at: datetime
    last_detected_commit: str
    detection_count: int
    ai_confidence: int | None


class ReconciliationResult(BaseModel):
    status: Literal["ok", "partial_error"]
    dry_run: bool
    review_run_id: str | None = None
    summary: dict[str, Any]
    results: list[dict[str, Any]]
