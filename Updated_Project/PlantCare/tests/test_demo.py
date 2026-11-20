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
        with patch.object(demo, 'load_live_state', return_value=self.state), patch.object(
            demo.time, 'time', return_value=NOW
        ):
            result = demo.handler(request(), None)
        self.assertEqual(result['statusCode'], 200)
        self.assertEqual(result['headers']['cache-control'], 'no-store')
        data = json.loads(result['body'])
        self.assertEqual(set(data), {'status', 'condition', 'sample_time', 'fresh_for_s', 'readings'})
        self.assertEqual(data['condition'], 'happy')
        self.assertEqual(set(data['readings']), {
            'temperature_c', 'humidity_pct', 'light_lux', 'soil_pct', 'soil_raw',
        })
        self.assertNotIn('private-', result['body'])
        self.assertNotIn('sensor-01', result['body'])

    def test_missing_and_expired_samples_expose_no_readings(self):
        for state, now in [(None, NOW), (self.state, NOW + 1000)]:
            with self.subTest(now=now):
                self.assertEqual(demo.snapshot(state, now), {
                    'status': 'stale', 'condition': 'unknown', 'readings': None,
                })

    def test_static_files_and_rejected_requests_do_not_read_dynamo(self):
        with patch.object(demo, 'load_live_state') as read:
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
            self.assertEqual(demo.handler(request(rawQueryString='mode=simulated'), None)['statusCode'], 400)
            read.assert_not_called()

    def test_read_uses_fixed_live_state_key(self):
        import boto3

        client = Mock()
        client.get_item.return_value = {}
        with patch.object(boto3, 'client', return_value=client), patch.dict(
            os.environ, HISTORY_TABLE='test'
        ):
            self.assertIsNone(demo.load_live_state())
        client.get_item.assert_called_once_with(
            TableName='test', Key={'pk': {'S': 'live'}, 'sk': {'S': 'STATE'}}, ConsistentRead=True,
        )

    def test_backend_errors_do_not_reach_public_response(self):
        with patch.object(demo, 'load_live_state', side_effect=RuntimeError('private')), self.assertLogs('aws.demo'):
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
            'Condition': {'ForAllValues:StringEquals': {'dynamodb:LeadingKeys': ['live']},
                          'Null': {'dynamodb:LeadingKeys': 'false'}},
        }]}])
