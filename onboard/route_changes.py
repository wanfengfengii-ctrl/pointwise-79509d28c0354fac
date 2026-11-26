import json
from hashlib import sha256

from driving.load import read_loaded_route, replace_remaining_route
from driving.progress import read_progress
from onboard.commitments import list_commitments
from transport import ApiError, encode


def read_stop_change_facts(db, trip, removed):
    affected = set(removed)
    return [
        commitment for commitment in list_commitments(db, trip)
        if commitment.arrival_id is None and (commitment.occurrence, commitment.station) in affected
    ]


def recheck_pending_requests(db, request):
    progress = read_progress(db, request.trip)
    if progress.loaded.closed:
        return False
    if request.generation != progress.loaded.generation:
        return any(call.name == request.name for call in progress.remaining)
    call = progress.future_call(request.occurrence)
    return call is not None and call.station == request.station


def apply_diversion(db, trip, request, base, target, removed):
    command = encode({'base': base, 'target': target.as_dict(), 'removed': removed})
    fingerprint = sha256(command.encode('utf-8')).hexdigest()
    existing = db.execute(
        'SELECT command, decision FROM vehicle_diversions WHERE trip = ? AND request = ?',
        (trip, request),
    ).fetchone()
    if existing is not None:
        if existing['command'] not in (command, fingerprint):
            raise ApiError(409, 'request_conflict', 'The vehicle diversion has different input')
        return json.loads(existing['decision'])

    loaded = read_loaded_route(db, trip)
    reason, blocked = _evaluate_and_apply(db, loaded, base, target, removed)
    decision = {
        'trip': trip, 'request': request, 'base': base, 'line': target.line,
        'revision': target.revision, 'status': 'effective' if reason is None else 'conflict',
        'reason': reason, 'blocked': blocked,
    }
    db.execute(
        'INSERT INTO vehicle_diversions (trip, request, command, decision) VALUES (?, ?, ?, ?)',
        (trip, request, fingerprint, encode(decision)),
    )
    return decision


def _evaluate_and_apply(db, loaded, base, target, removed):
    if loaded.closed:
        return 'trip_closed', []
    if loaded.route.line != target.line:
        return 'wrong_line', []
    if loaded.route.revision != base:
        return 'stale_revision', []

    facts = read_stop_change_facts(db, loaded.trip, removed)
    if facts:
        return 'promised_stop', list(dict.fromkeys(fact.occurrence for fact in facts))
    try:
        replace_remaining_route(db, loaded, target)
    except ApiError as error:
        if error.code != 'arrived_prefix_conflict':
            raise
        return error.code, []
    return None, []
