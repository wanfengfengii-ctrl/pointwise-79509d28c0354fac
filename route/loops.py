from dataclasses import dataclass

from route.stops import read_stop
from transport import ApiError, array, field, object_value


@dataclass(frozen=True)
class StopCall:
    occurrence: str
    station: str
    name: str
    position: int

    @property
    def key(self):
        return self.occurrence, self.station


def read_call_input(calls):
    pairs = []
    seen = set()
    for entry in array(calls, 'calls'):
        call = object_value(entry, 'stop call')
        occurrence = field(call, 'occurrence')
        station = field(call, 'station')
        if occurrence in seen:
            raise ApiError(422, 'duplicate_occurrence', f'Duplicate stop call {occurrence}')
        seen.add(occurrence)
        pairs.append((occurrence, station))
    return pairs


def expand_loop(db, calls):
    result = []
    for position, (occurrence, station) in enumerate(read_call_input(calls)):
        stop = read_stop(db, station)
        result.append(StopCall(occurrence, stop.station, stop.name, position))
    return tuple(result)
