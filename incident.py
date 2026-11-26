import json
import unittest
from concurrent.futures import ThreadPoolExecutor
from http.client import RemoteDisconnected

from tests.support import AnnouncementGate, LoopCase
from transport import ApiError, request_json


class BusinessDeviation(AssertionError):
    pass


class IncidentResult(unittest.TextTestResult):
    business_failures = 0

    def addFailure(self, test, error):
        super().addFailure(test, error)
        if issubclass(error[0], BusinessDeviation):
            self.business_failures += 1


def check(case, actual, expected):
    print(json.dumps({'case': case, 'actual': actual, 'expected': expected},
                     ensure_ascii=False, sort_keys=True), flush=True)
    if actual != expected:
        raise BusinessDeviation(case)


def publication(result):
    receipt = result['diversion']
    return [receipt['status'], result['route']['revision'], receipt['reason'], receipt['blocked']]


class RiverLoopIncident(LoopCase):
    def lose_east_reply(self):
        drop = self.services.relay.drop_next('/confirm_stop', after=True)
        with self.assertRaises(RemoteDisconnected):
            request_json(self.services.vehicle_relay, '/confirm_stop', {
                'trip': 'T', 'request': 'C1', 'occurrence': 'E1',
            })
        self.assertTrue(drop.triggered.is_set())
        return self.confirmation()

    def test_spoken_east_must_remain_reachable(self):
        self.open_trip()
        self.define('ONLY-WEST', ('E2', 'west'))
        original = self.lose_east_reply()
        result = self.divert('ONLY-WEST')
        installed = self.vehicle_state()['route']['revision']
        try:
            arrival = self.arrive('E1')['arrival']['station']
        except ApiError as error:
            if (error.status, error.code) != (409, 'wrong_arrival'):
                raise
            arrival = error.code
        state = self.vehicle_state()
        check('spoken_east', {
            'publication': publication(result), 'installed': installed,
            'arrival': arrival, 'original_status': original['status'],
            'replayed': self.confirm('E1'), 'speeches': state['speeches'],
        }, {
            'publication': ['conflict', 'R1', 'promised_stop', ['E1']], 'installed': 'R1',
            'arrival': 'east', 'original_status': 'spoken',
            'replayed': original, 'speeches': [original['speech']],
        })

    def test_unconfirmed_diversion_must_not_publish(self):
        self.open_trip()
        self.define('ONLY-WEST', ('E2', 'west'))
        self.lose_east_reply()
        drop = self.services.relay.drop_next('/internal/divert_trip', after=False)
        first = self.divert('ONLY-WEST')
        self.assertTrue(drop.triggered.is_set())
        before = self.published(request='D1')
        installed = self.vehicle_state()['route']['revision']
        unaffected = self.confirm('E2', 'C2')['status']
        self.services.reopen()
        reopened = self.published(request='D1')
        settled = self.divert('ONLY-WEST')
        check('unknown_diversion', [publication(first), publication(before), installed,
                                   unaffected, publication(reopened), publication(settled)],
              [['pending', 'R1', None, []], ['pending', 'R1', None, []], 'R1', 'spoken',
               ['pending', 'R1', None, []], ['conflict', 'R1', 'promised_stop', ['E1']]])

    def divert_while_east_is_queued(self, revision, *calls):
        gate = AnnouncementGate()
        self.services.reopen(gate)
        self.open_trip()
        self.define(revision, *calls)
        with ThreadPoolExecutor(max_workers=1) as executor:
            waiting = executor.submit(self.confirm, 'E1')
            try:
                self.assertTrue(gate.entered.wait(8), 'C1 did not reach the announcement gate')
                self.assertEqual(self.confirmation()['status'], 'queued')
                result = self.divert(revision)
                other = self.confirm('E2', 'C2')['status']
            finally:
                gate.release.set()
            late = waiting.result(timeout=10)
        self.services.reopen()
        readback = self.confirm('E1')
        speeches = [row['occurrence'] for row in self.vehicle_state()['speeches']]
        return [publication(result), other, late['status'], readback == late, speeches]

    def test_deleted_east_must_not_announce(self):
        actual = self.divert_while_east_is_queued('ONLY-WEST', ('E2', 'west'))
        check('late_east', actual, [['effective', 'ONLY-WEST', None, []],
                                    'spoken', 'terminated', True, ['E2']])

    def test_retained_east_can_move(self):
        actual = self.divert_while_east_is_queued('MOVE', ('E2', 'west'), ('E1', 'east'))
        check('retained_east', actual, [['effective', 'MOVE', None, []],
                                        'spoken', 'spoken', True, ['E2', 'E1']])


if __name__ == '__main__':
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(RiverLoopIncident)
    result = unittest.TextTestRunner(verbosity=2, resultclass=IncidentResult).run(suite)
    if result.business_failures and not result.errors and result.business_failures == len(result.failures):
        print('RIVER_LOOP_STOP_PROMISE_BROKEN', flush=True)
    raise SystemExit(0 if result.wasSuccessful() else 1)
