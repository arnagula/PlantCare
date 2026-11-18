"""Canonical profile and evidence gates; simulation numbers never qualify live hardware."""
import copy
from .contracts import require, number, integer, ident

TIMING = {'normal': dict(sample_s=60, fast_sample_s=2, stale_s=180, fast_stale_s=10, clear_s=60, dry_s=300, wet_s=3600, light_s=1800, temperature_s=300, humidity_s=1800), 'demo': dict(sample_s=2, fast_sample_s=2, stale_s=10, fast_stale_s=10, clear_s=5, dry_s=10, wet_s=10, light_s=10, temperature_s=10, humidity_s=10)}
def default(mode='live'):
    p = dict(mode=mode, profile_revision='v2-unqualified', plant='Epipremnum aureum', timezone='America/New_York', night={'start':'20:00','end':'08:00'}, thresholds=dict(light_enter_lux=1100,light_exit_lux=1300,cold_enter_c=16,cold_exit_c=17,hot_enter_c=27,hot_exit_c=26,humidity_enter_pct=50,humidity_exit_pct=55), soil={k:None for k in ('calibration_id','raw_dry','raw_wet','dry_enter_pct','dry_exit_pct','wet_exit_pct','wet_enter_pct','noise_pct','raw_noise','dry_samples','wet_samples')}, watering={k:None for k in ('config_id','dose_ms','hard_max_ms','normal_cooldown_s','normal_response_wait_s','demo_cooldown_s','demo_response_wait_s','min_rise_pct')}, timing=copy.deepcopy(TIMING))
    p['soil']['evidence_approved'] = False
    p['watering'].update(qualified=False,evidence_approved=False)
    if mode == 'simulated':
        p['profile_revision']='v2-simulation-fixture'
        p['soil'].update(calibration_id='sim-soil',raw_dry=300,raw_wet=700,dry_enter_pct=30,dry_exit_pct=40,wet_exit_pct=70,wet_enter_pct=80,noise_pct=1,raw_noise=4,dry_samples=20,wet_samples=20,evidence_approved=True)
        p['watering'].update(qualified=True,evidence_approved=True,config_id='sim-config',dose_ms=2000,hard_max_ms=3000,normal_cooldown_s=60,normal_response_wait_s=6,demo_cooldown_s=12,demo_response_wait_s=6,min_rise_pct=3)
    return p

def validate(p):
    require(p.get('mode') in ('live','simulated') and ident(p.get('profile_revision')), 'profile_identity')
    require(p.get('timezone') == 'America/New_York' and p.get('night') == {'start':'20:00','end':'08:00'}, 'night')
    t=p['thresholds']
    for a,b in [('light_enter_lux','light_exit_lux'),('cold_enter_c','cold_exit_c'),('hot_exit_c','hot_enter_c'),('humidity_enter_pct','humidity_exit_pct')]:
        require(number(t.get(a)) and number(t.get(b)) and t[a]<t[b], 'threshold_order')
    s=p['soil']; keys=('dry_enter_pct','dry_exit_pct','wet_exit_pct','wet_enter_pct')
    if any(s.get(k) is not None for k in keys):
        require(all(number(s.get(k),0,100) for k in keys), 'soil_thresholds')
        require(all(s[keys[i]]<s[keys[i+1]] for i in range(3)), 'soil_order')
    if s.get('evidence_approved'):
        require(ident(s.get('calibration_id')) and all(integer(s.get(k),20) for k in ('dry_samples','wet_samples')), 'soil_evidence')
        require(all(number(s.get(k),0,65535) for k in ('raw_dry','raw_wet')), 'endpoints')
        span=abs(s['raw_wet']-s['raw_dry'])
        require(number(s.get('raw_noise'),0) and span>2*s['raw_noise'], 'noise_overlap')
        require(number(s.get('noise_pct'),0) and s['noise_pct']>=100*s['raw_noise']/span, 'noise_pct')
        require(all(number(s.get(k),0,100) for k in keys), 'qualified_thresholds')
    w=p['watering']
    require(type(w.get('qualified')) is bool, 'qualified')
    if w['qualified']:
        require(s.get('evidence_approved') is True and w.get('evidence_approved') is True, 'watering_evidence')
        require(ident(w.get('config_id')) and integer(w.get('dose_ms'),1) and integer(w.get('hard_max_ms'),1) and w['dose_ms']<=w['hard_max_ms'], 'dose')
        require(number(w.get('min_rise_pct'),0) and w['min_rise_pct']>s['noise_pct'], 'rise_above_noise')
        for name in ('normal','demo'):
            wait=w.get(name+'_response_wait_s'); cool=w.get(name+'_cooldown_s')
            require(number(wait,6) and number(cool,wait), 'water_timing')
    for t in p['timing'].values():
        require(all(number(t.get(k),.001) for k in TIMING['normal']), 'timing')
        require(t['stale_s']>=3*t['sample_s'] and t['fast_stale_s']>=3*t['fast_sample_s'], 'stale_ratio')
    require('demo_daylight' not in p or (p['mode']=='simulated' and type(p['demo_daylight']) is bool), 'day_override')
    return copy.deepcopy(p)

def calibrated(p, sample):
    s=sample['soil']; cfg=p['soil']
    return cfg.get('evidence_approved') is True and s['calibrated'] and s['valid'] and s['calibration_id']==cfg['calibration_id']

def moisture(raw,p):
    s=p['soil']; require(s.get('evidence_approved') is True, 'unqualified')
    return max(0,min(100,100*(raw-s['raw_dry'])/(s['raw_wet']-s['raw_dry'])))
