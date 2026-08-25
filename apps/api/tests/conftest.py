import os
import tempfile
from pathlib import Path


TEST_DIRECTORY = tempfile.TemporaryDirectory()
DATABASE_PATH = Path(TEST_DIRECTORY.name) / "test.db"
os.environ["REVIEW_HUB_DATABASE_URL"] = f"sqlite:///{DATABASE_PATH}"

import pytest  # noqa: E402

from review_hub.database import Base, engine  # noqa: E402


@pytest.fixture(autouse=True)
def clean_database():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield
    Base.metadata.drop_all(engine)
