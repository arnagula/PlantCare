import datetime,math

def validate_telemetry(p):
    if not isinstance(p,dict) or p.get('schema') != 1 or p.get('mode') not in ('live','simulated'):
        raise ValueError('invalid schema/mode')
    for k in ('device_id','boot_id','ts','config_id'):
        if not isinstance(p.get(k),str) or not p[k] or len(p[k])>64 and k!='ts':raise ValueError('missing/invalid '+k)
    if not isinstance(p.get('seq'),int) or isinstance(p['seq'],bool) or p['seq']<1:raise ValueError('invalid seq')
    ts=datetime.datetime.fromisoformat(p['ts'].replace('Z','+00:00'))
    if ts.tzinfo is None:raise ValueError('timestamp must be timezone-aware')
    for key,low,high in [('temperature_c',-40,85),('humidity_pct',0,100),('light_lux',0,200000)]:
        e=p.get(key)
        if not isinstance(e,dict) or not isinstance(e.get('valid'),bool):raise ValueError(key+' validity missing')
        v=e.get('value')
        if e['valid'] and (isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) or not low<=v<=high):raise ValueError(key+' invalid reading')
        if not e['valid'] and v is not None:raise ValueError(key+' invalid must have null value')
    soil=p.get('soil')
    if not isinstance(soil,dict) or not isinstance(soil.get('calibrated'),bool) or not isinstance(soil.get('valid'),bool): raise ValueError('invalid soil')
    if not soil['calibrated'] and soil.get('pct') is not None:raise ValueError('uncalibrated soil pct must be null')
    if soil['valid'] and (not soil['calibrated'] or isinstance(soil.get('pct'),bool) or not isinstance(soil.get('pct'),(int,float)) or not 0<=soil['pct']<=100):raise ValueError('invalid soil pct')
    return p
