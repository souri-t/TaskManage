"""Make finding line numbers optional.

Revision ID: 0004_optional_line_numbers
Revises: 0003_codex_fix_requests
"""

from alembic import op
import sqlalchemy as sa


revision = "0004_optional_line_numbers"
down_revision = "0003_codex_fix_requests"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    finding_column = next(
        column for column in sa.inspect(bind).get_columns("findings") if column["name"] == "line_number"
    )
    occurrence_column = next(
        column for column in sa.inspect(bind).get_columns("finding_occurrences") if column["name"] == "line_number"
    )
    if not finding_column["nullable"] or not occurrence_column["nullable"]:
        with op.batch_alter_table("findings") as batch:
            if not finding_column["nullable"]:
                batch.alter_column("line_number", existing_type=sa.Integer(), nullable=True)
        with op.batch_alter_table("finding_occurrences") as batch:
            if not occurrence_column["nullable"]:
                batch.alter_column("line_number", existing_type=sa.Integer(), nullable=True)


def downgrade() -> None:
    with op.batch_alter_table("finding_occurrences") as batch:
        batch.alter_column("line_number", existing_type=sa.Integer(), nullable=False)
    with op.batch_alter_table("findings") as batch:
        batch.alter_column("line_number", existing_type=sa.Integer(), nullable=False)
