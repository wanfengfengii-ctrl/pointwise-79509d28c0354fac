from http.client import RemoteDisconnected

from tests.support import LoopCase
from transport import request_json


class TestOperation(LoopCase):
    def test_confirm_and_arrive(self):
        self.open_trip()
        confirmation = self.confirm('E1')
        self.assertEqual(confirmation['status'], 'spoken')
        self.assertEqual(confirmation['speech']['text'], '将在河桥停靠')
        self.assertEqual(confirmation['speech']['station'], 'east')
        pending = self.vehicle_state()['commitments']
        self.assertEqual([(entry['occurrence'], entry['arrival_id']) for entry in pending], [('E1', None)])
        result = self.arrive('E1')
        self.assertEqual(result['next_stop']['occurrence'], 'E2')
        state = self.vehicle_state()
        self.assertEqual(state['speeches'], [confirmation['speech']])
        self.assertEqual(state['commitments'][0]['arrival_id'], result['arrival']['id'])
        self.assert_api_error(409, 'stop_unavailable', self.confirm, 'E1', 'C2')
        self.assertEqual(self.arrive('E2')['next_stop'], None)

    def test_lost_confirmation_reply(self):
        self.open_trip()
        drop = self.services.relay.drop_next('/confirm_stop', after=True)
        with self.assertRaises(RemoteDisconnected):
            request_json(self.services.vehicle_relay, '/confirm_stop', {
                'trip': 'T', 'occurrence': 'E1', 'request': 'C1',
            })
        self.assertTrue(drop.triggered.is_set())
        original = self.confirmation()
        self.assertEqual(original['status'], 'spoken')
        reached = self.arrive('E1')['arrival']
        self.services.reopen()
        self.assertEqual(self.confirm('E1'), original)
        self.assert_api_error(409, 'request_conflict', self.confirm, 'E2')
        state = self.vehicle_state()
        self.assertEqual(state['speeches'], [original['speech']])
        self.assertEqual(state['commitments'][0]['arrival_id'], reached['id'])
        self.assertEqual(state['next_stop']['occurrence'], 'E2')

    def test_wrong_same_name_arrival(self):
        self.open_trip()
        self.confirm('E1')
        before = self.vehicle_state()
        self.assert_api_error(409, 'wrong_arrival', self.arrive, 'E2')
        self.assertEqual(self.vehicle_state(), before)
        self.assertEqual(before['next_stop']['occurrence'], 'E1')
        self.assertIsNone(before['commitments'][0]['arrival_id'])
        actual = self.arrive('E1')['arrival']
        self.assertEqual(actual['occurrence'], 'E1')
        self.assertEqual(self.vehicle_state()['commitments'][0]['arrival_id'], actual['id'])
