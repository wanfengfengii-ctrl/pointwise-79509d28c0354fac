from dataclasses import dataclass


@dataclass(frozen=True)
class Commitment:
    speech_id: int
    trip: str
    request: str
    occurrence: str
    station: str
    arrival_id: int | None

    @property
    def key(self):
        return self.trip, self.occurrence, self.station


def record_commitment(db, speech):
    db.execute(
        'INSERT INTO commitments (speech_id, trip, request, occurrence, station) '
        'VALUES (?, ?, ?, ?, ?)',
        (speech.id, speech.trip, speech.request, speech.occurrence, speech.station),
    )


def fulfill_commitments(db, trip, occurrence, station, arrival_id):
    db.execute(
        'UPDATE commitments SET arrival_id = ? '
        'WHERE trip = ? AND occurrence = ? AND station = ? AND arrival_id IS NULL',
        (arrival_id, trip, occurrence, station),
    )


def list_commitments(db, trip):
    return [Commitment(**dict(row)) for row in db.execute(
        'SELECT * FROM commitments WHERE trip = ? ORDER BY speech_id', (trip,)
    )]
