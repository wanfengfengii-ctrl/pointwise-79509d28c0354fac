import json
from dataclasses import asdict, dataclass

from transport import ApiError, encode


@dataclass(frozen=True)
class DiversionReceipt:
    trip: str
    request: str
    base: str
    revision: str
    status: str
    reason: str | None
    blocked: tuple[str, ...]

    def as_dict(self):
        return asdict(self)


def read_diversion_receipt(db, trip, request):
    row = db.execute(
        'SELECT * FROM diversions WHERE trip = ? AND request = ?', (trip, request)
    ).fetchone()
    if row is None:
        return None
    data = dict(row)
    data['blocked'] = tuple(json.loads(data['blocked']))
    return DiversionReceipt(**data)


def reserve_diversion(db, trip, request, base, revision):
    existing = read_diversion_receipt(db, trip, request)
    if existing is not None:
        if existing.revision != revision:
            raise ApiError(409, 'request_conflict', 'The diversion number has different input')
        return existing
    pending = db.execute(
        "SELECT request FROM diversions WHERE trip = ? AND status = 'pending'", (trip,)
    ).fetchone()
    if pending is not None:
        raise ApiError(409, 'diversion_pending', f"Continue diversion {pending['request']} first")
    db.execute(
        'INSERT INTO diversions (trip, request, base, revision, status) VALUES (?, ?, ?, ?, ?)',
        (trip, request, base, revision, 'pending'),
    )
    return read_diversion_receipt(db, trip, request)


def settle_diversion(db, receipt, decision):
    changed = db.execute(
        'UPDATE diversions SET status = ?, reason = ?, blocked = ? '
        "WHERE trip = ? AND request = ? AND status = 'pending'",
        (decision['status'], decision['reason'], encode(decision['blocked']),
         receipt.trip, receipt.request),
    ).rowcount
    if changed != 1:
        raise RuntimeError('Expected a pending dispatch receipt')
