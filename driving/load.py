import json
from dataclasses import dataclass

from route.revisions import Revision
from transport import ApiError, encode


@dataclass(frozen=True)
class LoadedRoute:
    trip: str
    vehicle: str
    initial_route: Revision
    route: Revision
    generation: int
    closed: bool


def read_loaded_route(db, trip):
    row = db.execute('SELECT * FROM loaded_routes WHERE trip = ?', (trip,)).fetchone()
    if row is None:
        raise ApiError(404, 'trip_not_found', f'No vehicle route for trip {trip}')
    return LoadedRoute(
        trip, row['vehicle'],
        Revision.from_dict(json.loads(row['initial_route'])),
        Revision.from_dict(json.loads(row['current_route'])),
        row['generation'], bool(row['closed']),
    )


def load_trip(db, trip, vehicle, route):
    original = encode(route.as_dict())
    row = db.execute(
        'SELECT vehicle, initial_route FROM loaded_routes WHERE trip = ?', (trip,)
    ).fetchone()
    if row is None:
        db.execute(
            'INSERT INTO loaded_routes (trip, vehicle, initial_route, current_route) '
            'VALUES (?, ?, ?, ?)', (trip, vehicle, original, original),
        )
    elif (row['vehicle'], row['initial_route']) != (vehicle, original):
        raise ApiError(409, 'trip_conflict', 'The vehicle has a different original load')
    return read_loaded_route(db, trip)


def replace_remaining_route(db, loaded, target):
    arrived = tuple(
        (row['occurrence'], row['station'])
        for row in db.execute(
            'SELECT occurrence, station FROM arrivals WHERE trip = ? ORDER BY id', (loaded.trip,)
        )
    )
    proposed_prefix = tuple(call.key for call in target.calls[:len(arrived)])
    if proposed_prefix != arrived:
        raise ApiError(409, 'arrived_prefix_conflict', 'The candidate changes the actual arrival prefix')
    db.execute(
        'UPDATE loaded_routes SET current_route = ?, generation = generation + 1 WHERE trip = ?',
        (encode(target.as_dict()), loaded.trip),
    )
