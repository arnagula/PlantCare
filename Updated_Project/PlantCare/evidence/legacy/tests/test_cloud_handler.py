import json
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from aws.handler import lambda_handler


class CloudHandlerTests(unittest.TestCase):
    def test_uncalibrated_live_telemetry_reaches_history_and_condition(self):
        path = Path(__file__).resolve().parents[1] / 'contracts' / 'telemetry.json'
        packet = json.loads(path.read_text())
        packet['profile'] = 'demo'
        packet['sample_interval_s'] = 2
        packet['light_lux'] = {'valid': False, 'value': None}
        db, mqtt = Mock(), Mock()
        boto = SimpleNamespace(client=lambda name, **kwargs: {'dynamodb': db, 'iot-data': mqtt}[name])
        settings = {'EXPECTED_MODE': 'live', 'DRY_RUN': 'false',
                    'HISTORY_TABLE': 'sample-history', 'IOT_DATA_ENDPOINT': 'example.invalid'}
        with patch.dict(sys.modules, {'boto3': boto}), patch.dict('os.environ', settings):
            result = lambda_handler(packet, None)
            with self.assertRaises(ValueError):
                lambda_handler({**packet, 'mode': 'simulated'}, None)
        db.put_item.assert_called_once()
        item = db.put_item.call_args.kwargs['Item']
        self.assertEqual(json.loads(item['telemetry']['S']), packet)
        mqtt.publish.assert_called_once()
        published = mqtt.publish.call_args.kwargs
        self.assertEqual(published['topic'], 'plantcare/team3/pothos1/condition')
        self.assertEqual(json.loads(published['payload']), result['report'])
        self.assertEqual(result['report']['state'], 'unknown')
