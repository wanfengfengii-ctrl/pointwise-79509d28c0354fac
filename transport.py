import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.error import HTTPError
from urllib.request import ProxyHandler, Request, build_opener


class ApiError(Exception):
    def __init__(self, status, code, detail):
        super().__init__(detail)
        self.status = status
        self.code = code
        self.detail = detail


def encode(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def object_value(value, name):
    if not isinstance(value, dict):
        raise ApiError(400, 'invalid_input', f'{name} must be a JSON object')
    return value


def array(value, name):
    if not isinstance(value, list):
        raise ApiError(400, 'invalid_input', f'{name} must be a JSON array')
    return value


def text(value, name):
    if not isinstance(value, str) or not value.strip():
        raise ApiError(400, 'invalid_input', f'{name} must be a nonempty string')
    return value


def field(body, name):
    return text(body.get(name), name)


def make_server(routes, port):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format, *args):
            return

        def do_POST(self):
            try:
                action = routes.get(self.path)
                if action is None:
                    raise ApiError(404, 'endpoint_not_found', self.path)
                body = self.read_body()
                result = action(body)
                status = 200
            except ApiError as error:
                result = {'error': error.code, 'detail': error.detail}
                status = error.status
            self.send_json(status, result)

        def read_body(self):
            try:
                length = int(self.headers.get('Content-Length', ''))
                if length <= 0:
                    raise ValueError('empty body')
                body = json.loads(self.rfile.read(length))
            except (ValueError, UnicodeError) as error:
                raise ApiError(400, 'invalid_json', 'A JSON body is required') from error
            return object_value(body, 'body')

        def send_json(self, status, result):
            payload = encode(result).encode('utf-8')
            try:
                self.send_response(status)
                self.send_header('Content-Type', 'application/json; charset=utf-8')
                self.send_header('Content-Length', str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)
            except (BrokenPipeError, ConnectionResetError):
                return

    return ThreadingHTTPServer(('127.0.0.1', port), Handler)


def run_server(server):
    with server:
        address, port = server.server_address
        print(f'Listening on http://{address}:{port}', flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


def request_json(base_url, path, body, timeout=10):
    request = Request(
        base_url.rstrip('/') + path,
        data=encode(body).encode('utf-8'),
        headers={'Content-Type': 'application/json'},
        method='POST',
    )
    opener = build_opener(ProxyHandler({}))
    try:
        with opener.open(request, timeout=timeout) as reply:
            document = json.load(reply)
    except HTTPError as error:
        with error:
            document = json.load(error)
        if not isinstance(document, dict) or not isinstance(document.get('error'), str):
            raise ValueError('Invalid HTTP error reply') from error
        raise ApiError(error.code, document['error'], document.get('detail', '')) from error
    if not isinstance(document, dict):
        raise ValueError('Expected a JSON object reply')
    return document
