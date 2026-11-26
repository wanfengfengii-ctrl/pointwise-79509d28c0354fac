from dataclasses import dataclass

from onboard.commitments import record_commitment


@dataclass(frozen=True)
class SpeechRecord:
    id: int
    trip: str
    request: str
    occurrence: str
    station: str
    text: str


def read_announcement(db, trip, request):
    row = db.execute(
        'SELECT * FROM speeches WHERE trip = ? AND request = ?', (trip, request)
    ).fetchone()
    return SpeechRecord(**dict(row)) if row is not None else None


def list_announcements(db, trip):
    return [SpeechRecord(**dict(row)) for row in db.execute(
        'SELECT * FROM speeches WHERE trip = ? ORDER BY id', (trip,)
    )]


def perform_announcement(db, request):
    # In this service a persisted speech event is the simulated speaker output.
    words = f'将在{request.name}停靠'
    cursor = db.execute(
        'INSERT INTO speeches (trip, request, occurrence, station, text) VALUES (?, ?, ?, ?, ?)',
        (request.trip, request.request, request.occurrence, request.station, words),
    )
    speech = SpeechRecord(
        cursor.lastrowid, request.trip, request.request, request.occurrence, request.station, words
    )
    record_commitment(db, speech)
    return speech
