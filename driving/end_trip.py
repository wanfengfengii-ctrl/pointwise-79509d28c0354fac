from dataclasses import dataclass

from driving.progress import ensure_all_arrived
from review.finalize import finalize_review


@dataclass(frozen=True)
class EndTripResult:
    trip: str
    status: str
    arrival_count: int


def end_trip(db, trip):
    progress = ensure_all_arrived(db, trip)
    if not progress.loaded.closed:
        finalize_review(db, trip, progress.loaded.route.revision)
        db.execute('UPDATE loaded_routes SET closed = 1 WHERE trip = ?', (trip,))
    return EndTripResult(trip, 'closed', progress.arrived_count)
