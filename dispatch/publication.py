from dispatch.receipts import read_diversion_receipt
from route.revisions import read_revision
from transport import ApiError


def publish_open_route(db, trip):
    db.execute(
        'UPDATE trips SET current_revision = initial_revision '
        'WHERE trip = ? AND current_revision IS NULL', (trip,)
    )


def publish_effective_revision(db, receipt):
    changed = db.execute(
        'UPDATE trips SET current_revision = ? WHERE trip = ? AND current_revision = ?',
        (receipt.revision, receipt.trip, receipt.base),
    ).rowcount
    if changed != 1:
        raise RuntimeError('Dispatch publication no longer has the expected predecessor')


def read_published_trip(db, trip):
    row = db.execute(
        'SELECT * FROM trips WHERE trip = ? AND current_revision IS NOT NULL', (trip,)
    ).fetchone()
    if row is None:
        raise ApiError(404, 'trip_not_found', f'No published trip {trip}')
    return row


def route_status(db, trip, request=None):
    published = read_published_trip(db, trip)
    route = read_revision(db, published['line'], published['current_revision'])
    receipt = None
    if request is not None:
        receipt = read_diversion_receipt(db, trip, request)
        if receipt is None:
            raise ApiError(404, 'diversion_not_found', f'Unknown diversion {request}')
    return {
        'trip': trip,
        'vehicle': published['vehicle'],
        'initial_revision': published['initial_revision'],
        'route': route.as_dict(),
        'diversion': receipt.as_dict() if receipt is not None else None,
    }
