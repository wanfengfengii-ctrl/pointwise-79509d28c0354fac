from tests.support import LoopCase, occurrences, show_scenario


class TestReview(LoopCase):
    def test_receipts_and_empty_turn(self):
        self.open_trip()
        speeches = [self.confirm('E2', 'C2')['speech'], self.confirm('E1', 'C1')['speech'],
                    self.confirm('E1', 'C3')['speech']]
        east = self.arrive('E1')['arrival']
        west = self.arrive('E2')['arrival']
        self.assertEqual(self.vehicle('/end_trip', trip='T'), {
            'trip': 'T', 'status': 'closed', 'arrival_count': 2,
        })
        review = self.vehicle('/read_review', trip='T')
        self.assertEqual((review['commitment_count'], review['fulfilled_count']), (3, 3))
        self.assertEqual(review['arrivals'], [east, west])
        self.assertEqual([entry['speech'] for entry in review['coverage']],
                         [speeches[1], speeches[2], speeches[0]])
        self.assertEqual([entry['arrival'] for entry in review['coverage']], [east, east, west])
        self.assertEqual([entry['commitment']['request'] for entry in review['coverage']], ['C1', 'C3', 'C2'])
        self.services.reopen()
        self.assertEqual(self.vehicle('/read_review', trip='T'), review)
        self.assertEqual(self.confirm('E1')['speech'], speeches[1])
        self.assertEqual(self.vehicle('/end_trip', trip='T')['status'], 'closed')

        self.open_trip('quiet')
        first = self.arrive('E1', 'quiet')['arrival']
        last = self.arrive('E2', 'quiet')['arrival']
        self.vehicle('/end_trip', trip='quiet')
        quiet = self.vehicle('/read_review', trip='quiet')
        self.assertIs(type(quiet['commitment_count']), int)
        self.assertEqual((quiet['commitment_count'], quiet['fulfilled_count']), (0, 0))
        self.assertEqual(quiet['coverage'], [])
        self.assertEqual(quiet['arrivals'], [first, last])

    def test_empty_stop_table(self):
        route = self.define('EMPTY')
        opened = self.open_trip('empty', 'EMPTY')
        self.assertEqual(opened['route'], route)
        self.assertEqual(route['calls'], [])
        self.assertIsNone(opened['next_stop'])
        self.assert_api_error(409, 'review_not_ready', self.vehicle, '/read_review', trip='empty')
        self.assert_api_error(409, 'stop_unavailable', self.confirm, 'E1', trip='empty')
        self.assertEqual(self.vehicle('/end_trip', trip='empty')['arrival_count'], 0)
        review = self.vehicle('/read_review', trip='empty')
        self.assertEqual(review['arrivals'], [])
        self.assertEqual(review['coverage'], [])
        self.assertEqual(review['commitment_count'], 0)
        self.services.reopen()
        self.assertEqual(self.vehicle('/read_review', trip='empty'), review)

    def test_review_before_close(self):
        self.open_trip()
        self.arrive('E1')
        self.assertEqual(self.vehicle_state()['commitments'], [])
        before = self.vehicle_state()
        self.assert_api_error(409, 'stops_remaining', self.vehicle, '/end_trip', trip='T')
        self.assert_api_error(409, 'review_not_ready', self.vehicle, '/read_review', trip='T')
        self.assertEqual(self.vehicle_state(), before)
        self.assertEqual(before['next_stop']['occurrence'], 'E2')
        self.arrive('E2')
        self.assertEqual(self.vehicle('/end_trip', trip='T')['status'], 'closed')
        review = self.vehicle('/read_review', trip='T')
        self.assertEqual([entry['occurrence'] for entry in review['arrivals']], ['E1', 'E2'])
        self.assertEqual(review['commitment_count'], 0)

    def test_day_of_service(self):
        base = self.define('DAY', ('A', 'center'), ('E1', 'east'), ('E2', 'west'))
        self.assertEqual(self.open_trip(revision='DAY')['route'], base)
        arrivals = [self.arrive('A')['arrival']]
        west = self.confirm('E2', 'WEST')['speech']
        east = self.confirm('E1', 'EAST')['speech']
        candidate = self.define('MARKET', ('A', 'center'), ('X', 'market'), ('E1', 'east'), ('E2', 'west'))
        switched = self.divert('MARKET')
        self.assertEqual(switched['diversion']['status'], 'effective')
        status = self.published(request='D1')
        vehicle = self.vehicle_state()
        expected = {'order': ['A', 'X', 'E1', 'E2'], 'next': 'X', 'revision': 'MARKET'}
        actual = {
            'order': occurrences(status['route']), 'next': vehicle['next_stop']['occurrence'],
            'revision': vehicle['route']['revision'],
        }
        self.assertEqual(actual, expected)
        for stop in ('X', 'E1', 'E2'):
            arrivals.append(self.arrive(stop)['arrival'])
        self.assertEqual(self.vehicle('/end_trip', trip='T')['arrival_count'], 4)
        before_reopen = self.vehicle('/read_review', trip='T')
        self.services.reopen()
        review = self.vehicle('/read_review', trip='T')
        self.assertEqual(review, before_reopen)
        self.assertEqual(review['arrivals'], arrivals)
        self.assertEqual([entry['speech'] for entry in review['coverage']], [east, west])
        self.assertEqual([entry['arrival'] for entry in review['coverage']], arrivals[2:])
        downstream_expected = {
            'arrived': ['A', 'X', 'E1', 'E2'], 'coverage_order': ['EAST', 'WEST'], 'fulfilled': 2,
        }
        downstream_actual = {
            'arrived': [row['occurrence'] for row in review['arrivals']],
            'coverage_order': [row['speech']['request'] for row in review['coverage']],
            'fulfilled': review['fulfilled_count'],
        }
        self.assertEqual(review['commitment_count'], 2)
        self.assertEqual(downstream_actual, downstream_expected)
        show_scenario(
            'v9.actual_order_and_sources',
            {'base': base, 'candidate': candidate, 'arrived_before': ['A'], 'speech_order': ['WEST', 'EAST']},
            expected, actual, downstream_expected, downstream_actual,
            ['route/loops.py', 'dispatch/diversions.py', 'driving/arrivals.py', 'driving/end_trip.py',
             'review/coverage.py', 'review/summaries.py'],
            '按候选表从 A 后开始接着行车，东口在西口前实到，手工配回各自原播报。',
        )
