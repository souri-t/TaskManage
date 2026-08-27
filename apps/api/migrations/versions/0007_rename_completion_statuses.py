"""Rename completion statuses.

Revision ID: 0007_rename_completion_statuses
Revises: 0006_simplify_finding_statuses
"""

from alembic import op


revision = "0007_rename_completion_statuses"
down_revision = "0006_simplify_finding_statuses"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("UPDATE findings SET status = '__completion_rename__' WHERE status = '修正完了'")
    op.execute("UPDATE findings SET status = '修正完了' WHERE status = '修正後確認中'")
    op.execute("UPDATE findings SET status = 'クローズ' WHERE status = '__completion_rename__'")


def downgrade() -> None:
    op.execute("UPDATE findings SET status = '__completion_rename__' WHERE status = 'クローズ'")
    op.execute("UPDATE findings SET status = '修正後確認中' WHERE status = '修正完了'")
    op.execute("UPDATE findings SET status = '修正完了' WHERE status = '__completion_rename__'")
