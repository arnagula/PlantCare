"""Cloud coordinator. Persist its state and command before publishing the returned command."""
import copy
import statistics
import uuid
from .contracts import timestamp, utc, require
from .profile import calibrated

ACTIVE={'COMMAND_PENDING','RUNNING','OBSERVING'}
class Watering:
    def __init__(self,profile,state=None):
        self.profile=profile
        self.state=copy.deepcopy(state) if state else dict(stage='DISARMED',fault=None,command=None,control=None,deadline=None,cool_until=0,baseline=None,completed=None,post=[],last_boot=None,pump_on=False)
    def dump(self): return copy.deepcopy(self.state)
    def fault(self,reason):
        if self.state['stage'] in ('COMMAND_PENDING','RUNNING') or self.state['control']:self.state['uncertain_cooldown']=True
        self.state.update(stage='FAULT',fault=reason)
    def cooldown(self,s): return self.profile['watering'].get(s['profile']+'_cooldown_s') or 0
    def block(self,action,s,now,inspected=False):
        w=self.state; cfg=self.profile['watering']
        if not s: return 'moisture_invalid'
        timing=self.profile['timing'][s['profile']]
        limit=timing['fast_stale_s'] if s['sample_interval_s']==timing['fast_sample_s'] else timing['stale_s']
        if not -5<=now-timestamp(s['ts'])<=limit: return 'clock_invalid' if now<timestamp(s['ts'])-5 else 'moisture_invalid'
        if w['stage'] in ACTIVE or w['control'] or s['pump']['on']: return 'busy'
        if action=='reset_fault':
            if not inspected: return 'malformed'
            if not calibrated(self.profile,s): return 'moisture_invalid'
            return None
        if action=='disarm': return None
        if w['stage']=='FAULT' or s['pump']['fault']: return 'fault_active'
        if not cfg['qualified'] or s['config_id']!=cfg['config_id']: return 'config_mismatch'
        if not calibrated(self.profile,s): return 'moisture_invalid'
        if now<w['cool_until'] or s['pump']['cooldown_remaining_s']>0: return 'cooldown'
        if action=='water':
            if w['stage']!='READY': return 'not_armed'
            if s['soil']['pct']>=self.profile['soil']['dry_enter_pct']: return 'soil_not_dry'
        return None
    def request(self,action,s,now,request_id,inspected=False,automatic=False):
        require(action in ('water','arm','disarm','reset_fault'),'action')
        reason=self.block(action,s,now,inspected); require(reason is None,reason or 'blocked')
        cmd=dict(schema=1,mode=self.profile['mode'],command_id=str(uuid.uuid5(uuid.NAMESPACE_URL,self.profile['mode']+':'+request_id)),action=action,target_boot_id=s['boot_id'],config_id=s['config_id'],issued_at=utc(now),expires_at=utc(now+10))
        if action=='water':
            cmd.update(duration_ms=self.profile['watering']['dose_ms'],reason='automatic' if automatic else 'manual')
            self.state.update(stage='COMMAND_PENDING',command=cmd,deadline=now+15,baseline=None,completed=None,post=[])
        else:
            if action=='reset_fault':
                cmd['inspected']=True
                if self.state.get('uncertain_cooldown'):self.state['cool_until']=max(self.state['cool_until'],now+self.cooldown(s))
            self.state.update(control=cmd,deadline=now+15)
        self.state['last_boot']=s['boot_id']
        return cmd
    def sample(self,s,now):
        w=self.state
        if w['last_boot'] is not None and w['last_boot']!=s['boot_id']:
            if w['stage'] in ACTIVE or w['control']: self.fault('sensor_restart')
            else: w.update(stage='DISARMED',control=None)
            w['cool_until']=max(w['cool_until'],now+self.cooldown(s))
        w['last_boot']=s['boot_id']
        if timestamp(s['ts'])>=w.get('pump_event_ts',0):w['pump_on']=s['pump']['on']
        if s['pump']['fault']: self.fault('device_fault')
        if w['stage'] in ACTIVE and not calibrated(self.profile,s): self.fault('moisture_invalid')
        if s['pump']['on'] and w['stage'] not in ('COMMAND_PENDING','RUNNING','FAULT'): self.fault('unexpected_pump')
        if w['stage']=='OBSERVING' and timestamp(s['ts'])>w['completed'] and calibrated(self.profile,s):
            w['post']=(w['post']+[s['soil']['pct']])[-3:]
    def event(self,e,now):
        w=self.state; c=w['control'] if e['action']!='water' else w['command']
        require(c is not None and e['command_id']==c['command_id'] and e['boot_id']==c['target_boot_id'] and e['action']==c['action'],'unknown_event')
        event_time=timestamp(e['ts']) if 'ts' in e else now
        if event_time<w.get('pump_event_ts',0):return
        w['pump_event_ts']=event_time
        w['pump_on']=e.get('pump_on',e['status']=='started')
        if w['stage']=='FAULT' and not (w['control'] and w['control']['action']=='reset_fault'): return
        if e['action']!='water':
            w['control']=None
            if e['status']=='rejected': self.fault('control_rejected')
            elif e['action']=='arm': w.update(stage='READY',fault=None)
            elif e['action']=='reset_fault':w.update(stage='DISARMED',fault=None,uncertain_cooldown=False)
            else:w.update(stage='FAULT' if w['fault'] else 'DISARMED')
            return
        if e['status']=='started':
            require(w['stage']=='COMMAND_PENDING','unexpected_started')
            w.update(stage='RUNNING',baseline=e['baseline_soil_pct'],deadline=timestamp(e['started_at'])+c['duration_ms']/1000+10,pump_on=True)
        elif e['status']=='completed':
            if w['stage']!='RUNNING': self.fault('missing_started'); return
            if e['actual_duration_ms']>self.profile['watering']['hard_max_ms']: self.fault('overrun'); return
            end=timestamp(e['ended_at']); w.update(stage='OBSERVING',completed=end,post=[],pump_on=False)
            w['cool_until']=max(w['cool_until'],end+self.profile['watering'][self.sample_profile+'_cooldown_s'])
        else: w['pump_on']=False; self.fault('water_'+e['status'])
    @property
    def sample_profile(self): return self.state.get('profile','normal')
    def tick(self,s,now):
        w=self.state
        if s: w['profile']=s['profile']
        if (w['control'] or w['stage'] in ('COMMAND_PENDING','RUNNING')) and now>=w['deadline']:
            self.fault('event_timeout'); w['control']=None
        if w['stage'] in ACTIVE:
            if not s or now-timestamp(s['ts'])>self.profile['timing'][s['profile']]['fast_stale_s']:
                self.fault('moisture_timeout')
        if w['stage']=='OBSERVING' and now>=w['completed']+self.profile['watering'][s['profile']+'_response_wait_s']:
            w['response']=dict(baseline=w['baseline'],completed_at=w['completed'],median=statistics.median(w['post']) if len(w['post'])==3 else None,min_rise_pct=self.profile['watering']['min_rise_pct'])
            if len(w['post'])<3: self.fault('missing_response')
            elif statistics.median(w['post'])-w['baseline']<self.profile['watering']['min_rise_pct']: self.fault('insufficient_rise')
            else: w['stage']='COOLDOWN'
        if w['stage']=='COOLDOWN' and now>=w['cool_until']:
            w['stage']='READY'; return True
        return False
    def snapshot(self,now):
        w=self.state
        return dict(stage=w['stage'],fault=w['fault'],pump_on=w['pump_on'],command_id=w['command']['command_id'] if w['command'] else None,cooldown_remaining_s=max(0,w['cool_until']-now))
