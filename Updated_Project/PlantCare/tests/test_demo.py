import json
import os
from pathlib import Path
import unittest
from unittest.mock import Mock, patch

from aws import demo
from plantcare.contracts import timestamp
from plantcare.profile import default
from plantcare.service import Service
from plantcare.storage import MemoryStore
from tools.scenarios import packet

NOW = timestamp('2026-11-12T15:00:00.000Z')


def request(path='/api/demo/telemetry', method='GET', **kwargs):
    return {'rawPath': path, 'requestContext': {'http': {'method': method}}, **kwargs}


class DemoTests(unittest.TestCase):
    def setUp(self):
        profile = default('simulated')
        store = MemoryStore()
        service = Service(store, Mock(), profile)
        sample = packet(NOW, 1)
        service.handle('telemetry', sample, NOW)
        self.state = store.load('simulated')
        self.state['profile']['mode'] = 'live'
        sample = self.state['engine']['sample']
        sample.update(mode='live', device_id='sensor-01')
        sample['pump']['active_command_id'] = 'private-command-id'
        sample['temperature_c']['secret'] = 'private-extra-field'
        self.state['outbox'] = [{'payload': 'private-outbox'}]

    def test_public_snapshot_returns_only_allowlisted_fields(self):
        with patch.object(demo, 'load_state', return_value=self.state), patch.object(
            demo.time, 'time', return_value=NOW
        ):
            result = demo.handler(request(), None)
        self.assertEqual(result['statusCode'], 200)
        self.assertEqual(result['headers']['cache-control'], 'no-store')
        data = json.loads(result['body'])
        self.assertEqual(set(data), {'mode', 'status', 'condition', 'sample_time', 'fresh_for_s', 'readings', 'thresholds'})
        self.assertEqual(data['thresholds'], {
            'temperature_c': {'low': 16, 'high': 27},
            'humidity_pct': {'low': 50, 'high': None},
            'light_lux': {'low': 1100, 'high': None},
            'soil_pct': {'low': 30, 'high': 80},
        })
        self.assertEqual(data['mode'], 'live')
        self.assertEqual(data['condition'], 'happy')
        self.assertEqual(set(data['readings']), {
            'temperature_c', 'humidity_pct', 'light_lux', 'soil_pct', 'soil_raw',
        })
        self.assertNotIn('private-', result['body'])
        self.assertNotIn('sensor-01', result['body'])

    def test_missing_and_expired_samples_expose_no_readings(self):
        for state, now in [(None, NOW), (self.state, NOW + 1000)]:
            with self.subTest(now=now):
                for mode in demo.MODES:
                    result = demo.snapshot(state, now, mode)
                    self.assertEqual(set(result), {'mode', 'status', 'condition', 'readings', 'thresholds'})
                    self.assertEqual(result['mode'], mode)
                    self.assertEqual((result['status'], result['condition'], result['readings']), ('stale', 'unknown', None))

    def test_static_files_and_rejected_requests_do_not_read_dynamo(self):
        with patch.object(demo, 'load_state') as read:
            for path in ('/', '/app.js', '/style.css'):
                self.assertEqual(demo.handler(request(path), None)['statusCode'], 200)
            for path, method in [
                ('/api/demo/telemetry', 'POST'),
                ('/api/state', 'GET'),
                ('/api/history', 'GET'),
                ('/api/watering', 'GET'),
                ('/api/watering', 'POST'),
                ('/api/request', 'GET'),
            ]:
                self.assertEqual(demo.handler(request(path, method), None)['statusCode'], 404)
            for raw, params in [
                ('mode=demo', {'mode': 'demo'}),
                ('mode=LIVE', {'mode': 'LIVE'}),
                ('mode=live&x=1', {'mode': 'live', 'x': '1'}),
                ('mode=live&mode=simulated', {'mode': 'live,simulated'}),
                ('x=1', {'x': '1'}),
                ('mode=live', None),
                ('', {'mode': 'live'}),
            ]:
                with self.subTest(raw=raw):
                    result = demo.handler(request(rawQueryString=raw, queryStringParameters=params), None)
                    self.assertEqual(result['statusCode'], 400)
            read.assert_not_called()

    def test_mode_query_selects_matching_state_and_labels_response(self):
        simulated = json.loads(json.dumps(self.state))
        simulated['profile']['mode'] = 'simulated'
        states = {'live': self.state, 'simulated': simulated}
        cases = [('live', None, None), ('live', 'mode=live', {'mode': 'live'}),
                 ('simulated', 'mode=simulated', {'mode': 'simulated'})]
        for mode, raw, params in cases:
            with self.subTest(mode=mode, raw=raw), patch.object(
                demo, 'load_state', side_effect=lambda m: states[m]
            ) as read, patch.object(demo.time, 'time', return_value=NOW):
                result = demo.handler(request(rawQueryString=raw, queryStringParameters=params), None)
                self.assertEqual(result['statusCode'], 200)
                self.assertEqual(json.loads(result['body'])['mode'], mode)
                read.assert_called_once_with(mode)

    def test_missing_simulated_state_uses_simulated_profile_and_shows_no_readings(self):
        with patch.object(demo, 'load_state', return_value=None), patch.object(demo.time, 'time', return_value=NOW):
            result = demo.handler(request(rawQueryString='mode=simulated', queryStringParameters={'mode': 'simulated'}), None)
        data = json.loads(result['body'])
        self.assertEqual((data['mode'], data['status'], data['readings']), ('simulated', 'stale', None))
        self.assertEqual(data['thresholds']['soil_pct'], {'low': 30, 'high': 80})

    def test_uncalibrated_live_soil_has_no_thresholds(self):
        with patch.object(demo, 'load_state', return_value=None), patch.object(demo.time, 'time', return_value=NOW):
            data = json.loads(demo.handler(request(), None)['body'])
        self.assertEqual(data['thresholds']['soil_pct'], {'low': None, 'high': None})
        self.assertEqual(data['thresholds']['temperature_c'], {'low': 16, 'high': 27})

    def test_invalid_threshold_values_are_not_published(self):
        profile = json.loads(json.dumps(self.state['profile']))
        profile['thresholds'].update(cold_enter_c='16', hot_enter_c=float('inf'), humidity_enter_pct=500)
        result = demo.public_thresholds(profile)
        self.assertEqual(result['temperature_c'], {'low': None, 'high': None})
        self.assertEqual(result['humidity_pct'], {'low': None, 'high': None})

    def test_read_uses_fixed_state_key_per_mode(self):
        import boto3

        for mode in ('live', 'simulated'):
            with self.subTest(mode=mode):
                client = Mock()
                client.get_item.return_value = {}
                with patch.object(boto3, 'client', return_value=client), patch.dict(
                    os.environ, HISTORY_TABLE='test'
                ):
                    self.assertIsNone(demo.load_state(mode))
                client.get_item.assert_called_once_with(
                    TableName='test', Key={'pk': {'S': mode}, 'sk': {'S': 'STATE'}}, ConsistentRead=True,
                )

    def test_backend_errors_do_not_reach_public_response(self):
        with patch.object(demo, 'load_state', side_effect=RuntimeError('private')), self.assertLogs('aws.demo'):
            result = demo.handler(request(), None)
        self.assertEqual(result['statusCode'], 503)
        self.assertEqual(json.loads(result['body']), {'error': 'telemetry_unavailable'})

    def test_only_demo_get_routes_bypass_jwt(self):
        resources = json.loads(Path('template.yaml').read_text())['Resources']
        self.assertEqual(resources['HttpApi']['Properties']['Auth']['DefaultAuthorizer'], 'Jwt')
        public = resources['Demo']['Properties']
        self.assertEqual(
            {(e['Properties']['Method'], e['Properties']['Path']) for e in public['Events'].values()},
            {('GET', path) for path in ('/', '/app.js', '/style.css', '/api/demo/telemetry')},
        )
        self.assertTrue(all(e['Properties']['Auth'] == {'Authorizer': 'NONE'} for e in public['Events'].values()))
        private = resources['Api']['Properties']['Events']
        self.assertTrue(all('Auth' not in e['Properties'] for e in private.values()))
        self.assertEqual(public['Policies'], [{'Statement': [{
            'Effect': 'Allow', 'Action': 'dynamodb:GetItem',
            'Resource': {'Fn::GetAtt': ['History', 'Arn']},
            'Condition': {'ForAllValues:StringEquals': {'dynamodb:LeadingKeys': ['live', 'simulated']},
                          'Null': {'dynamodb:LeadingKeys': 'false'}},
        }]}])
