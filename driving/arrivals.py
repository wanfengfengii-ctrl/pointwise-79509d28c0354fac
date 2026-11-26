from dataclasses import asdict, dataclass

from driving.progress import advance_progress, next_stop
from onboard.commitments import fulfill_commitments


@dataclass(frozen=True)
class Arrival:
    id: int
    trip: str
    occurrence: str
    station: str
    revision: str

    @property
    def key(self):
        return self.trip, self.occurrence, self.station


def list_arrivals(db, trip):
    return [Arrival(**dict(row)) for row in db.execute(
        'SELECT * FROM arrivals WHERE trip = ? ORDER BY id', (trip,)
    )]


def arrive(db, trip, occurrence):
    arrival_id = advance_progress(db, trip, occurrence)
    row = db.execute('SELECT * FROM arrivals WHERE id = ?', (arrival_id,)).fetchone()
    actual = Arrival(**dict(row))
    fulfill_commitments(db, actual.trip, actual.occurrence, actual.station, actual.id)
    following = next_stop(db, trip)
    return {'arrival': asdict(actual), 'next_stop': asdict(following) if following else None}
