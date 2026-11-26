from dispatch.publication import publish_open_route
from dispatch.vehicle_client import VehicleReplyUnavailable
from route.revisions import read_revision
from transport import ApiError


def open_trip(store, client, trip, vehicle, line, revision):
    with store.connect(write=True) as db:
        existing = db.execute('SELECT * FROM trips WHERE trip = ?', (trip,)).fetchone()
        if existing is not None:
            original = existing['vehicle'], existing['line'], existing['initial_revision']
            if original != (vehicle, line, revision):
                raise ApiError(409, 'trip_conflict', 'The trip has a different initial assignment')
        route = read_revision(db, line, revision)
        if existing is None:
            db.execute(
                'INSERT INTO trips (trip, vehicle, line, initial_revision) VALUES (?, ?, ?, ?)',
                (trip, vehicle, line, revision),
            )
        published = existing is not None and existing['current_revision'] is not None

    if not published:
        try:
            client.load_trip(trip, vehicle, route)
        except VehicleReplyUnavailable:
            with store.connect() as db:
                row = db.execute('SELECT current_revision FROM trips WHERE trip = ?', (trip,)).fetchone()
                if row['current_revision'] is None:
                    return {'status': 'pending', 'trip': trip}
        else:
            with store.connect(write=True) as db:
                publish_open_route(db, trip)

    snapshot = route.as_dict()
    return {
        'status': 'opened', 'trip': trip, 'vehicle': vehicle, 'route': snapshot,
        'next_stop': snapshot['calls'][0] if snapshot['calls'] else None,
    }
