from dataclasses import dataclass

from driving.load import LoadedRoute, read_loaded_route
from transport import ApiError


@dataclass(frozen=True)
class ArrivalProgress:
    loaded: LoadedRoute
    arrived_count: int

    @property
    def remaining(self):
        return self.loaded.route.calls[self.arrived_count:]

    @property
    def next(self):
        return self.remaining[0] if self.remaining else None

    def future_call(self, occurrence):
        if self.loaded.closed:
            return None
        return next((call for call in self.remaining if call.occurrence == occurrence), None)


def read_progress(db, trip):
    loaded = read_loaded_route(db, trip)
    count = db.execute('SELECT count(*) FROM arrivals WHERE trip = ?', (trip,)).fetchone()[0]
    return ArrivalProgress(loaded, count)


def next_stop(db, trip):
    return read_progress(db, trip).next


def advance_progress(db, trip, occurrence):
    progress = read_progress(db, trip)
    if progress.loaded.closed:
        raise ApiError(409, 'trip_closed', 'The trip is closed')
    call = progress.next
    if call is None or call.occurrence != occurrence:
        expected = call.occurrence if call is not None else 'none'
        raise ApiError(409, 'wrong_arrival', f'Expected next occurrence {expected}')
    cursor = db.execute(
        'INSERT INTO arrivals (trip, occurrence, station, revision) VALUES (?, ?, ?, ?)',
        (trip, call.occurrence, call.station, progress.loaded.route.revision),
    )
    return cursor.lastrowid


def ensure_all_arrived(db, trip):
    progress = read_progress(db, trip)
    if progress.next is not None:
        raise ApiError(409, 'stops_remaining', f'Next planned stop is {progress.next.occurrence}')
    return progress
