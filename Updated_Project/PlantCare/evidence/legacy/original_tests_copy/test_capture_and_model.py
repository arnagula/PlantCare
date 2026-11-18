import json
from pathlib import Path
import unittest
from unittest.mock import patch

from aws.handler import process_packet
from aws.model import load_demo_model
from tools.log_sensors import samples


class CaptureAndModelTests(unittest.TestCase):
    def test_capture_keeps_invalid_reading_blank(self):
        lines = ['Uptime: 1200 ms', 'Temperature: 23.00 C',
                 'Humidity: INVALID / OFFLINE', 'Light: 0.00 lux',
                 'Soil Moisture (raw): 360']
        row, = samples(lines, 'dry')
        self.assertIsNone(row['humidity_pct'])
        self.assertFalse(row['humidity_pct_valid'])
        self.assertEqual(row['soil_raw'], 360)
        self.assertTrue(row['light_lux_valid'])
        self.assertEqual(list(samples(lines[:-1], 'dry')), [])

    def test_lambda_path_runs_saved_model_in_simulation(self):
        fixture = Path(__file__).resolve().parents[1] / 'contracts' / 'telemetry.json'
        packet = json.loads(fixture.read_text())
        packet.update(mode='simulated', device_id='sim-sensor-01')
        packet['soil'].update(pct=5.0, valid=True, calibrated=True, calibration_id='sim-v1')
        with patch.dict('os.environ', {'ENABLE_SYNTHETIC_MODEL': 'true'}):
            report = process_packet(packet)
        self.assertEqual(report['issues'], load_demo_model().predict_issues(packet))
        self.assertIn('thirsty', report['issues'])
        self.assertEqual(report['watering']['stage'], 'DISARMED')
