"""Add review guidelines and the review-run snapshot.

Revision ID: 0002_review_guidelines
Revises: 0001_initial
"""

from alembic import op
import sqlalchemy as sa


revision = "0002_review_guidelines"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "review_guidelines",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("content_markdown", sa.Text(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("sequence"),
    )
    op.create_index(
        "ix_review_guidelines_is_active", "review_guidelines", ["is_active"]
    )
    existing_columns = {
        column["name"] for column in sa.inspect(op.get_bind()).get_columns("review_runs")
    }
    columns = (
        sa.Column("review_guideline_id", sa.String(length=36)),
        sa.Column("review_guideline_display_id", sa.String(length=32)),
        sa.Column("review_guideline_title", sa.String(length=255)),
        sa.Column("review_guideline_version", sa.Integer()),
        sa.Column("review_guideline_markdown", sa.Text()),
    )
    for column in columns:
        if column.name not in existing_columns:
            op.add_column("review_runs", column)


def downgrade() -> None:
    with op.batch_alter_table("review_runs") as batch:
        batch.drop_column("review_guideline_markdown")
        batch.drop_column("review_guideline_version")
        batch.drop_column("review_guideline_title")
        batch.drop_column("review_guideline_display_id")
        batch.drop_column("review_guideline_id")
    op.drop_index("ix_review_guidelines_is_active", table_name="review_guidelines")
    op.drop_table("review_guidelines")
