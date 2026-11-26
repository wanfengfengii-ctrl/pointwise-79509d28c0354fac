import argparse
from dataclasses import asdict

from driving.arrivals import arrive, list_arrivals
from driving.end_trip import end_trip
from driving.load import load_trip
from driving.progress import read_progress
from driving.store import VehicleStore
from onboard.announcements import list_announcements
from onboard.commitments import list_commitments
from onboard.requests import confirm_stop, read_confirmation
from onboard.route_changes import apply_diversion
from review.readback import read_review
from route.revisions import Revision
from transport import ApiError, array, field, make_server, run_server, text


def _removed_keys(payload):
    keys = []
    for pair in array(payload, 'removed'):
        if not isinstance(pair, list) or len(pair) != 2:
            raise ApiError(400, 'invalid_input', 'Each removed call needs an occurrence and station')
        keys.append((text(pair[0], 'occurrence'), text(pair[1], 'station')))
    if len(set(keys)) != len(keys):
        raise ApiError(400, 'invalid_input', 'Removed call keys must be unique')
    return keys


def serve_vehicle(db_path, port=8091, *, before_announcement=None):
    store = VehicleStore(db_path)
    store.initialize()

    def load(body):
        trip = field(body, 'trip')
        route = Revision.from_dict(body.get('route'))
        with store.connect(write=True) as db:
            loaded = load_trip(db, trip, field(body, 'vehicle'), route)
            return {
                'status': 'loaded', 'trip': trip, 'vehicle': loaded.vehicle,
                'route': loaded.initial_route.as_dict(),
            }

    def divert(body):
        trip = field(body, 'trip')
        request = field(body, 'request')
        base = field(body, 'base')
        target = Revision.from_dict(body.get('target'))
        removed = _removed_keys(body.get('removed'))
        with store.connect(write=True) as db:
            return apply_diversion(db, trip, request, base, target, removed)

    def confirm(body):
        return confirm_stop(
            store, field(body, 'trip'), field(body, 'occurrence'), field(body, 'request'),
            before_announcement,
        )

    def confirmation(body):
        with store.connect() as db:
            return read_confirmation(db, field(body, 'trip'), field(body, 'request'))

    def vehicle_status(body):
        trip = field(body, 'trip')
        with store.connect() as db:
            progress = read_progress(db, trip)
            following = progress.next
            return {
                'trip': trip, 'vehicle': progress.loaded.vehicle,
                'closed': progress.loaded.closed, 'route': progress.loaded.route.as_dict(),
                'next_stop': asdict(following) if following else None,
                'arrivals': [asdict(row) for row in list_arrivals(db, trip)],
                'speeches': [asdict(row) for row in list_announcements(db, trip)],
                'commitments': [asdict(row) for row in list_commitments(db, trip)],
            }

    def record_arrival(body):
        with store.connect(write=True) as db:
            return arrive(db, field(body, 'trip'), field(body, 'occurrence'))

    def close(body):
        with store.connect(write=True) as db:
            return asdict(end_trip(db, field(body, 'trip')))

    def review(body):
        with store.connect() as db:
            return read_review(db, field(body, 'trip'))

    return make_server({
        '/internal/load_trip': load,
        '/internal/divert_trip': divert,
        '/confirm_stop': confirm,
        '/confirmation_status': confirmation,
        '/vehicle_status': vehicle_status,
        '/arrive': record_arrival,
        '/end_trip': close,
        '/read_review': review,
    }, port)


def main():
    parser = argparse.ArgumentParser(description='Community loop vehicle service')
    parser.add_argument('--db', default='vehicle.sqlite')
    parser.add_argument('--port', type=int, default=8091)
    args = parser.parse_args()
    run_server(serve_vehicle(args.db, args.port))


if __name__ == '__main__':
    main()
