import copy
import unittest
from plantcare import contracts as c
from plantcare.profile import default,validate,moisture
from plantcare.engine import Engine,RULES
from plantcare.watering import Watering
from plantcare.service import Service
from plantcare.storage import MemoryStore,Conflict
from tools.scenarios import packet
from tools.log_sensors import samples
T=c.timestamp('2026-11-12T15:00:00.000Z')

class Contracts(unittest.TestCase):
    def test_valid(self): c.telemetry(packet(T,1),now=T)
    def test_extra_allowed(self):
        p=packet(T,1);p['extra']='ok';c.telemetry(p)
    def test_exact_future_boundary(self): c.telemetry(packet(T+5,1),now=T)
    def test_null_validity(self): c.telemetry(packet(T,1,temp=None,rh=None,lux=None,soil=None))
    def test_status(self): c.status(dict(schema=1,mode='live',client='sensor',boot_id='b',status='offline',ts=None))
    def test_command(self): c.command(dict(schema=1,mode='live',command_id='x',action='water',target_boot_id='b',config_id='c',issued_at=c.utc(T),expires_at=c.utc(T+10),duration_ms=1,reason='manual'))

# Separate test cases preserve each missing-field/boundary result in evidence.
def missing_test(path):
    def test(self):
        p=packet(T,1);obj=p
        for k in path[:-1]: obj=obj[k]
        del obj[path[-1]]
        with self.assertRaises(c.Rejected):c.telemetry(p)
    return test
for key in packet(T,1): setattr(Contracts,'test_missing_'+key,missing_test([key]))
for group in ('soil','pump','temperature_c','humidity_pct','light_lux'):
    for key in packet(T,1)[group]:setattr(Contracts,'test_missing_'+group+'_'+key,missing_test([group,key]))

def bad_test(path,value):
    def test(self):
        p=packet(T,1);obj=p
        for k in path[:-1]: obj=obj[k]
        obj[path[-1]]=value
        with self.assertRaises(c.Rejected):c.telemetry(p,now=T)
    return test
BAD=[(['schema'],True),(['seq'],True),(['seq'],0),(['uptime_ms'],-1),(['profile'],'x'),(['sample_interval_s'],0),(['ts'],c.utc(T+6)),(['ts'],'2026-11-12T15:00:00Z'),(['ts'],'2026-11-12T15:00:00.000+00:00'),(['boot_id'],'x'*65),(['temperature_c','value'],float('nan')),(['humidity_pct','value'],101),(['light_lux','value'],-1),(['soil','raw'],2.4),(['soil','raw_valid'],'yes'),(['soil','pct'],101),(['soil','calibrated'],False),(['pump','on'],1),(['pump','cooldown_remaining_s'],-1),(['extra'],'x'*4096)]
for i,(path,value) in enumerate(BAD):setattr(Contracts,'test_bad_%02d'%i,bad_test(path,value))

class Profiles(unittest.TestCase):
    def test_live_unqualified(self): self.assertFalse(validate(default())['watering']['qualified'])
    def test_sim_qualified(self): self.assertTrue(validate(default('simulated'))['watering']['qualified'])
    def test_conversion_clips(self):
        p=default('simulated');self.assertEqual(moisture(0,p),0);self.assertEqual(moisture(1000,p),100);self.assertEqual(moisture(500,p),50)
    def test_reversed_raw_supported(self):
        p=default('simulated');p['soil'].update(raw_dry=700,raw_wet=300);validate(p);self.assertEqual(moisture(600,p),25)

def profile_bad(section,key,value):
    def test(self):
        p=default('simulated');p[section][key]=value
        with self.assertRaises(c.Rejected):validate(p)
    return test
for i,(section,key,value) in enumerate([('soil','dry_samples',19),('soil','wet_samples',19),('soil','raw_noise',200),('soil','noise_pct',.5),('soil','raw_wet',300),('soil','dry_enter_pct',40),('soil','evidence_approved',False),('watering','evidence_approved',False),('watering','dose_ms',4000),('watering','dose_ms',0),('watering','min_rise_pct',1),('watering','demo_response_wait_s',5),('watering','demo_cooldown_s',5)]):setattr(Profiles,'test_gate_%02d'%i,profile_bad(section,key,value))

VALUES={'thirsty':('soil',20,30,35,50),'too_wet':('soil',90,80,75,50),'low_light':('lux',800,1100,1200,1500),'too_cold':('temp',15,16,16.5,23),'too_hot':('temp',28,27,26.5,23),'low_humidity':('rh',40,50,52,60)}
class Rules(unittest.TestCase):
    def setUp(self):self.p=default('simulated');self.e=Engine(self.p)
    def test_gap_interrupts(self):
        for n,t in enumerate([0,2,4,10,12,14],1): r=self.e.update(packet(T+t,n,lux=800),T+t)
        self.assertNotIn('low_light',r['issues'])
    def test_duplicate_no_advance(self):
        p=packet(T,1,lux=800);self.e.update(p,T)
        with self.assertRaises(c.Rejected):self.e.update(p,T+10)
    def test_stale(self):
        self.e.update(packet(T,1),T);self.assertEqual(self.e.assess(T+10)['data_status'],'ok');self.assertEqual(self.e.assess(T+10.01)['data_status'],'stale')
    def test_invalid_other_issue_continues(self):
        for i in range(6):r=self.e.update(packet(T+2*i,i+1,temp=None,lux=800),T+2*i)
        self.assertEqual(r['state'],'unknown');self.assertIn('low_light',r['issues']);self.assertIn('temperature_c',r['invalid_fields'])
    def test_night_transition(self):
        start=c.timestamp('2026-11-13T00:59:48.000Z')
        for i in range(6):r=self.e.update(packet(start+2*i,i+1,lux=800),start+2*i)
        self.assertIn('low_light',r['issues']);self.assertNotIn('low_light',self.e.assess(start+12)['issues'])
    def test_daylight_new_timer(self):
        start=c.timestamp('2026-11-12T12:59:58.000Z')
        for i in range(6):r=self.e.update(packet(start+2*i,i+1,lux=800),start+2*i)
        self.assertNotIn('low_light',r['issues'])
    def test_unqualified_claim(self):
        p=default();e=Engine(p);s=packet(T,1);s.update(mode='live',device_id='sensor-01');r=e.update(s,T);self.assertEqual(r['data_status'],'uncalibrated')
    def test_no_high_humidity_light(self):
        for i in range(6):r=self.e.update(packet(T+2*i,i+1,rh=100,lux=100000),T+2*i)
        self.assertEqual(r['issues'],[])

def rule_test(code,normal=False):
    def test(self):
        key,enter,equal,gap,clear=VALUES[code]; profile='normal' if normal else 'demo';step=60 if normal else 2;duration=self.p['timing'][profile][RULES[code][4]]
        for i,t in enumerate(range(0,duration+1,step),1):
            r=self.e.update(packet(T+t,i,profile=profile,**{key:enter}),T+t)
            self.assertEqual(code in r['issues'],t>=duration)
        if normal:return
        for t in (12,14,16):r=self.e.update(packet(T+t,100+t,**{key:gap}),T+t);self.assertIn(code,r['issues'])
        for t in (18,20,22,24):
            r=self.e.update(packet(T+t,100+t,**{key:clear}),T+t)
            self.assertEqual(code in r['issues'],t<24)
    return test
for code in VALUES:
    setattr(Rules,'test_demo_'+code,rule_test(code));setattr(Rules,'test_normal_'+code,rule_test(code,True))
    def equality(self,code=code):
        key,_,v,_,_=VALUES[code]
        for i in range(7):r=self.e.update(packet(T+2*i,i+1,**{key:v}),T+2*i)
        self.assertNotIn(code,r['issues'])
    setattr(Rules,'test_equality_'+code,equality)

class Durability(unittest.TestCase):
    def setUp(self):
        self.store=MemoryStore();self.p=default('simulated');self.sent=[];self.s=Service(self.store,lambda *a:self.sent.append(a),self.p)
    def test_five_rows_receipt(self):
        self.s.handle('telemetry',packet(T,1),T+1)
        rows=[v for (m,k),v in self.store.records.items() if k.startswith('READING#')]
        self.assertEqual(len(rows),5);self.assertTrue(all(x['received_at']==c.utc(T+1) for x in rows))
    def test_duplicate_does_not_republish(self):
        p=packet(T,1);self.s.handle('telemetry',p,T);n=len(self.sent);self.assertEqual(self.s.handle('telemetry',p,T+1)['status'],'duplicate');self.assertEqual(len(self.sent),n)
    def test_conflicting_duplicate_immutable(self):
        self.s.handle('telemetry',packet(T,1),T);self.assertEqual(self.s.handle('telemetry',packet(T,1,lux=800),T+1)['status'],'rejected');self.assertEqual(self.s.get_state(T+1)['values']['light_lux']['value'],1500)
    def test_old_sample_no_rollback(self):
        self.s.handle('telemetry',packet(T+2,2),T+2);self.s.handle('telemetry',packet(T,1),T+2);self.assertEqual(self.s.get_state(T+2)['source']['seq'],2)
    def test_outbox_recovers(self):
        def fail(*args):raise RuntimeError('network')
        self.s.publish=fail
        with self.assertRaises(RuntimeError):self.s.handle('telemetry',packet(T,1),T)
        self.assertTrue(self.store.load('simulated')['outbox']);self.s.publish=lambda *a:self.sent.append(a)
        self.s.handle('telemetry',packet(T,1),T);self.assertFalse(self.store.load('simulated')['outbox']);self.assertEqual(len(self.sent),2)
    def test_atomic_conflict(self):
        self.s.handle('tick',{},T)
        with self.assertRaises(Conflict):self.store.commit('simulated',0,{}, {})
    def test_request_idempotency(self):
        self.s.handle('telemetry',packet(T,1,soil=20),T)
        req={'action':'arm','request_id':'one'};a=self.s.handle('request',req,T);n=len(self.sent);self.assertEqual(self.s.handle('request',req,T),a);self.assertEqual(len(self.sent),n)
        self.assertEqual(self.s.handle('request',{'action':'disarm','request_id':'one'},T)['status'],'rejected')
    def test_commands_never_retained(self):
        self.s.handle('telemetry',packet(T,1),T);self.s.handle('request',{'action':'arm','request_id':'arm'},T)
        self.assertTrue(any(x[0].endswith('command') and x[2] is False for x in self.sent))
    def test_backend_generation_disarms(self):
        self.s.handle('telemetry',packet(T,1),T);b=Service(self.store,lambda *a:None,self.p,'new');b.handle('tick',{},T+1);self.assertEqual(b.get_state(T+1)['watering']['stage'],'DISARMED')
    def test_mode_isolation(self):
        self.assertEqual(self.s.handle('telemetry',{**packet(T,1),'mode':'live'},T)['status'],'rejected')
        self.assertFalse(self.store.history('live','READING#','', 'z'))
    def test_status_receipt(self):
        self.s.handle('status',dict(schema=1,mode='simulated',client='sensor',boot_id='b',status='offline',ts=None),T)
        self.assertEqual(self.s.get_state(T)['connections']['sensor']['received_at'],c.utc(T))

class WaterTests(unittest.TestCase):
    def setUp(self):self.p=default('simulated');self.w=Watering(self.p);self.s=packet(T,1,soil=20);self.w.state['profile']='demo'
    def arm(self):
        cmd=self.w.request('arm',self.s,T,'arm');self.w.event(dict(action='arm',command_id=cmd['command_id'],boot_id='sim-boot',status='accepted'),T);return cmd
    def start(self):
        self.arm();cmd=self.w.request('water',self.s,T,'water');self.w.event(dict(action='water',command_id=cmd['command_id'],boot_id='sim-boot',status='started',baseline_soil_pct=20,started_at=c.utc(T)),T);return cmd
    def complete(self,cmd):self.w.event(dict(action='water',command_id=cmd['command_id'],boot_id='sim-boot',status='completed',actual_duration_ms=2000,ended_at=c.utc(T+2)),T+2)
    def test_arm_needs_ack(self):self.w.request('arm',self.s,T,'a');self.assertEqual(self.w.state['stage'],'DISARMED')
    def test_disarmed_rejects(self):self.assertEqual(self.w.block('water',self.s,T),'not_armed')
    def test_manual_requires_dry(self):self.arm();self.s['soil']['pct']=30;self.assertEqual(self.w.block('water',self.s,T),'soil_not_dry')
    def test_success_median_cooldown(self):
        cmd=self.start();self.complete(cmd)
        for i,v in enumerate([24,100,24],2):s=packet(T+i*2,i,soil=v);self.w.sample(s,T+i*2)
        self.w.tick(s,T+8);self.assertEqual(self.w.state['stage'],'COOLDOWN');self.w.tick(packet(T+14,8),T+14);self.assertEqual(self.w.state['stage'],'READY')
    def test_outlier_not_response(self):
        cmd=self.start();self.complete(cmd)
        for i,v in enumerate([20,100,20],2):s=packet(T+i*2,i,soil=v);self.w.sample(s,T+i*2)
        self.w.tick(s,T+8);self.assertEqual(self.w.state['fault'],'insufficient_rise')
    def test_missing_response(self):
        cmd=self.start();self.complete(cmd);self.w.tick(packet(T+8,5),T+8);self.assertEqual(self.w.state['fault'],'missing_response')
    def test_start_timeout(self):self.arm();self.w.request('water',self.s,T,'w');self.w.tick(packet(T+15,9),T+15);self.assertEqual(self.w.state['fault'],'event_timeout')
    def test_sensor_reboot_fault(self):self.start();self.w.sample(packet(T+2,1,boot='new'),T+2);self.assertEqual(self.w.state['fault'],'sensor_restart')
    def test_invalid_during_run(self):self.start();self.w.sample(packet(T+2,2,soil=None),T+2);self.assertEqual(self.w.state['fault'],'moisture_invalid')
    def test_reset_inspection(self):self.w.fault('test');self.assertEqual(self.w.block('reset_fault',self.s,T),'malformed')
    def test_reset_stays_disarmed_preserves_cooldown(self):
        self.w.fault('test');self.w.state['cool_until']=T+60;cmd=self.w.request('reset_fault',self.s,T,'reset',True);self.w.event(dict(action='reset_fault',command_id=cmd['command_id'],boot_id='sim-boot',status='accepted'),T);self.assertEqual(self.w.state['stage'],'DISARMED');self.assertEqual(self.w.state['cool_until'],T+60)
    def test_late_completion_no_clear(self):
        cmd=self.start();self.w.fault('timeout');self.complete(cmd);self.assertEqual(self.w.state['stage'],'FAULT')
    def test_missing_started_fault(self):self.arm();cmd=self.w.request('water',self.s,T,'w');self.complete(cmd);self.assertEqual(self.w.state['fault'],'missing_started')

class Logger(unittest.TestCase):
    def test_offline_row(self):
        lines=['Uptime: 2 ms','Temperature: 23 C','Humidity: 60 %','Light: 1500 lux','Soil Moisture: INVALID / OFFLINE'];rows=list(samples(lines,'dry'));self.assertEqual(len(rows),1);self.assertFalse(rows[0]['soil_raw_valid'])
    def test_fraction_not_truncated(self):
        lines=['Uptime: 2 ms','Temperature: 23 C','Humidity: 60 %','Light: 1500 lux','Soil Moisture (raw): 360.9'];self.assertIsNone(list(samples(lines,'dry'))[0]['soil_raw'])
