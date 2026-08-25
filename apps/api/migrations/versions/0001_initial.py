"""Create the Review Hub schema."""

from alembic import op

from review_hub.database import Base
from review_hub import models  # noqa: F401


revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    Base.metadata.create_all(
        bind=op.get_bind(),
        tables=[
            table
            for table in Base.metadata.sorted_tables
            if table.name != "review_guidelines"
        ],
    )


def downgrade() -> None:
    Base.metadata.drop_all(bind=op.get_bind())
