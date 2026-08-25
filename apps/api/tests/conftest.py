import os
import tempfile
from pathlib import Path


TEST_DIRECTORY = tempfile.TemporaryDirectory()
DATABASE_PATH = Path(TEST_DIRECTORY.name) / "test.db"
os.environ["REVIEW_HUB_DATABASE_URL"] = f"sqlite:///{DATABASE_PATH}"

import pytest  # noqa: E402

from review_hub.database import Base, SessionLocal, engine  # noqa: E402
from review_hub.models import ReviewGuideline  # noqa: E402


@pytest.fixture(autouse=True)
def clean_database():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    with SessionLocal() as session, session.begin():
        session.add(
            ReviewGuideline(
                sequence=1,
                title="テスト標準観点",
                content_markdown="- 正しさ\n- セキュリティ",
            )
        )
    yield
    Base.metadata.drop_all(engine)
