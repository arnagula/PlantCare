"""Frozen schema-1 validation. No numeric coercion or network side effects."""
import datetime as dt
import json
import math
import re

class Rejected(ValueError):
    pass

def require(ok, field):
    if not ok:
        raise Rejected(field)

def number(x, low=-float('inf'), high=float('inf')):
    return type(x) in (int, float) and math.isfinite(x) and low <= x <= high

def integer(x, low=0):
    return type(x) is int and x >= low

def ident(x):
    return isinstance(x, str) and 0 < len(x) <= 64

def timestamp(x):
    require(isinstance(x, str) and re.fullmatch(r'\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{3}Z', x), 'timestamp')
    try:
        return dt.datetime.fromisoformat(x.replace('Z', '+00:00')).timestamp()
    except ValueError as exc:
        raise Rejected('timestamp') from exc

def utc(t):
    return dt.datetime.fromtimestamp(t, dt.timezone.utc).isoformat(timespec='milliseconds').replace('+00:00', 'Z')

def envelope(p, mode=None):
    require(isinstance(p, dict), 'object')
    try:
        require(len(json.dumps(p, ensure_ascii=False, allow_nan=False, separators=(',', ':')).encode()) <= 4096, 'payload_size')
    except (ValueError, TypeError, UnicodeError) as exc:
        raise Rejected('json') from exc
    require(type(p.get('schema')) is int and p['schema'] == 1, 'schema')
    require(p.get('mode') in ('live', 'simulated') and (mode is None or mode == p['mode']), 'mode')

def measurement(e, key, low, high, flag='valid'):
    require(isinstance(e, dict) and type(e.get(flag)) is bool and key in e, key)
    require(number(e[key], low, high) if e[flag] else e[key] is None, key)

def telemetry(p, mode=None, now=None):
    envelope(p, mode)
    for key in ('device_id', 'boot_id', 'config_id'):
        require(ident(p.get(key)), key)
    require(p.get('profile') in ('normal', 'demo'), 'profile')
    require(integer(p.get('seq'), 1), 'seq')
    require(integer(p.get('uptime_ms')), 'uptime_ms')
    require(number(p.get('sample_interval_s'), 0.001), 'sample_interval_s')
    t = timestamp(p.get('ts'))
    require(now is None or t <= now + 5, 'future_timestamp')
    for key, lo, hi in [('temperature_c', -40, 85), ('humidity_pct', 0, 100), ('light_lux', 0, 200000)]:
        measurement(p.get(key), 'value', lo, hi)
    s = p.get('soil')
    measurement(s, 'raw', 0, 65535, 'raw_valid')
    require(s['raw'] is None or integer(s['raw']), 'soil.raw')
    measurement(s, 'pct', 0, 100)
    require(type(s.get('calibrated')) is bool and 'calibration_id' in s, 'calibrated')
    require(ident(s['calibration_id']) if s['calibrated'] else s['calibration_id'] is None, 'calibration_id')
    require(not s['valid'] or (s['calibrated'] and s['raw_valid']), 'soil.valid')
    require(s['calibrated'] or s['pct'] is None, 'soil.pct')
    pump = p.get('pump')
    require(isinstance(pump, dict), 'pump')
    for key in ('on', 'armed'):
        require(type(pump.get(key)) is bool, 'pump.' + key)
    for key in ('fault', 'active_command_id'):
        require(key in pump and (pump[key] is None or ident(pump[key])), 'pump.' + key)
    require(number(pump.get('cooldown_remaining_s'), 0), 'cooldown_remaining_s')
    return p

def command(p, mode=None):
    envelope(p, mode)
    for key in ('command_id', 'target_boot_id', 'config_id'):
        require(ident(p.get(key)), key)
    require(p.get('action') in ('water', 'arm', 'disarm', 'reset_fault'), 'action')
    require(abs(timestamp(p.get('expires_at')) - timestamp(p.get('issued_at')) - 10) < .0001, 'expiry_window')
    if p['action'] == 'water':
        require(integer(p.get('duration_ms'), 1), 'duration_ms')
        require(p.get('reason') in ('manual', 'automatic'), 'reason')
    else:
        require('duration_ms' not in p, 'control_duration')
    if p['action'] == 'reset_fault':
        require(p.get('inspected') is True, 'inspected')
    return p

REASONS = {'malformed', 'expired', 'wrong_boot', 'config_mismatch', 'not_armed', 'busy', 'cooldown', 'moisture_invalid', 'soil_not_dry', 'duration_invalid', 'clock_invalid', 'fault_active'}
def event(p, mode=None):
    envelope(p, mode)
    for key in ('device_id', 'boot_id', 'command_id'):
        require(ident(p.get(key)), key)
    require(integer(p.get('event_seq'), 1), 'event_seq')
    timestamp(p.get('ts'))
    require(p.get('action') in ('water', 'arm', 'disarm', 'reset_fault'), 'action')
    statuses = ('started', 'completed', 'rejected', 'aborted') if p['action'] == 'water' else ('accepted', 'rejected')
    require(p.get('status') in statuses, 'status')
    require(type(p.get('pump_on')) is bool, 'pump_on')
    if p['action']!='water' and p['status']=='accepted':require(p['pump_on'] is False,'control_pump_off')
    require('reason_code' in p and (p['reason_code'] in REASONS if p['status'] == 'rejected' else p['reason_code'] is None or ident(p['reason_code'])), 'reason_code')
    if p['status'] == 'started':
        require(p['pump_on'] is True, 'started_pump')
        require(timestamp(p.get('started_at'))<=timestamp(p['ts']), 'start_time')
        require(number(p.get('baseline_soil_pct'), 0, 100), 'baseline')
    if p['status'] in ('completed', 'aborted'):
        require(p['pump_on'] is False, 'stopped_pump')
        start, end = timestamp(p.get('started_at')), timestamp(p.get('ended_at'))
        require(end >= start and end<=timestamp(p['ts']) and integer(p.get('actual_duration_ms')), 'duration')
        require(abs((end-start)*1000-p['actual_duration_ms'])<=2, 'duration_timestamp')
        require(number(p.get('baseline_soil_pct'), 0, 100), 'baseline')
    return p

def status(p, mode=None):
    envelope(p, mode)
    require(ident(p.get('boot_id')), 'boot_id')
    require(p.get('client') in ('sensor', 'display', 'backend'), 'client')
    require(p.get('status') in ('online', 'offline'), 'status')
    require('ts' in p, 'ts')
    if p['ts'] is None:
        require(p['status'] == 'offline', 'null_online')
    else:
        timestamp(p['ts'])
    return p

def condition(p,mode=None):
    envelope(p,mode)
    require(p.get('profile') in ('normal','demo'),'profile')
    for key in ('backend_boot_id','profile_revision'):require(ident(p.get(key)),key)
    require(integer(p.get('report_seq'),1),'report_seq');timestamp(p.get('ts'))
    require('source' in p and 'sample_ts' in p,'source')
    if p['source'] is None:require(p['sample_ts'] is None and p.get('data_status')=='stale','startup_source')
    else:
        require(isinstance(p['source'],dict),'source')
        for key in ('device_id','boot_id'):require(ident(p['source'].get(key)),key)
        require(integer(p['source'].get('seq'),1),'source_seq');timestamp(p['sample_ts'])
    require(number(p.get('freshness_timeout_s'),.001),'freshness_timeout')
    issues={'thirsty','too_wet','low_light','too_cold','too_hot','low_humidity'}
    require(p.get('data_status') in ('ok','invalid','stale','uncalibrated'),'data_status')
    require(p.get('state') in issues|{'unknown','watering_fault','watering','checking_moisture','happy'},'state')
    require(p.get('mood') in ('happy','regular','sad'),'mood')
    require(isinstance(p.get('reason'),str) and p['reason'].isascii() and len(p['reason'])<=119,'reason')
    require(isinstance(p.get('invalid_fields'),list) and all(isinstance(x,str) for x in p['invalid_fields']),'invalid_fields')
    require(isinstance(p.get('issues'),list) and all(x in issues for x in p['issues']) and len(set(p['issues']))==len(p['issues']),'issues')
    require(isinstance(p.get('details'),list),'details')
    for d in p['details']:
        require(isinstance(d,dict) and d.get('code') in p['issues'] and number(d.get('value')) and number(d.get('threshold')) and isinstance(d.get('unit'),str) and isinstance(d.get('recommendation'),str),'detail')
    w=p.get('watering');require(isinstance(w,dict),'watering')
    require(w.get('stage') in ('DISARMED','READY','COMMAND_PENDING','RUNNING','OBSERVING','COOLDOWN','FAULT'),'stage')
    require(type(w.get('pump_on')) is bool and number(w.get('cooldown_remaining_s'),0),'watering_fields')
    for key in ('command_id','fault'):require(key in w and (w[key] is None or ident(w[key])),key)
    return p
