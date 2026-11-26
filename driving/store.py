import sqlite3
from contextlib import contextmanager


SCHEMA = '''
CREATE TABLE IF NOT EXISTS loaded_routes (
    trip TEXT PRIMARY KEY,
    vehicle TEXT NOT NULL,
    initial_route TEXT NOT NULL,
    current_route TEXT NOT NULL,
    generation INTEGER NOT NULL DEFAULT 0 CHECK (generation >= 0),
    closed INTEGER NOT NULL DEFAULT 0 CHECK (closed IN (0, 1))
);
CREATE TABLE IF NOT EXISTS arrivals (
    id INTEGER PRIMARY KEY,
    trip TEXT NOT NULL REFERENCES loaded_routes (trip),
    occurrence TEXT NOT NULL,
    station TEXT NOT NULL,
    revision TEXT NOT NULL,
    UNIQUE (trip, occurrence)
);
CREATE TABLE IF NOT EXISTS confirmations (
    trip TEXT NOT NULL REFERENCES loaded_routes (trip),
    request TEXT NOT NULL,
    occurrence TEXT NOT NULL,
    station TEXT NOT NULL,
    name TEXT NOT NULL,
    generation INTEGER NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('queued', 'spoken', 'terminated')),
    PRIMARY KEY (trip, request)
);
CREATE TABLE IF NOT EXISTS speeches (
    id INTEGER PRIMARY KEY,
    trip TEXT NOT NULL,
    request TEXT NOT NULL,
    occurrence TEXT NOT NULL,
    station TEXT NOT NULL,
    text TEXT NOT NULL,
    UNIQUE (trip, request),
    FOREIGN KEY (trip, request) REFERENCES confirmations (trip, request)
);
CREATE TABLE IF NOT EXISTS commitments (
    speech_id INTEGER PRIMARY KEY REFERENCES speeches (id),
    trip TEXT NOT NULL,
    request TEXT NOT NULL,
    occurrence TEXT NOT NULL,
    station TEXT NOT NULL,
    arrival_id INTEGER REFERENCES arrivals (id),
    FOREIGN KEY (trip, request) REFERENCES confirmations (trip, request)
);
CREATE INDEX IF NOT EXISTS commitments_by_trip ON commitments (trip, speech_id);
CREATE TABLE IF NOT EXISTS vehicle_diversions (
    trip TEXT NOT NULL REFERENCES loaded_routes (trip),
    request TEXT NOT NULL,
    command TEXT NOT NULL,
    decision TEXT NOT NULL,
    PRIMARY KEY (trip, request)
);
CREATE TABLE IF NOT EXISTS reviews (
    trip TEXT PRIMARY KEY REFERENCES loaded_routes (trip),
    summary TEXT NOT NULL
);
'''


class VehicleStore:
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
