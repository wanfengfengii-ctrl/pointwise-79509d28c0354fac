from http.client import RemoteDisconnected

from dispatch.store import DispatchStore
from tests.support import LoopCase, occurrences


class TestOpening(LoopCase):
    def test_same_name_and_seed_reopen(self):
        custom = self.define('CUSTOM', ('E1', 'east'), ('E2', 'west'))
        opened = self.open_trip('weekday', 'CUSTOM')
        self.assertEqual(opened['status'], 'opened')
        self.assertEqual(opened['route'], custom)
        self.assertEqual(occurrences(custom), ['E1', 'E2'])
        self.assertEqual([(call['station'], call['name'], call['position']) for call in custom['calls']],
                         [('east', '河桥', 0), ('west', '河桥', 1)])
        self.assertEqual(self.vehicle_state('weekday')['route'], custom)
        self.assertEqual(self.confirm('E1', trip='weekday')['status'], 'spoken')
        first = self.arrive('E1', 'weekday')['arrival']

        store = DispatchStore(self.services.dispatch_db)
        with store.connect(write=True) as db:
            db.execute('UPDATE stops SET name = ? WHERE station = ?', ('河桥东侧', 'east'))
            db.execute('DELETE FROM stops WHERE station = ?', ('market',))
            db.execute('DELETE FROM revisions WHERE line = ? AND revision = ?', ('river', 'R-WALK'))
        self.services.reopen()
        self.assertEqual(self.open_trip('weekday', 'CUSTOM'), opened)
        self.assertEqual(self.published('weekday')['route'], custom)
        self.assertEqual(self.define('CUSTOM', ('E1', 'east'), ('E2', 'west')), custom)
        self.assertEqual(self.define('LOCAL', ('E1', 'east'), ('X', 'market'))['calls'][0]['name'], '河桥东侧')
        self.assertEqual(occurrences(self.open_trip('walk', 'R-WALK')['route']), ['A', 'E1', 'E2'])
        state = self.vehicle_state('weekday')
        self.assertEqual(state['arrivals'], [first])
        self.assertEqual(state['commitments'][0]['arrival_id'], first['id'])
        self.assertEqual([speech['occurrence'] for speech in state['speeches']], ['E1'])
        self.assert_api_error(409, 'trip_conflict', self.open_trip, 'weekday', 'R1')
        self.assert_api_error(409, 'trip_conflict', self.open_trip, 'weekday', 'CUSTOM', 'other-bus')

    def test_reject_duplicate_occurrence(self):
        first = self.open_trip()['route']
        self.assert_api_error(422, 'duplicate_occurrence', self.define, 'BAD', ('E1', 'east'), ('E1', 'west'))
        self.assert_api_error(422, 'unknown_station', self.define, 'BAD-STOP', ('B', 'missing'))
        self.assert_api_error(409, 'revision_conflict', self.define, 'R1', ('E2', 'west'), ('E1', 'east'))
        self.assert_api_error(404, 'revision_not_found', self.open_trip, 'other', 'BAD')
        self.assert_api_error(404, 'revision_not_found', self.open_trip, 'other', 'BAD-STOP')
        self.assertEqual(self.published()['route'], first)
        self.assertEqual(self.define('R1', ('E1', 'east'), ('E2', 'west')), first)
        self.assert_api_error(400, 'invalid_input', self.dispatch, '/define_route', line='river', revision='MISSING')

    def test_open_reply_lost(self):
        drop = self.services.relay.drop_next('/internal/load_trip', after=True)
        self.assertEqual(self.open_trip()['status'], 'pending')
        self.assertTrue(drop.triggered.is_set())
        self.assert_api_error(404, 'trip_not_found', self.published)
        self.assertEqual(self.vehicle_state()['next_stop']['occurrence'], 'E1')
        self.services.reopen()
        opened = self.open_trip()
        self.assertEqual(opened['status'], 'opened')
        self.assertEqual(self.published()['route'], opened['route'])
        self.assertEqual(self.vehicle_state()['route'], opened['route'])
