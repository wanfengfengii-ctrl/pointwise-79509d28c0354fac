import json
import threading
import unittest
from collections import defaultdict, deque
from dataclasses import dataclass, field
from http.client import HTTPConnection
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory

from dispatch.http import serve_dispatch
from onboard.http import serve_vehicle
from transport import ApiError, request_json


@dataclass
class ReplyDrop:
    after: bool
    triggered: threading.Event = field(default_factory=threading.Event)


class LoopbackRelay:
    def __init__(self, target):
        self.target = target
        self.drops = defaultdict(deque)
        self.lock = threading.Lock()
        relay = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, format, *args):
                return

            def do_POST(self):
                data = self.rfile.read(int(self.headers['Content-Length']))
                with relay.lock:
                    queue = relay.drops[self.path]
                    drop = queue.popleft() if queue else None
                if drop is not None and not drop.after:
                    self.close_connection = True
                    drop.triggered.set()
                    return

                connection = HTTPConnection(*relay.target, timeout=25)
                try:
                    connection.request('POST', self.path, data, {'Content-Type': 'application/json'})
                    response = connection.getresponse()
                    status = response.status
                    content = response.read()
                finally:
                    connection.close()
                if drop is not None:
                    self.close_connection = True
                    drop.triggered.set()
                    return

                self.send_response(status)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(content)))
                self.end_headers()
                self.wfile.write(content)

        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)

    def drop_next(self, path, *, after):
        drop = ReplyDrop(after)
        with self.lock:
            self.drops[path].append(drop)
        return drop


class AnnouncementGate:
    def __init__(self, request='C1'):
        self.request = request
        self.entered = threading.Event()
        self.release = threading.Event()

    def __call__(self, entry):
        if entry.request == self.request:
            self.entered.set()
            if not self.release.wait(20):
                raise RuntimeError('The test did not release the queued confirmation')


def url(server):
    host, port = server.server_address
    return f'http://{host}:{port}'


class Services:
    def __init__(self, directory):
        self.dispatch_db = Path(directory) / 'dispatch.sqlite'
        self.vehicle_db = Path(directory) / 'vehicle.sqlite'
        self.running = []

    def _start(self, server):
        thread = threading.Thread(
            target=server.serve_forever, kwargs={'poll_interval': 0.02}, daemon=True,
        )
        thread.start()
        self.running.append((server, thread))
        return server

    def start(self, before_announcement=None):
        self.vehicle = self._start(serve_vehicle(self.vehicle_db, 0, before_announcement=before_announcement))
        self.relay = LoopbackRelay(self.vehicle.server_address)
        self._start(self.relay.server)
        self.dispatch = self._start(serve_dispatch(self.dispatch_db, self.vehicle_relay, 0))

    @property
    def vehicle_relay(self):
        return url(self.relay.server)

    def stop(self):
        for server, thread in reversed(self.running):
            server.shutdown()
            server.server_close()
            thread.join()
        self.running.clear()

    def reopen(self, before_announcement=None):
        self.stop()
        self.start(before_announcement)


class LoopCase(unittest.TestCase):
    def setUp(self):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.services = Services(directory.name)
        self.addCleanup(self.services.stop)
        self.services.start()

    def dispatch(self, path, **body):
        return request_json(url(self.services.dispatch), path, body, timeout=25)

    def vehicle(self, path, **body):
        return request_json(url(self.services.vehicle), path, body, timeout=25)

    def define(self, revision, *calls):
        return self.dispatch(
            '/define_route', line='river', revision=revision,
            calls=[{'occurrence': occurrence, 'station': station} for occurrence, station in calls],
        )['route']

    def open_trip(self, trip='T', revision='R1', vehicle='bus-1'):
        return self.dispatch('/open_trip', trip=trip, vehicle=vehicle, line='river', revision=revision)

    def divert(self, revision, request='D1', trip='T'):
        return self.dispatch('/divert_trip', trip=trip, revision=revision, request=request)

    def published(self, trip='T', request=None):
        body = {'trip': trip}
        if request is not None:
            body['request'] = request
        return self.dispatch('/route_status', **body)

    def confirm(self, occurrence, request='C1', trip='T'):
        return self.vehicle('/confirm_stop', trip=trip, occurrence=occurrence, request=request)

    def confirmation(self, request='C1', trip='T'):
        return self.vehicle('/confirmation_status', trip=trip, request=request)

    def arrive(self, occurrence, trip='T'):
        return self.vehicle('/arrive', trip=trip, occurrence=occurrence)

    def vehicle_state(self, trip='T'):
        return self.vehicle('/vehicle_status', trip=trip)

    def assert_api_error(self, status, code, operation, *args, **kwargs):
        with self.assertRaises(ApiError) as received:
            operation(*args, **kwargs)
        self.assertEqual((received.exception.status, received.exception.code), (status, code))


def occurrences(route):
    return [call['occurrence'] for call in route['calls']]


def show_scenario(case_id, inputs, expected, actual, downstream_expected, downstream_actual,
                  code_paths, oracle):
    document = {
        'case_id': case_id, 'input': inputs, 'expected': expected, 'actual': actual,
        'downstream_expected': downstream_expected, 'downstream_actual': downstream_actual,
        'code_paths': code_paths, 'oracle': oracle,
    }
    print('POINTWISE_SCENARIO ' + json.dumps(document, ensure_ascii=False, sort_keys=True), flush=True)
