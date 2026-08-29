"""Add finding artifacts, content versions, and diagram cache.

Revision ID: 0009_rich_finding_content
Revises: 0008_merge_remediation_into_description
"""

from alembic import op
import sqlalchemy as sa
import hashlib
import uuid

revision = "0009_rich_finding_content"
down_revision = "0008_merge_remediation_into_description"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table("finding_artifacts", sa.Column("id", sa.String(36), primary_key=True), sa.Column("sequence", sa.Integer(), nullable=False, unique=True), sa.Column("finding_id", sa.String(36), sa.ForeignKey("findings.id"), nullable=False), sa.Column("blob", sa.LargeBinary(), nullable=False), sa.Column("mime_type", sa.String(64), nullable=False), sa.Column("filename", sa.String(512), nullable=False), sa.Column("size_bytes", sa.Integer(), nullable=False), sa.Column("sha256", sa.String(64), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.Column("deleted_at", sa.DateTime(timezone=True)))
    op.create_index("ix_finding_artifacts_finding_id", "finding_artifacts", ["finding_id"])
    op.create_table("finding_content_versions", sa.Column("id", sa.String(36), primary_key=True), sa.Column("finding_id", sa.String(36), sa.ForeignKey("findings.id"), nullable=False), sa.Column("version", sa.Integer(), nullable=False), sa.Column("content_markdown", sa.Text(), nullable=False), sa.Column("content_sha256", sa.String(64), nullable=False), sa.Column("created_by", sa.String(255), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.UniqueConstraint("finding_id", "version", name="uq_content_version"))
    op.create_index("ix_finding_content_versions_finding_id", "finding_content_versions", ["finding_id"])
    op.create_table("finding_artifact_references", sa.Column("id", sa.String(36), primary_key=True), sa.Column("content_version_id", sa.String(36), sa.ForeignKey("finding_content_versions.id"), nullable=False), sa.Column("artifact_id", sa.String(36), sa.ForeignKey("finding_artifacts.id"), nullable=False), sa.UniqueConstraint("content_version_id", "artifact_id", name="uq_content_artifact_reference"))
    op.create_table("diagram_render_cache", sa.Column("id", sa.String(36), primary_key=True), sa.Column("engine", sa.String(32), nullable=False), sa.Column("source_sha256", sa.String(64), nullable=False), sa.Column("output_format", sa.String(16), nullable=False), sa.Column("svg", sa.LargeBinary(), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.UniqueConstraint("engine", "source_sha256", "output_format", name="uq_diagram_render_cache"))
    bind = op.get_bind()
    rows = bind.execute(sa.text("SELECT id, description_markdown, created_by, created_at FROM findings")).mappings()
    for row in rows:
        content = row["description_markdown"]
        bind.execute(sa.text("INSERT INTO finding_content_versions (id, finding_id, version, content_markdown, content_sha256, created_by, created_at) VALUES (:id, :finding_id, 1, :content, :sha, :created_by, :created_at)"), {"id": str(uuid.uuid4()), "finding_id": row["id"], "content": content, "sha": hashlib.sha256(content.encode()).hexdigest(), "created_by": row["created_by"], "created_at": row["created_at"]})


def downgrade() -> None:
    op.drop_table("diagram_render_cache")
    op.drop_table("finding_artifact_references")
    op.drop_table("finding_content_versions")
    op.drop_table("finding_artifacts")
