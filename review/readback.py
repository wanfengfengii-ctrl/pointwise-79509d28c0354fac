import json

from driving.load import read_loaded_route
from transport import ApiError


def read_review(db, trip):
    route = read_loaded_route(db, trip)
    if not route.closed:
        raise ApiError(409, 'review_not_ready', 'The trip is still in operation')
    row = db.execute('SELECT summary FROM reviews WHERE trip = ?', (trip,)).fetchone()
    if row is None:
        raise RuntimeError('The closed trip lacks its finalized review')
    return json.loads(row['summary'])
