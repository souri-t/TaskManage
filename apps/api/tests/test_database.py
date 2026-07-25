from review_hub.database import configure_sqlite


class FakeCursor:
    def __init__(self, connection):
        self.connection = connection
        self.statements = []
        self.closed = False

    def execute(self, statement):
        assert self.connection.autocommit is True
        self.statements.append(statement)

    def close(self):
        self.closed = True


class FakeConnection:
    def __init__(self):
        self.autocommit = False
        self.created_cursor = None

    def cursor(self):
        self.created_cursor = FakeCursor(self)
        return self.created_cursor


def test_connection_pragmas_temporarily_enable_autocommit():
    connection = FakeConnection()

    configure_sqlite(connection, None)

    assert connection.autocommit is False
    assert connection.created_cursor.closed is True
    assert connection.created_cursor.statements == [
        "PRAGMA journal_mode = WAL",
        "PRAGMA foreign_keys = ON",
        "PRAGMA busy_timeout = 30000",
        "PRAGMA synchronous = NORMAL",
    ]
