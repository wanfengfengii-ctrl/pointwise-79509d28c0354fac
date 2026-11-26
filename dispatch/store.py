import sqlite3
from contextlib import contextmanager


SCHEMA = '''
CREATE TABLE IF NOT EXISTS stops (
    station TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    location TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS revisions (
    line TEXT NOT NULL,
    revision TEXT NOT NULL,
    source TEXT NOT NULL,
    snapshot TEXT NOT NULL,
    PRIMARY KEY (line, revision)
);
CREATE TABLE IF NOT EXISTS trips (
    trip TEXT PRIMARY KEY,
    vehicle TEXT NOT NULL,
    line TEXT NOT NULL,
    initial_revision TEXT NOT NULL,
    current_revision TEXT,
    FOREIGN KEY (line, initial_revision) REFERENCES revisions (line, revision),
    FOREIGN KEY (line, current_revision) REFERENCES revisions (line, revision)
);
CREATE TABLE IF NOT EXISTS diversions (
    trip TEXT NOT NULL REFERENCES trips (trip),
    request TEXT NOT NULL,
    base TEXT NOT NULL,
    revision TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('pending', 'effective', 'conflict')),
    reason TEXT,
    blocked TEXT NOT NULL DEFAULT '[]',
    PRIMARY KEY (trip, request)
);
CREATE UNIQUE INDEX IF NOT EXISTS one_pending_diversion
    ON diversions (trip) WHERE status = 'pending';
'''


class DispatchStore:
    def __init__(self, path):
        self.path = path

    def initialize(self):
        with self.connect() as db:
            db.executescript(SCHEMA)

    @contextmanager
    def connect(self, *, write=False):
        db = sqlite3.connect(self.path, isolation_level=None, timeout=10)
        try:
            db.row_factory = sqlite3.Row
            db.execute('PRAGMA foreign_keys = ON')
            db.execute('BEGIN IMMEDIATE' if write else 'BEGIN')
            with db:
                yield db
        finally:
            db.close()
