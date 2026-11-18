"""Spec-derived tests. Run: python test_spec_audit.py /path/to/PlantCare_Team3_Starter
No AWS connections; SDK fakes model the current unconditional PutItem and retained publish.
Failures intentionally expose gaps in the supplied code; they are not marked expected.
"""
import copy, datetime, io, json, os, sys, unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
ROOT=Path(sys.argv[1]).resolve(); sys.path.insert(0,str(ROOT))
from aws.contracts import validate_telemetry
from aws.handler import process_packet, lambda_handler, PROFILE
from tools.log_sensors import samples
NOW=datetime.datetime(2026,11,12,15,0,tzinfo=datetime.timezone.utc)
def stamp(t):return t.isoformat(timespec='milliseconds').replace('+00:00','Z')
def packet():
 p=json.loads((ROOT/'contracts/telemetry.json').read_text());p.update(ts=stamp(NOW),seq=1,profile='demo',sample_interval_s=2)
 p['humidity_pct']['value']=60
 p['soil'].update(pct=50,valid=True,calibrated=True,calibration_id='sim-qualified')
 return p
def profile():
 p=copy.deepcopy(PROFILE);p['soil'].update(dry_enter_pct=30,dry_exit_pct=40,wet_exit_pct=70,wet_enter_pct=80)
 return p
class Clock(datetime.datetime):
 @classmethod
 def now(cls,tz=None):return NOW if tz else NOW.replace(tzinfo=None)
class Base(unittest.TestCase):
 def setUp(self):
  self.env=patch.dict(os.environ,{'ENABLE_SYNTHETIC_MODEL':'false','DRY_RUN':'true','EXPECTED_MODE':'live'});self.env.start()
  self.clock=patch('aws.handler.datetime.datetime',Clock);self.clock.start()
  self.addCleanup(self.env.stop);self.addCleanup(self.clock.stop)
 def assess(self,p=None):return process_packet(p or packet(),profile())
class Contracts(Base):pass
def add_bad(name,mutate):
 def test(self):
  p=packet();mutate(p)
  with self.assertRaises(ValueError,msg='Malformed packet accepted'):validate_telemetry(p)
 setattr(Contracts,'test_'+name,test)
for key in ['profile','uptime_ms','sample_interval_s','pump']:
 add_bad('missing_'+key,lambda p,k=key:p.pop(k))
for key in ['raw','raw_valid','calibration_id']:
 add_bad('soil_missing_'+key,lambda p,k=key:p['soil'].pop(k))
for name,key,value in [('schema_bool','schema',True),('schema_unknown','schema',2),('bad_mode','mode','test'),('seq_bool','seq',True),('seq_zero','seq',0),('seq_float','seq',2.5),('empty_id','device_id',''),('long_id','boot_id','x'*65),('unknown_profile','profile','turbo'),('negative_uptime','uptime_ms',-1),('zero_interval','sample_interval_s',0),('nonnumeric_interval','sample_interval_s','two'),('pump_not_object','pump',0),('noncanonical_utc','ts','2026-11-12T15:00:00+00:00'),('nonutc','ts','2026-11-12T10:00:00.000-05:00'),('naive_timestamp','ts','2026-11-12T15:00:00.000'),('oversize_payload','padding','x'*4096)]:
 add_bad(name,lambda p,k=key,v=value:p.update({k:v}))
for name,key,val in [('negative_raw','raw',-1),('string_raw','raw','bad'),('raw_valid_not_bool','raw_valid',1),('long_calibration_id','calibration_id','x'*65),('soil_nan','pct',float('nan')),('soil_above_100','pct',101),('soil_bool','pct',True)]:
 add_bad(name,lambda p,k=key,v=val:p['soil'].update({k:v}))
add_bad('invalid_soil_nonnull_pct',lambda p:p['soil'].update(valid=False,pct=50))
add_bad('invalid_raw_nonnull',lambda p:p['soil'].update(raw_valid=False,raw=360))
add_bad('pump_negative_cooldown',lambda p:p['pump'].update(cooldown_remaining_s=-1))
for name,key,val in [('temperature_nan','temperature_c',float('nan')),('temperature_infinity','temperature_c',float('inf')),('humidity_above_100','humidity_pct',101),('negative_lux','light_lux',-1),('bool_temperature','temperature_c',True)]:
 add_bad(name,lambda p,k=key,v=val:p[k].update(value=v))
add_bad('invalid_metric_missing_value',lambda p:p.update(light_lux={'valid':False}))
add_bad('invalid_metric_nonnull',lambda p:p.update(light_lux={'valid':False,'value':0}))
class ValidContracts(Base):
 def test_valid(self):validate_telemetry(packet())
 def test_unknown_small_extra_ignored(self):
  p=packet();p['extra']='ok';validate_telemetry(p)
 def test_invalid_metric_null(self):
  p=packet();p['light_lux']={'valid':False,'value':None};validate_telemetry(p)
 def test_uncalibrated_null(self):
  p=packet();p['soil'].update(pct=None,valid=False,calibrated=False,calibration_id=None);validate_telemetry(p)
class Behavior(Base):
 def test_happy_baseline(self):self.assertEqual(self.assess()['state'],'happy')
 def test_first_low_light_sample_does_not_activate(self):
  p=packet();p['light_lux']['value']=800;self.assertNotIn('low_light',self.assess(p)['issues'])
 def test_four_second_dip_no_alert(self):
  for i in range(3):
   p=packet();p.update(seq=i+1,ts=stamp(NOW-datetime.timedelta(seconds=4-2*i)));p['light_lux']['value']=800
   self.assertNotIn('low_light',self.assess(p)['issues'])
 def test_twelve_second_low_light_alert(self):
  for i in range(7):
   p=packet();p.update(seq=i+1,ts=stamp(NOW-datetime.timedelta(seconds=12-2*i)));p['light_lux']['value']=800;r=self.assess(p)
  self.assertIn('low_light',r['issues'])
 def test_hysteresis_gap_holds(self):
  for i in range(7):
   p=packet();p.update(seq=i+1,ts=stamp(NOW-datetime.timedelta(seconds=12-2*i)));p['light_lux']['value']=800;self.assess(p)
  p.update(seq=8,ts=stamp(NOW+datetime.timedelta(seconds=2)));p['light_lux']['value']=1200
  self.assertIn('low_light',self.assess(p)['issues'])
 def test_recovery_not_immediate(self):
  for i in range(7):
   p=packet();p.update(seq=i+1,ts=stamp(NOW-datetime.timedelta(seconds=12-2*i)));p['light_lux']['value']=800;self.assess(p)
  p.update(seq=8,ts=stamp(NOW+datetime.timedelta(seconds=2)));p['light_lux']['value']=1400
  self.assertIn('low_light',self.assess(p)['issues'])
 def test_night_suppression(self):
  p=packet();p['ts']='2026-11-12T03:00:00.000Z';p['light_lux']['value']=0
  with patch.object(Clock,'now',return_value=datetime.datetime.fromisoformat(p['ts'].replace('Z','+00:00'))):
   self.assertNotIn('low_light',self.assess(p)['issues'])
 def test_stale_cannot_be_happy(self):
  p=packet();p['ts']=stamp(NOW-datetime.timedelta(hours=1));r=self.assess(p)
  self.assertEqual((r['state'],r['data_status']),('unknown','stale'))
 def test_future_more_than_five_seconds_rejected(self):
  p=packet();p['ts']=stamp(NOW+datetime.timedelta(seconds=6))
  with self.assertRaises(ValueError):self.assess(p)
 def test_demo_freshness_ten_seconds(self):self.assertEqual(self.assess()['freshness_timeout_s'],10)
 def test_invalid_fields_identified(self):
  p=packet();p['light_lux']={'value':None,'valid':False};self.assertIn('light_lux',self.assess(p)['invalid_fields'])
 def test_issue_details_present(self):
  p=packet();p['temperature_c']['value']=33;r=self.assess(p)
  self.assertTrue(r['details'],'Active issue has no reading/threshold/recommendation')
 def test_multiple_issues_preserved(self):
  p=packet();p['humidity_pct']['value']=30;p['light_lux']['value']=800
  # Only record behavior; PDF does not specify this relative priority.
  self.assertEqual(set(self.assess(p)['issues']),{'low_light','low_humidity'})
 def test_low_humidity_mild(self):
  p=packet();p['humidity_pct']['value']=30;self.assertEqual(self.assess(p)['mood'],'regular')
 def test_no_high_humidity_rule(self):
  p=packet();p['humidity_pct']['value']=99;self.assertEqual(self.assess(p)['issues'],[])
 def test_no_excess_light_rule(self):
  p=packet();p['light_lux']['value']=100000;self.assertEqual(self.assess(p)['issues'],[])
 def test_other_valid_issues_survive_invalid_sensor(self):
  p=packet();p['temperature_c']['value']=33;p['light_lux']={'value':None,'valid':False};self.assertIn('too_hot',self.assess(p)['issues'])
 def test_unqualified_profile_not_happy_for_dry_claim(self):
  p=packet();p['soil']['pct']=0;r=process_packet(p,PROFILE)
  self.assertNotEqual(r['state'],'happy','No qualified soil thresholds exist')
 def test_invalid_profile_thresholds_rejected(self):
  prof=profile();prof['soil'].update(dry_enter_pct=90,dry_exit_pct=40,wet_exit_pct=70,wet_enter_pct=80)
  with self.assertRaises(ValueError):process_packet(packet(),prof)
 def test_pump_on_not_reported_off(self):
  p=packet();p['pump'].update(on=True,armed=True,active_command_id='dose-1')
  self.assertTrue(self.assess(p)['watering']['pump_on'])
 def test_pump_fault_visible(self):
  p=packet();p['pump']['fault']='interrupted_run';self.assertEqual(self.assess(p)['state'],'watering_fault')
 def test_reason_ascii_length(self):
  r=self.assess();self.assertLessEqual(len(r['reason']),119);self.assertTrue(r['reason'].isascii())
class FakeAWS:
 def __init__(self):self.rows={};self.publications=[];self.writes=[];self.fail_publish=False
 def client(self,name,**kw):return self
 def put_item(self,**kw):
  self.writes.append(copy.deepcopy(kw));i=kw['Item'];self.rows[(i['device']['S'],i['sample']['S'])]=copy.deepcopy(i)
 def publish(self,**kw):
  if self.fail_publish:raise RuntimeError('simulated MQTT outage')
  self.publications.append(copy.deepcopy(kw))
class Cloud(Base):
 def setUp(self):
  super().setUp();self.aws=FakeAWS()
  self.sdk=patch.dict(sys.modules,{'boto3':self.aws});self.sdk.start();self.addCleanup(self.sdk.stop)
  self.deploy=patch.dict(os.environ,{'DRY_RUN':'false','HISTORY_TABLE':'test','IOT_DATA_ENDPOINT':'example.invalid'});self.deploy.start();self.addCleanup(self.deploy.stop)
 def test_retained_qos1_correct_live_topic(self):
  lambda_handler(packet(),None);pub=self.aws.publications[0]
  self.assertEqual((pub['topic'],pub['qos'],pub['retain']),('plantcare/team3/pothos1/condition',1,True))
 def test_mode_mismatch_no_side_effects(self):
  p=packet();p['mode']='simulated'
  with self.assertRaises(ValueError):lambda_handler(p,None)
  self.assertFalse(self.aws.writes or self.aws.publications)
 def test_duplicate_one_history_identity(self):
  p=packet();lambda_handler(p,None);lambda_handler(p,None);self.assertEqual(len(self.aws.rows),1)
 def test_old_duplicate_cannot_restore_previous_condition(self):
  old=packet();lambda_handler(old,None);new=packet();new['seq']=2;lambda_handler(new,None);lambda_handler(old,None)
  self.assertEqual(json.loads(self.aws.publications[-1]['payload'])['source']['seq'],2)
 def test_same_identity_changed_payload_cannot_overwrite(self):
  p=packet();lambda_handler(p,None);before=copy.deepcopy(self.aws.rows);p['temperature_c']['value']=40;lambda_handler(p,None)
  self.assertEqual(self.aws.rows,before)
 def test_old_sample_cannot_replace_retained_latest(self):
  p=packet();p['seq']=2;lambda_handler(p,None);p.update(seq=1,ts=stamp(NOW-datetime.timedelta(seconds=2)));lambda_handler(p,None)
  latest=json.loads(self.aws.publications[-1]['payload']);self.assertEqual(latest['source']['seq'],2)
 def test_receipt_time_stored_separately(self):
  lambda_handler(packet(),None);self.assertIn('received_at',self.aws.writes[0]['Item'])
 def test_report_identity_unique_across_sensor_boots(self):
  p=packet();r1=lambda_handler(p,None)['report'];p['boot_id']='boot-new';r2=lambda_handler(p,None)['report']
  self.assertNotEqual((r1['backend_boot_id'],r1['report_seq']),(r2['backend_boot_id'],r2['report_seq']))
 def test_simulation_topic_isolated(self):
  p=packet();p.update(mode='simulated',device_id='sim-sensor-01')
  with patch.dict(os.environ,{'EXPECTED_MODE':'simulated'}):lambda_handler(p,None)
  self.assertEqual(self.aws.publications[-1]['topic'],'plantcare/team3/sim/pothos1/condition')
 def test_mqtt_failure_then_retry_one_stored_identity(self):
  p=packet();self.aws.fail_publish=True
  with self.assertRaises(RuntimeError):lambda_handler(p,None)
  self.aws.fail_publish=False;lambda_handler(p,None)
  self.assertEqual(len(self.aws.rows),1);self.assertEqual(len(self.aws.publications),1)
class Logger(Base):
 def test_valid_complete_row(self):
  rows=list(samples(['Uptime: 1200 ms','Temperature: 23.00 C','Humidity: 60.00 %','Light: 0.00 lux','Soil Moisture (raw): 360'],'dry'))
  self.assertEqual(len(rows),1);self.assertEqual(rows[0]['soil_raw'],360)
 def test_soil_disconnected_row_preserved(self):
  rows=list(samples(['Uptime: 1200 ms','Temperature: 23.00 C','Humidity: 60.00 %','Light: 0.00 lux','Soil Moisture: INVALID / OFFLINE'],'dry'))
  self.assertEqual(len(rows),1,'Actual firmware soil failure label causes entire sample to vanish')
  self.assertFalse(rows[0]['soil_raw_valid']);self.assertIsNone(rows[0]['soil_raw'])
 def test_fractional_raw_not_truncated(self):
  rows=list(samples(['Uptime: 1200 ms','Temperature: 23.00 C','Humidity: 60.00 %','Light: 0.00 lux','Soil Moisture (raw): 360.9'],'dry'))
  self.assertFalse(rows[0]['soil_raw_valid'])
if __name__=='__main__':
 suite=unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__]);stream=io.StringIO()
 result=unittest.TextTestRunner(stream=stream,verbosity=2).run(suite)
 output=Path(__file__).resolve().parent
 (output/'spec_test_results.txt').write_text(stream.getvalue())
 summary={'run':result.testsRun,'passed':result.testsRun-len(result.failures)-len(result.errors),'failures':len(result.failures),'errors':len(result.errors),'failed_tests':[t.id() for t,_ in result.failures],'error_tests':[t.id() for t,_ in result.errors]}
 (output/'spec_test_summary.json').write_text(json.dumps(summary,indent=2))
 print(json.dumps(summary,indent=2));sys.exit(not result.wasSuccessful())
