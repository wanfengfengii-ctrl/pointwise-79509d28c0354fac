from dispatch.publication import publish_effective_revision, read_published_trip, route_status
from dispatch.receipts import read_diversion_receipt, reserve_diversion, settle_diversion
from dispatch.vehicle_client import VehicleReplyUnavailable
from route.changes import compare_revisions
from route.revisions import read_revision
from transport import ApiError


def divert_trip(store, client, trip, revision, request):
    with store.connect(write=True) as db:
        published = read_published_trip(db, trip)
        existing = read_diversion_receipt(db, trip, request)
        if existing is not None:
            if existing.revision != revision:
                raise ApiError(409, 'request_conflict', 'The diversion number has different input')
            if existing.status != 'pending':
                return route_status(db, trip, request)
        target = read_revision(db, published['line'], revision)
        receipt = reserve_diversion(db, trip, request, published['current_revision'], revision)
        base = read_revision(db, published['line'], receipt.base)
        change = compare_revisions(base, target)

    # The transport call follows the reservation commit. It holds no dispatch lock.
    try:
        decision = client.submit_diversion(receipt, target, change)
    except VehicleReplyUnavailable:
        # The vehicle may have committed, rolled back, or never received the
        # command.  Until its decision is read back, station publication stays
        # on the last confirmed revision and the receipt stays pending.
        with store.connect() as db:
            return route_status(db, trip, request)

    with store.connect(write=True) as db:
        current = read_diversion_receipt(db, trip, request)
        if current.status == 'pending':
            if decision['status'] == 'effective':
                publish_effective_revision(db, current)
            settle_diversion(db, current, decision)
        return route_status(db, trip, request)
