from dataclasses import dataclass

from transport import ApiError, field, object_value


@dataclass(frozen=True)
class Stop:
    station: str
    name: str
    location: str


def read_stop(db, station):
    row = db.execute(
        'SELECT station, name, location FROM stops WHERE station = ?', (station,)
    ).fetchone()
    if row is None:
        raise ApiError(422, 'unknown_station', f'Unknown physical stop {station}')
    return Stop(**dict(row))


def seed_missing_stops(db, entries):
    for entry in entries:
        stop = object_value(entry, 'sample stop')
        db.execute(
            'INSERT INTO stops (station, name, location) VALUES (?, ?, ?) '
            'ON CONFLICT(station) DO NOTHING',
            (field(stop, 'station'), field(stop, 'name'), field(stop, 'location')),
        )
