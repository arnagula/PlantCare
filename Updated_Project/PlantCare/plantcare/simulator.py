"""Simulation-only actuator, with the same message contracts and local refusal gates."""
import copy
from .contracts import command,utc,timestamp,Rejected

class Actuator:
    def __init__(self,profile,boot='sim-boot',marker=None):
        if profile['mode']!='simulated':raise ValueError('simulation only')
        self.profile=profile;self.boot=boot;self.marker=copy.deepcopy(marker) if marker else {'active':False,'id':None,'issued':0}
        self.armed=False;self.fault=bool(self.marker['active']);self.cool_until=0;self.ids=[];self.seq=0;self.current=None;self.sample=None
    def emit(self,c,status,now,reason=None):
        self.seq+=1
        e=dict(schema=1,mode='simulated',device_id='sim-sensor-01',boot_id=self.boot,event_seq=self.seq,command_id=c['command_id'],action=c['action'],status=status,ts=utc(now),pump_on=self.current is not None,reason_code=reason)
        if status in ('started','completed','aborted'):
            e.update(started_at=utc(self.started),baseline_soil_pct=self.baseline)
        if status in ('completed','aborted'):e.update(ended_at=utc(now),actual_duration_ms=round((now-self.started)*1000))
        return e
    def accept(self,c,now):
        try:command(c,'simulated')
        except Rejected:return self.emit(c,'rejected',now,'malformed')
        if c['command_id'] in self.ids or c['command_id']==self.marker['id']:return None
        reason=None;s=self.sample;cfg=self.profile['watering'];action=c['action']
        if c['target_boot_id']!=self.boot:reason='wrong_boot'
        elif c['config_id']!=cfg['config_id']:reason='config_mismatch'
        elif now>=timestamp(c['expires_at']) or timestamp(c['issued_at'])<=self.marker['issued']:reason='expired'
        elif timestamp(c['issued_at'])>now+5:reason='clock_invalid'
        elif self.current:reason='busy'
        elif action=='reset_fault':
            if not s or not s['soil']['valid']:reason='moisture_invalid'
            else:self.fault=False;self.armed=False;self.marker['active']=False
        elif action=='disarm':self.armed=False
        elif self.fault:reason='fault_active'
        elif not cfg['qualified']:reason='config_mismatch'
        elif now<self.cool_until:reason='cooldown'
        elif not s or not s['soil']['valid'] or now-timestamp(s['ts'])>10:reason='moisture_invalid'
        elif action=='arm':self.armed=True
        elif not self.armed:reason='not_armed'
        elif s['soil']['pct']>=self.profile['soil']['dry_enter_pct']:reason='soil_not_dry'
        elif c['duration_ms']>cfg['hard_max_ms']:reason='duration_invalid'
        else:
            self.marker={'active':True,'id':c['command_id'],'issued':timestamp(c['issued_at'])};self.current=c;self.started=now;self.baseline=s['soil']['pct']
        if reason:return self.emit(c,'rejected',now,reason)
        self.ids=(self.ids+[c['command_id']])[-16:]
        return self.emit(c,'started' if action=='water' else 'accepted',now)
    def tick(self,now):
        if not self.current:return None
        valid=self.sample and self.sample['soil']['valid']
        if valid and now<self.started+self.current['duration_ms']/1000:return None
        c=self.current;self.current=None;self.marker['active']=False;self.cool_until=now+self.profile['watering'][self.sample['profile']+'_cooldown_s'];self.fault=not valid
        return self.emit(c,'completed' if valid else 'aborted',now,None if valid else 'moisture_invalid')
