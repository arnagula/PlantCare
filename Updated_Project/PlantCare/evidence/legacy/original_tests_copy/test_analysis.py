import unittest,json
from pathlib import Path
from aws.handler import process_packet
from aws.analysis import classify_rules
from aws.contracts import validate_telemetry
ROOT=Path(__file__).resolve().parents[1]
class Tests(unittest.TestCase):
 def setUp(self):
  self.p=json.loads((ROOT/'contracts/telemetry.json').read_text())
  self.profile=json.loads((ROOT/'profiles/pothos.json').read_text())
 def test_valid_packet(self):self.assertIs(validate_telemetry(self.p),self.p)
 def test_uncalibrated_is_unknown(self):
  r=process_packet(self.p);self.assertEqual(r['state'],'unknown');self.assertEqual(r['data_status'],'uncalibrated')
 def test_too_hot(self):
  self.p['temperature_c']['value']=33
  self.assertIn('too_hot',classify_rules(self.p,self.profile))
 def test_invalid_value_not_zero(self):
  self.p['light_lux']={'value':0,'valid':False}
  with self.assertRaises(ValueError):validate_telemetry(self.p)
 def test_dry_run_cannot_water(self):
  from aws.handler import lambda_handler
  r=lambda_handler(self.p,None)
  self.assertTrue(r['dry_run'])
  self.assertEqual(r['report']['watering']['stage'],'DISARMED')
 def test_sim_identity_rejection(self):
  self.p['device_id']='sim-controller'
  with self.assertRaises(ValueError):process_packet(self.p)
if __name__=='__main__':unittest.main()
