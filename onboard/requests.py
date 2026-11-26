from dataclasses import asdict, dataclass

from driving.progress import read_progress
from onboard.announcements import perform_announcement, read_announcement
from onboard.route_changes import recheck_pending_requests
from transport import ApiError


@dataclass(frozen=True)
class ConfirmationRequest:
    trip: str
    request: str
    occurrence: str
    station: str
    name: str
    generation: int
    status: str


def _read_request(db, trip, request):
    row = db.execute(
        'SELECT * FROM confirmations WHERE trip = ? AND request = ?', (trip, request)
    ).fetchone()
    return ConfirmationRequest(**dict(row)) if row is not None else None


def accept_request(db, trip, occurrence, request):
    existing = _read_request(db, trip, request)
    if existing is not None:
        if existing.occurrence != occurrence:
            raise ApiError(409, 'request_conflict', 'The confirmation number has different input')
        return existing
    progress = read_progress(db, trip)
    call = progress.future_call(occurrence)
    if call is None:
        raise ApiError(409, 'stop_unavailable', f'Stop call {occurrence} is unavailable')
    entry = ConfirmationRequest(
        trip, request, occurrence, call.station, call.name, progress.loaded.generation, 'queued'
    )
    db.execute(
        'INSERT INTO confirmations (trip, request, occurrence, station, name, generation, status) '
        'VALUES (:trip, :request, :occurrence, :station, :name, :generation, :status)',
        asdict(entry),
    )
    return entry


def read_confirmation(db, trip, request):
    entry = _read_request(db, trip, request)
    if entry is None:
        raise ApiError(404, 'confirmation_not_found', f'Unknown confirmation {request}')
    speech = read_announcement(db, trip, request)
    return {
        'trip': trip, 'request': request, 'occurrence': entry.occurrence,
        'station': entry.station, 'status': entry.status,
        'speech': asdict(speech) if speech is not None else None,
    }


def confirm_stop(store, trip, occurrence, request, before_announcement=None):
    with store.connect(write=True) as db:
        entry = accept_request(db, trip, occurrence, request)
        if entry.status != 'queued':
            return read_confirmation(db, trip, request)

    if before_announcement is not None:
        before_announcement(entry)

    with store.connect(write=True) as db:
        entry = _read_request(db, trip, request)
        if entry.status == 'queued':
            if recheck_pending_requests(db, entry):
                perform_announcement(db, entry)
                status = 'spoken'
            else:
                status = 'terminated'
            db.execute(
                'UPDATE confirmations SET status = ? WHERE trip = ? AND request = ?',
                (status, trip, request),
            )
        return read_confirmation(db, trip, request)
