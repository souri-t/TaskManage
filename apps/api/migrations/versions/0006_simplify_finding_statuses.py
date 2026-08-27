"""Simplify finding statuses and add a non-remediation reason.

Revision ID: 0006_simplify_finding_statuses
Revises: 0005_rename_planned_status
"""

from alembic import op
import sqlalchemy as sa


revision = "0006_simplify_finding_statuses"
down_revision = "0005_rename_planned_status"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    columns = {column["name"] for column in sa.inspect(bind).get_columns("findings")}
    if "non_remediation_reason" not in columns:
        op.add_column("findings", sa.Column("non_remediation_reason", sa.String(length=64)))
    op.execute("UPDATE findings SET status = '新規' WHERE status = '確認中'")
    op.execute("UPDATE findings SET status = '修正後確認中' WHERE status = '修正確認中'")
    op.execute("UPDATE findings SET status = '修正完了' WHERE status = '修正済み'")
    op.execute("UPDATE findings SET status = '対応不要', non_remediation_reason = 'リスク受容' WHERE status = 'リスク受容'")
    op.execute("UPDATE findings SET status = '対応不要', non_remediation_reason = '指摘の誤り（取下げ）' WHERE status = '取下げ'")


def downgrade() -> None:
    op.execute("UPDATE findings SET status = '確認中' WHERE status = '新規'")
    op.execute("UPDATE findings SET status = '修正確認中' WHERE status = '修正後確認中'")
    op.execute("UPDATE findings SET status = '修正済み' WHERE status = '修正完了'")
    op.execute("UPDATE findings SET status = 'リスク受容' WHERE status = '対応不要' AND non_remediation_reason = 'リスク受容'")
    op.execute("UPDATE findings SET status = '取下げ' WHERE status = '対応不要' AND non_remediation_reason = '指摘の誤り（取下げ）'")
    op.drop_column("findings", "non_remediation_reason")
