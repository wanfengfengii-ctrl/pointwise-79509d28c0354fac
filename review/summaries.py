from dataclasses import asdict, dataclass

from driving.arrivals import Arrival
from review.coverage import CoverageEntry


@dataclass(frozen=True)
class TripSummary:
    trip: str
    revision: str
    commitment_count: int
    fulfilled_count: int
    arrivals: list[Arrival]
    coverage: list[CoverageEntry]

    def as_dict(self):
        return asdict(self)


def build_summary(trip, revision, arrivals, entries):
    arrival_positions = {arrival.id: index for index, arrival in enumerate(arrivals)}

    def review_order(entry):
        position = arrival_positions.get(entry.commitment.arrival_id, len(arrivals))
        return position, entry.speech.id

    return TripSummary(
        trip=trip,
        revision=revision,
        commitment_count=len(entries),
        fulfilled_count=sum(entry.arrival is not None for entry in entries),
        arrivals=arrivals,
        coverage=sorted(entries, key=review_order),
    )
