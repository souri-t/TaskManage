"""Merge optional remediation text into the finding Markdown body.

Revision ID: 0008_merge_remediation_into_description
Revises: 0007_rename_completion_statuses
"""

from alembic import op
import sqlalchemy as sa


revision = "0008_merge_remediation_into_description"
down_revision = "0007_rename_completion_statuses"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    columns = {column["name"] for column in sa.inspect(bind).get_columns("findings")}
    if "remediation_markdown" not in columns:
        return

    op.execute(
        """
        UPDATE findings
        SET description_markdown = description_markdown || '\n\n## 修正案\n\n' || remediation_markdown
        WHERE remediation_markdown IS NOT NULL
          AND trim(remediation_markdown) <> ''
        """
    )
    op.drop_column("findings", "remediation_markdown")


def downgrade() -> None:
    op.add_column("findings", sa.Column("remediation_markdown", sa.Text(), nullable=True))
