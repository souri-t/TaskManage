"""Rename the planned response status.

Revision ID: 0005_rename_planned_status
Revises: 0004_optional_line_numbers
"""

from alembic import op


revision = "0005_rename_planned_status"
down_revision = "0004_optional_line_numbers"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("UPDATE findings SET status = '対応予定' WHERE status = '対応対象'")


def downgrade() -> None:
    op.execute("UPDATE findings SET status = '対応対象' WHERE status = '対応予定'")
