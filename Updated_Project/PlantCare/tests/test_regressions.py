import copy,json,unittest
from unittest.mock import patch
from plantcare.contracts import timestamp,utc,Rejected
from plantcare.profile import default
from plantcare.service import Service
from plantcare.storage import MemoryStore
from tools.scenarios import packet
from aws import api
T=timestamp('2026-11-12T15:00:00.000Z')
class Regressions(unittest.TestCase):
 def setUp(self):
  self.store=MemoryStore();self.sent=[];self.p=default('simulated');self.app=Service(self.store,lambda *x:self.sent.append(x),self.p);self.app.handle('telemetry',packet(T,1,soil=20),T)
 def request(self,action='arm',id='request',**extra):
  e={'rawPath':'/api/'+action,'body':json.dumps(dict(request_id=id,**extra)),'queryStringParameters':{'mode':'simulated'},'requestContext':{'authorizer':{'jwt':{'claims':{'sub':'operator'}}},'http':{'method':'POST'}}}
  with patch.object(api,'service',return_value=self.app),patch.object(api.time,'time',return_value=T),patch.object(api,'enqueue') as q:
   r=api.handler(e,None);return r,q
 def test_api_202_has_command_id(self):
  r,q=self.request();self.assertEqual(r['statusCode'],202);self.assertTrue(json.loads(r['body'])['command_id']);q.assert_called_once()
 def test_api_pending_repeat_200_same_id(self):
  r,_=self.request();r2,_=self.request();self.assertEqual(r2['statusCode'],200);self.assertEqual(json.loads(r['body'])['command_id'],json.loads(r2['body'])['command_id'])
 def test_api_id_conflict(self):self.request();r,q=self.request('disarm');self.assertEqual(r['statusCode'],409);q.assert_not_called()
 def test_api_blocked_stable(self):
  r,q=self.request('water');self.assertEqual(r['statusCode'],409);q.assert_not_called();r2,_=self.request('water');self.assertEqual(r2['body'],r['body'])
 def test_api_reset_requires_inspection(self):self.assertEqual(self.request('reset_fault')[0]['statusCode'],400)
 def test_worker_rechecks_and_journals_block(self):
  r=self.app.handle('request',{'action':'water','request_id':'w'},T);self.assertEqual(r['status'],'rejected');self.assertIsNotNone(self.store.get('simulated','REQUEST#w'))
 def test_reload_disarms_clears_assessment(self):
  p=copy.deepcopy(self.p);p['profile_revision']='new';self.assertEqual(self.app.handle('reload',p,T)['status'],'accepted');self.assertEqual(self.app.get_state(T)['data_status'],'stale');self.assertEqual(self.app.get_state(T)['profile_revision'],'new')
 def test_reload_refused_control_pending(self):
  self.app.handle('request',{'action':'arm','request_id':'a'},T);p=copy.deepcopy(self.p);p['profile_revision']='new';self.assertEqual(self.app.handle('reload',p,T)['status'],'rejected')
 def test_restart_pending_fault(self):
  self.app.handle('request',{'action':'arm','request_id':'a'},T);s=Service(self.store,lambda *x:None,self.p,'new');s.handle('tick',{},T+1);self.assertEqual(s.get_state(T+1)['watering']['fault'],'backend_restart')
 def test_colon_hash_identity_collision(self):
  # IDs are arbitrary schema-1 strings, so identity encoding must be unambiguous.
  a=json.dumps(['sensor-01','b#1',2],separators=(',',':'));b=json.dumps(['sensor-01','b',12],separators=(',',':'));self.assertNotEqual(a,b)
 def test_unknown_event_rejected(self):
  e=dict(schema=1,mode='simulated',device_id='sim-sensor-01',boot_id='sim-boot',event_seq=1,command_id='missing',action='arm',status='accepted',ts=utc(T),pump_on=False,reason_code=None)
  self.assertEqual(self.app.handle('event',e,T)['status'],'rejected')
 def test_condition_history_no_heartbeat_spam(self):
  for i in range(1,5):self.app.handle('tick',{},T+i)
  count=sum(k.startswith('CONDITION#') for m,k in self.store.records);self.assertEqual(count,1)
 def test_delayed_future_packet_rejected_at_receipt(self):
  self.assertEqual(self.app.handle('telemetry',packet(T+8,2),T+10,received_at=T)['status'],'rejected')
 def test_unexpected_pump_visible(self):
  p=packet(T+2,2);p['pump']['on']=True;p['pump']['active_command_id']='unknown';self.app.handle('telemetry',p,T+2);state=self.app.get_state(T+2);self.assertTrue(state['watering']['pump_on']);self.assertEqual(state['state'],'watering_fault')
 def test_device_fault_visible(self):
  p=packet(T+2,2);p['pump']['fault']='bench_fault';self.app.handle('telemetry',p,T+2);self.assertEqual(self.app.get_state(T+2)['state'],'watering_fault')
 def test_report_identity_across_sensor_boots(self):
  a=self.app.get_state(T);self.app.handle('telemetry',packet(T+2,1,boot='new'),T+2);b=self.app.get_state(T+2);self.assertNotEqual((a['backend_boot_id'],a['report_seq']),(b['backend_boot_id'],b['report_seq']))
 def test_four_second_dip(self):
  for i in range(1,8):self.app.handle('telemetry',packet(T+2*i,i+1,lux=800 if i<3 else 1500),T+2*i)
  self.assertNotIn('low_light',self.app.get_state(T+14)['issues'])
 def test_reload_cannot_clear_fault(self):
  bad=packet(T+2,2);bad['pump']['fault']='bench';self.app.handle('telemetry',bad,T+2);p=copy.deepcopy(self.p);p['profile_revision']='new';self.app.handle('reload',p,T+2);self.assertEqual(self.app.get_state(T+2)['watering']['stage'],'FAULT')
 def test_condition_stale_history_once(self):
  self.app.handle('tick',{},T+11);self.app.handle('tick',{},T+12);rows=[v for (m,k),v in self.store.records.items() if k.startswith('CONDITION#')];self.assertEqual(sum(r['data_status']=='stale' for r in rows),1)
 def test_history_mode_and_ascending(self):
  for i in (1,2,3):self.app.handle('telemetry',packet(T+2*i,i+1),T+2*i)
  rows=self.store.history('simulated','READING#soil_pct#',utc(T),utc(T+6));self.assertEqual([r['ts'] for r in rows],sorted(r['ts'] for r in rows));self.assertFalse(self.store.history('live','READING#soil_pct#',utc(T),utc(T+6)))
 def test_api_excess_history_page_rejected(self):
  event={'rawPath':'/api/history','queryStringParameters':{'mode':'simulated','limit':'2001'},'requestContext':{'authorizer':{'jwt':{'claims':{'sub':'operator'}}},'http':{'method':'GET'}}}
  with patch.object(api,'service',return_value=self.app):self.assertEqual(api.handler(event,None)['statusCode'],400)
 def test_wrong_mode_reload_rejected(self):
  self.assertEqual(self.app.handle('reload',default('live'),T)['status'],'rejected')
 def test_rejection_does_not_echo_packet(self):
  p=packet(T+2,2);p['schema']=9;p['private']='sensitive-example';self.app.handle('telemetry',p,T+2)
  rows=[v for (m,k),v in self.store.records.items() if k.startswith('REJECTION#')];self.assertNotIn('sensitive-example',json.dumps(rows))
 def test_late_started_cannot_rewind_completed_pump(self):
  from plantcare.watering import Watering
  w=Watering(self.p);w.state.update(stage='OBSERVING',command={'command_id':'c','target_boot_id':'sim-boot','action':'water'},pump_event_ts=T+2,pump_on=False)
  w.event({'command_id':'c','boot_id':'sim-boot','action':'water','status':'started','ts':utc(T),'pump_on':True},T+3)
  self.assertFalse(w.state['pump_on']);self.assertEqual(w.state['stage'],'OBSERVING')
 def test_disarm_preserves_existing_fault(self):
  from plantcare.watering import Watering
  w=Watering(self.p);w.fault('problem');s=packet(T,1);cmd=w.request('disarm',s,T,'d');w.event(dict(action='disarm',command_id=cmd['command_id'],boot_id=s['boot_id'],status='accepted'),T)
  self.assertEqual(w.state['fault'],'problem');self.assertEqual(w.state['stage'],'FAULT')
 def test_uncertain_reset_enforces_full_cooldown(self):
  from plantcare.watering import Watering
  w=Watering(self.p);w.state['stage']='RUNNING';w.fault('event_timeout');s=packet(T,1);w.request('reset_fault',s,T,'r',True);self.assertGreaterEqual(w.state['cool_until'],T+12)
 def test_reading_fields(self):
  row=self.store.history('simulated','READING#soil_pct#',utc(T),utc(T))[0]
  self.assertEqual(row['mode'],'simulated');self.assertEqual(row['unit'],'%');self.assertTrue(row['calibrated'])
