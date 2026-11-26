from concurrent.futures import ThreadPoolExecutor
from http.client import RemoteDisconnected

from tests.support import AnnouncementGate, LoopCase, occurrences, show_scenario
from transport import request_json


class TestDiversion(LoopCase):
    def test_keep_promised_occurrence(self):
        self.open_trip(revision='R-WALK')
        first = self.arrive('A')['arrival']
        speech = self.confirm('E1')['speech']
        target = self.define('R2', ('A', 'center'), ('X', 'market'), ('E1', 'east'), ('E2', 'west'))
        result = self.divert('R2')
        self.assertEqual(result['diversion']['status'], 'effective')
        self.assertEqual(result['route'], target)
        self.assertEqual(self.published(request='D1'), result)
        self.assertEqual(self.open_trip(revision='R-WALK')['route']['revision'], 'R-WALK')
        state = self.vehicle_state()
        actual = [occurrences(result['route']), state['next_stop']['occurrence']]
        self.assertEqual(actual, [['A', 'X', 'E1', 'E2'], 'X'])
        self.assertEqual(state['arrivals'], [first])
        self.assertEqual(self.arrive('X')['next_stop']['occurrence'], 'E1')
        east = self.arrive('E1')['arrival']
        state = self.vehicle_state()
        actual_arrivals = [arrival['occurrence'] for arrival in state['arrivals']]
        self.assertEqual(actual_arrivals, ['A', 'X', 'E1'])
        self.assertEqual(state['speeches'], [speech])
        self.assertEqual(state['commitments'][0]['arrival_id'], east['id'])
        self.assert_api_error(409, 'request_conflict', self.divert, 'R1')
        show_scenario(
            'v6.keep_arrived_prefix',
            {'before': ['A', 'E1', 'E2'], 'arrived': ['A'], 'promise': 'E1', 'candidate': ['A', 'X', 'E1', 'E2']},
            [['A', 'X', 'E1', 'E2'], 'X'], actual,
            ['A', 'X', 'E1'], actual_arrivals,
            ['route/changes.py', 'dispatch/diversions.py', 'driving/load.py', 'driving/progress.py'],
            '手工从候选表扣除已走的 A，预计先到 X，再到承诺原址 E1。',
        )

    def test_same_name_is_not_retention(self):
        self.open_trip()
        self.confirm('E1')
        self.define('ONLY-WEST', ('E2', 'west'))
        same_reference = self.define('MOVED-LOCATION', ('E1', 'west'), ('E2', 'west'))
        for revision, request in [('ONLY-WEST', 'D1'), (same_reference['revision'], 'D2')]:
            result = self.divert(revision, request)
            receipt = result['diversion']
            self.assertEqual((receipt['status'], receipt['reason'], receipt['blocked']),
                             ('conflict', 'promised_stop', ['E1']))
            self.assertEqual(occurrences(result['route']), ['E1', 'E2'])
            self.assertEqual(self.vehicle_state()['next_stop']['station'], 'east')
        self.assertEqual(self.arrive('E1')['arrival']['station'], 'east')

    def test_committed_reply_lost(self):
        self.open_trip()
        target = self.define('ONLY-WEST', ('E2', 'west'))
        lost_confirmation = self.services.relay.drop_next('/confirm_stop', after=True)
        with self.assertRaises(RemoteDisconnected):
            request_json(self.services.vehicle_relay, '/confirm_stop', {
                'trip': 'T', 'occurrence': 'E1', 'request': 'C1',
            })
        self.assertTrue(lost_confirmation.triggered.is_set())
        no_vehicle_fact = self.services.relay.drop_next('/internal/divert_trip', after=False)
        pending = self.divert(target['revision'])
        self.assertTrue(no_vehicle_fact.triggered.is_set())
        self.assertEqual(self.published(request='D1'), pending)
        self.assertEqual(pending['diversion']['status'], 'pending')
        self.assertEqual(occurrences(pending['route']), ['E1', 'E2'])
        self.assertEqual(self.confirm('E2', 'C2')['status'], 'spoken')
        self.assert_api_error(409, 'request_conflict', self.divert, 'R1')
        self.assert_api_error(409, 'diversion_pending', self.divert, 'R1', 'D2')

        lost_decision = self.services.relay.drop_next('/internal/divert_trip', after=True)
        self.assertEqual(self.divert(target['revision']), pending)
        self.assertTrue(lost_decision.triggered.is_set())
        self.services.reopen()
        self.assertEqual(self.published(request='D1'), pending)
        settled = self.divert(target['revision'])
        receipt = settled['diversion']
        self.assertEqual((receipt['status'], receipt['reason'], receipt['blocked']),
                         ('conflict', 'promised_stop', ['E1']))
        self.assertEqual(occurrences(settled['route']), ['E1', 'E2'])
        east = self.arrive('E1')['arrival']
        original = self.confirm('E1')
        state = self.vehicle_state()
        e1_speeches = [speech for speech in state['speeches'] if speech['occurrence'] == 'E1']
        self.assertEqual(e1_speeches, [original['speech']])
        self.assertEqual(state['commitments'][0]['arrival_id'], east['id'])
        self.assertEqual(self.divert(target['revision']), settled)
        show_scenario(
            'v7.wait_for_vehicle_fact',
            {'trip': 'T', 'target': target, 'initial_confirmation': 'C1', 'dropped_replies': ['C1', 'D1']},
            ['pending', 'conflict'], [pending['diversion']['status'], receipt['status']],
            {'arrival': 'E1', 'E1_speech_count': 1},
            {'arrival': east['occurrence'], 'E1_speech_count': len(e1_speeches)},
            ['dispatch/diversions.py', 'dispatch/publication.py', 'onboard/route_changes.py', 'onboard/requests.py'],
            '东口实播先于删停且尚未到站，待查时沿用旧表，查实后须允许东口实到。',
        )

    def test_delayed_request(self):
        gate = AnnouncementGate()
        self.services.reopen(gate)
        self.open_trip()
        target = self.define('ONLY-WEST', ('E2', 'west'))
        with ThreadPoolExecutor(max_workers=1) as executor:
            old_request = executor.submit(self.confirm, 'E1')
            try:
                self.assertTrue(gate.entered.wait(8), 'C1 did not reach the pre-speech gate')
                self.assertEqual(self.confirmation()['status'], 'queued')
                self.assertEqual(self.vehicle_state()['speeches'], [])
                published = self.divert(target['revision'])
                self.assertEqual(published['diversion']['status'], 'effective')
                self.assertEqual(occurrences(published['route']), ['E2'])
                unaffected = self.confirm('E2', 'C2')
                self.assertEqual(unaffected['status'], 'spoken')
            finally:
                gate.release.set()
            late = old_request.result(timeout=10)
        self.assertEqual(late['status'], 'terminated')
        self.assertIsNone(late['speech'])
        self.services.reopen()
        self.assertEqual(self.confirm('E1'), late)
        self.assertEqual(self.divert(target['revision']), published)
        self.assert_api_error(409, 'request_conflict', self.confirm, 'E2')
        self.assert_api_error(409, 'stop_unavailable', self.confirm, 'E1', 'NEW')
        self.assert_api_error(409, 'wrong_arrival', self.arrive, 'E1')
        west = self.arrive('E2')['arrival']
        state = self.vehicle_state()
        self.assertEqual(state['speeches'], [unaffected['speech']])
        self.assertEqual(state['commitments'][0]['arrival_id'], west['id'])
        show_scenario(
            'v8', {'queued': 'E1', 'candidate': target, 'unaffected': 'E2'},
            ['effective', 'terminated'], [published['diversion']['status'], late['status']],
            ['E2'], [speech['occurrence'] for speech in state['speeches']],
            ['dispatch/diversions.py', 'onboard/requests.py', 'onboard/route_changes.py', 'driving/arrivals.py'],
            '按夹具次序先删停再恢复东口首次实播，只有西口本来就有执行资格。',
        )

    def test_effective_reply_lost(self):
        gate = AnnouncementGate()
        self.services.reopen(gate)
        self.open_trip()
        self.define('ONLY-WEST', ('E2', 'west'))
        with ThreadPoolExecutor(max_workers=1) as executor:
            old_request = executor.submit(self.confirm, 'E1')
            try:
                self.assertTrue(gate.entered.wait(8))
                drop = self.services.relay.drop_next('/internal/divert_trip', after=True)
                pending = self.divert('ONLY-WEST')
                self.assertTrue(drop.triggered.is_set())
                self.assertEqual(pending['diversion']['status'], 'pending')
                self.assertEqual(occurrences(self.published(request='D1')['route']), ['E1', 'E2'])
                self.assertEqual(occurrences(self.vehicle_state()['route']), ['E2'])
                self.assertEqual(self.confirm('E2', 'C2')['status'], 'spoken')
            finally:
                gate.release.set()
            self.assertEqual(old_request.result(timeout=10)['status'], 'terminated')
        self.services.reopen()
        self.assertEqual(self.published(request='D1'), pending)
        settled = self.divert('ONLY-WEST')
        self.assertEqual(settled['diversion']['status'], 'effective')
        self.assertEqual(occurrences(settled['route']), ['E2'])
        self.assertEqual([entry['occurrence'] for entry in self.vehicle_state()['speeches']], ['E2'])

    def test_readded_stop_does_not_revive_old_confirmation(self):
        gate = AnnouncementGate()
        self.services.reopen(gate)
        self.open_trip()
        self.define('ONLY-WEST', ('E2', 'west'))
        with ThreadPoolExecutor(max_workers=1) as executor:
            old_request = executor.submit(self.confirm, 'E1')
            try:
                self.assertTrue(gate.entered.wait(8))
                self.assertEqual(self.divert('ONLY-WEST')['diversion']['status'], 'effective')
                self.assertEqual(self.divert('R1', 'D2')['diversion']['status'], 'effective')
            finally:
                gate.release.set()
            self.assertEqual(old_request.result(timeout=10)['status'], 'terminated')
        self.assertEqual(self.vehicle_state()['speeches'], [])
        self.assertEqual(self.confirm('E1', 'C-NEW')['status'], 'spoken')

    def test_diversion_cannot_rewrite_arrived_prefix(self):
        self.open_trip()
        east = self.arrive('E1')['arrival']
        self.define('ONLY-WEST', ('E2', 'west'))
        result = self.divert('ONLY-WEST')
        self.assertEqual(result['diversion']['status'], 'conflict')
        self.assertEqual(result['diversion']['reason'], 'arrived_prefix_conflict')
        self.assertEqual(occurrences(result['route']), ['E1', 'E2'])
        state = self.vehicle_state()
        self.assertEqual(state['arrivals'], [east])
        self.assertEqual(state['next_stop']['occurrence'], 'E2')
        self.assert_api_error(404, 'diversion_not_found', self.published, request='unknown')
