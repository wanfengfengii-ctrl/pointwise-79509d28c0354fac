import json
from pathlib import Path

from route.revisions import define_route
from route.stops import seed_missing_stops
from transport import array, field, object_value


def initialize_sample(db):
    samples = Path(__file__).resolve().parent.parent / 'samples'
    stops = json.loads((samples / 'stops.json').read_text(encoding='utf-8'))
    revisions = json.loads((samples / 'routes.json').read_text(encoding='utf-8'))
    seed_missing_stops(db, array(stops, 'stops'))
    for entry in array(revisions, 'routes'):
        route = object_value(entry, 'sample route')
        line = field(route, 'line')
        revision = field(route, 'revision')
        exists = db.execute(
            'SELECT 1 FROM revisions WHERE line = ? AND revision = ?', (line, revision)
        ).fetchone()
        if exists is None:
            define_route(db, line, revision, route.get('calls'))
