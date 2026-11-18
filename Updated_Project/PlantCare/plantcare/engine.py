"""Serializable sample-driven persistence and hysteresis, with explicit wall-clock ticks."""
import copy
import datetime as dt
from zoneinfo import ZoneInfo
from .contracts import telemetry, timestamp, require
from .profile import validate, calibrated

RULES = {
 'too_wet':('soil','wet_enter_pct','wet_exit_pct',1,'wet_s','%','Allow soil to dry; inspect drainage'),
 'thirsty':('soil','dry_enter_pct','dry_exit_pct',-1,'dry_s','%','Check soil and water if qualified'),
 'too_cold':('temperature_c','cold_enter_c','cold_exit_c',-1,'temperature_s','C','Move away from cold drafts'),
 'too_hot':('temperature_c','hot_enter_c','hot_exit_c',1,'temperature_s','C','Move away from heat sources'),
 'low_light':('light_lux','light_enter_lux','light_exit_lux',-1,'light_s','lux','Move to brighter indirect light'),
 'low_humidity':('humidity_pct','humidity_enter_pct','humidity_exit_pct',-1,'humidity_s','%RH','Increase nearby humidity')}

def empty_rule():
    return {'active':False,'enter':None,'clear':None}

class Engine:
    def __init__(self, profile, state=None):
        self.profile=validate(profile)
        self.state=copy.deepcopy(state) if state else dict(sample=None,received_at=None,retired_boots=[],rules={k:empty_rule() for k in RULES})
    def dump(self):
        return copy.deepcopy(self.state)
    def night(self,t):
        p=self.profile
        if 'demo_daylight' in p:
            return not p['demo_daylight']
        hour=dt.datetime.fromtimestamp(t,ZoneInfo(p['timezone'])).hour
        return hour>=20 or hour<8
    def reset(self):
        self.state['rules']={k:empty_rule() for k in RULES}
    def timeout(self,sample=None):
        s=sample or self.state['sample']
        if not s: return 10
        t=self.profile['timing'][s['profile']]
        return t['fast_stale_s'] if s['sample_interval_s']==t['fast_sample_s'] else t['stale_s']
    def values(self,s):
        return {**{k:s[k]['value'] if s[k]['valid'] else None for k in ('temperature_c','humidity_pct','light_lux')},'soil':s['soil']['pct'] if calibrated(self.profile,s) else None}
    def update(self,s,now):
        telemetry(s,self.profile['mode'],now)
        require(s['device_id']==('sensor-01' if s['mode']=='live' else 'sim-sensor-01'),'device_id')
        timing=self.profile['timing'][s['profile']]
        require(s['sample_interval_s'] in (timing['sample_s'],timing['fast_sample_s']), 'sample_interval')
        old=self.state['sample']; t=timestamp(s['ts'])
        if old:
            prev=timestamp(old['ts'])
            require(t>prev,'out_of_order_time')
            if old['boot_id']==s['boot_id']:
                require(s['seq']>old['seq'],'out_of_order_seq')
            else:
                require(s['boot_id'] not in self.state['retired_boots'],'retired_boot')
                self.state['retired_boots'].append(old['boot_id']); self.reset()
            if old['profile']!=s['profile'] or t-prev>1.5*old['sample_interval_s']:
                # A gap interrupts pending timers; unknown data also clears active assessment.
                self.reset()
        self.state.update(sample=copy.deepcopy(s),received_at=now)
        if now-t>self.timeout(s):
            self.reset(); return self.assess(now)
        values=self.values(s)
        for code,(metric,enter,clear,direction,duration,unit,advice) in RULES.items():
            r=self.state['rules'][code]; value=values[metric]
            if value is None or (code=='low_light' and self.night(t)):
                self.state['rules'][code]=empty_rule(); continue
            thresholds=self.profile['soil'] if metric=='soil' else self.profile['thresholds']
            if r['active']:
                qualifies=(value-thresholds[clear])*direction<0
                r['enter']=None
                if not qualifies: r['clear']=None
                elif r['clear'] is None: r['clear']=t
                elif t-r['clear']>=timing['clear_s']: self.state['rules'][code]=empty_rule()
            else:
                qualifies=(value-thresholds[enter])*direction>0
                r['clear']=None
                if not qualifies: r['enter']=None
                elif r['enter'] is None: r['enter']=t
                elif t-r['enter']>=timing[duration]: r.update(active=True,enter=None)
        return self.assess(now)
    def assess(self,now):
        s=self.state['sample']
        stale=s is None or now-timestamp(s['ts'])>self.timeout(s) or now<timestamp(s['ts'])-5
        if stale: self.reset()
        elif self.night(now): self.state['rules']['low_light']=empty_rule()
        values=self.values(s) if s else {k:None for k in ('soil','temperature_c','humidity_pct','light_lux')}
        invalid=[k for k,v in values.items() if v is None]
        status='stale' if stale else ('invalid' if any(k!='soil' for k in invalid) or (s['soil']['calibrated'] and not s['soil']['valid']) else ('uncalibrated' if 'soil' in invalid else 'ok'))
        issues=[k for k,r in self.state['rules'].items() if r['active'] and not stale]
        details=[]
        for code in issues:
            metric,enter,_,_,_,unit,advice=RULES[code]
            thresholds=self.profile['soil'] if metric=='soil' else self.profile['thresholds']
            details.append(dict(code=code,value=values[metric],unit=unit,threshold=thresholds[enter],recommendation=advice))
        state='unknown' if status!='ok' else (issues[0] if issues else 'happy')
        mood='regular' if status!='ok' else ('sad' if any(k in issues for k in ('too_wet','thirsty','too_hot','too_cold')) else ('regular' if issues else 'happy'))
        return dict(data_status=status,invalid_fields=invalid,state=state,mood=mood,issues=issues,details=details,reason=('Measurements '+status if status!='ok' else ', '.join(issues) or 'No active issues')[:119])
