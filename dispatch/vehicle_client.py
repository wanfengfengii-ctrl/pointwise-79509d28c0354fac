from http.client import HTTPException

from transport import request_json


class VehicleReplyUnavailable(Exception):
    pass


class VehicleClient:
    def __init__(self, url, timeout=10):
        self.url = url
        self.timeout = timeout

    def _send(self, path, body):
        try:
            return request_json(self.url, path, body, self.timeout)
        except (OSError, HTTPException, ValueError) as error:
            raise VehicleReplyUnavailable(path) from error

    def load_trip(self, trip, vehicle, route):
        body = {'trip': trip, 'vehicle': vehicle, 'route': route.as_dict()}
        reply = self._send('/internal/load_trip', body)
        if reply.get('status') != 'loaded' or any(reply.get(key) != value for key, value in body.items()):
            raise VehicleReplyUnavailable('Unverified load reply')
        return reply

    def submit_diversion(self, receipt, target, change):
        body = {
            'trip': receipt.trip,
            'request': receipt.request,
            'base': receipt.base,
            'target': target.as_dict(),
            'removed': [list(call.key) for call in change.removed],
        }
        reply = self._send('/internal/divert_trip', body)
        expected = {
            'trip': receipt.trip, 'request': receipt.request, 'base': receipt.base,
            'line': target.line, 'revision': target.revision,
        }
        if any(reply.get(key) != value for key, value in expected.items()):
            raise VehicleReplyUnavailable('Diversion reply does not identify the original command')
        blocked = reply.get('blocked')
        if not isinstance(blocked, list) or any(not isinstance(item, str) for item in blocked):
            raise VehicleReplyUnavailable('Invalid diversion blockers')
        status = reply.get('status')
        reason = reply.get('reason')
        if status == 'effective' and 'reason' in reply and reason is None and not blocked:
            return reply
        if status == 'conflict' and isinstance(reason, str) and reason:
            return reply
        raise VehicleReplyUnavailable('No definite vehicle decision')
