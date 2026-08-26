"""Add Codex fix-request fields to findings.

Revision ID: 0003_codex_fix_requests
Revises: 0002_review_guidelines
"""

from alembic import op
import sqlalchemy as sa


revision = "0003_codex_fix_requests"
down_revision = "0002_review_guidelines"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    existing_columns = {
        column["name"] for column in sa.inspect(bind).get_columns("findings")
    }
    if "codex_fix_requested_at" not in existing_columns:
        op.add_column(
            "findings", sa.Column("codex_fix_requested_at", sa.DateTime(timezone=True))
        )
    if "codex_fix_request_note" not in existing_columns:
        op.add_column("findings", sa.Column("codex_fix_request_note", sa.Text()))
    existing_indexes = {
        index["name"] for index in sa.inspect(bind).get_indexes("findings")
    }
    if "ix_findings_codex_fix_requested_at" not in existing_indexes:
        op.create_index(
            "ix_findings_codex_fix_requested_at",
            "findings",
            ["codex_fix_requested_at"],
        )


def downgrade() -> None:
    op.drop_index("ix_findings_codex_fix_requested_at", table_name="findings")
    op.drop_column("findings", "codex_fix_request_note")
    op.drop_column("findings", "codex_fix_requested_at")
