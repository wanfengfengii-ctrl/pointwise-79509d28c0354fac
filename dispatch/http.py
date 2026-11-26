import argparse

from dispatch.diversions import divert_trip
from dispatch.publication import route_status
from dispatch.store import DispatchStore
from dispatch.trips import open_trip
from dispatch.vehicle_client import VehicleClient
from route.revisions import define_route
from route.seed import initialize_sample
from transport import field, make_server, run_server


def serve_dispatch(db_path, vehicle_url, port=8090, *, seed=True):
    store = DispatchStore(db_path)
    store.initialize()
    if seed:
        with store.connect(write=True) as db:
            initialize_sample(db)
    client = VehicleClient(vehicle_url)

    def define(body):
        line = field(body, 'line')
        revision = field(body, 'revision')
        with store.connect(write=True) as db:
            route = define_route(db, line, revision, body.get('calls'))
            return {'route': route.as_dict()}

    def open_route(body):
        return open_trip(
            store, client, field(body, 'trip'), field(body, 'vehicle'),
            field(body, 'line'), field(body, 'revision'),
        )

    def status(body):
        request = field(body, 'request') if 'request' in body else None
        with store.connect() as db:
            return route_status(db, field(body, 'trip'), request)

    def divert(body):
        return divert_trip(
            store, client, field(body, 'trip'), field(body, 'revision'), field(body, 'request')
        )

    return make_server({
        '/define_route': define,
        '/open_trip': open_route,
        '/route_status': status,
        '/divert_trip': divert,
    }, port)


def main():
    parser = argparse.ArgumentParser(description='Community loop dispatch service')
    parser.add_argument('--db', default='dispatch.sqlite')
    parser.add_argument('--port', type=int, default=8090)
    parser.add_argument('--vehicle', default='http://127.0.0.1:8091')
    parser.add_argument('--no-seed', action='store_true')
    args = parser.parse_args()
    run_server(serve_dispatch(args.db, args.vehicle, args.port, seed=not args.no_seed))


if __name__ == '__main__':
    main()
