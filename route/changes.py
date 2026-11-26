from dataclasses import dataclass

from route.loops import StopCall
from route.revisions import Revision
from transport import ApiError


@dataclass(frozen=True)
class RouteChange:
    retained: tuple[StopCall, ...]
    removed: tuple[StopCall, ...]
    added: tuple[StopCall, ...]
    moved: tuple[StopCall, ...]


def compare_revisions(old: Revision, new: Revision):
    if old.line != new.line:
        raise ApiError(409, 'wrong_line', 'A diversion must keep the trip line')
    before = {call.key: call for call in old.calls}
    after = {call.key: call for call in new.calls}
    return RouteChange(
        retained=tuple(call for key, call in after.items() if key in before),
        removed=tuple(call for key, call in before.items() if key not in after),
        added=tuple(call for key, call in after.items() if key not in before),
        moved=tuple(
            call for key, call in after.items()
            if key in before and before[key].position != call.position
        ),
    )
