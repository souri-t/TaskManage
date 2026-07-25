from collections.abc import Generator
import sys
from threading import RLock

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import get_settings


class Base(DeclarativeBase):
    pass


settings = get_settings()
connect_args = {"check_same_thread": False, "timeout": 30}
if sys.version_info >= (3, 12):
    connect_args["autocommit"] = False

engine: Engine = create_engine(settings.database_url, connect_args=connect_args)


@event.listens_for(engine, "connect")
def configure_sqlite(dbapi_connection, _connection_record) -> None:
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode = WAL")
    cursor.execute("PRAGMA foreign_keys = ON")
    cursor.execute("PRAGMA busy_timeout = 30000")
    cursor.execute("PRAGMA synchronous = NORMAL")
    cursor.close()


SessionLocal = sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)
write_lock = RLock()


def get_session() -> Generator[Session, None, None]:
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
