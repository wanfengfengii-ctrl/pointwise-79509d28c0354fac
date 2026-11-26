import json
from dataclasses import asdict, dataclass

from route.loops import StopCall, expand_loop, read_call_input
from transport import ApiError, encode, field, object_value


@dataclass(frozen=True)
class Revision:
    line: str
    revision: str
    calls: tuple[StopCall, ...]

    def as_dict(self):
        return {
            'line': self.line,
            'revision': self.revision,
            'calls': [asdict(call) for call in self.calls],
        }

    @classmethod
    def from_dict(cls, document):
        document = object_value(document, 'route')
        line = field(document, 'line')
        revision = field(document, 'revision')
        calls = document.get('calls')
        result = []
        for position, (occurrence, station) in enumerate(read_call_input(calls)):
            call = calls[position]
            if type(call.get('position')) is not int or call['position'] != position:
                raise ApiError(400, 'invalid_position', 'Frozen calls must follow their positions')
            result.append(StopCall(occurrence, station, field(call, 'name'), position))
        return cls(line, revision, tuple(result))


def define_route(db, line, revision, calls):
    source = encode(read_call_input(calls))
    existing = db.execute(
        'SELECT source, snapshot FROM revisions WHERE line = ? AND revision = ?',
        (line, revision),
    ).fetchone()
    if existing is not None:
        if existing['source'] != source:
            raise ApiError(409, 'revision_conflict', 'The frozen revision has different calls')
        return Revision.from_dict(json.loads(existing['snapshot']))
    result = Revision(line, revision, expand_loop(db, calls))
    db.execute(
        'INSERT INTO revisions (line, revision, source, snapshot) VALUES (?, ?, ?, ?)',
        (line, revision, source, encode(result.as_dict())),
    )
    return result


def read_revision(db, line, revision):
    row = db.execute(
        'SELECT snapshot FROM revisions WHERE line = ? AND revision = ?', (line, revision)
    ).fetchone()
    if row is None:
        raise ApiError(404, 'revision_not_found', f'Unknown revision {line}/{revision}')
    return Revision.from_dict(json.loads(row['snapshot']))
