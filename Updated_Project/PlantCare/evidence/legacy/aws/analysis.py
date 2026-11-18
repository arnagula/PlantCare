"""Pure rule baseline and optional trained classification; no network operations."""
import math

RULES = {
  'low_light': ('light_lux', 1100, 'below'),
  'too_cold': ('temperature_c', 16, 'below'),
  'too_hot': ('temperature_c', 27, 'above'),
  'low_humidity': ('humidity_pct', 50, 'below'),
}

def valid_metric(packet, key):
    entry=packet.get(key)
    if not isinstance(entry,dict) or entry.get('valid') is not True: return None
    v=entry.get('value')
    if isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v): return None
    return float(v)

def classify_rules(packet, profile):
    """Immediate conditions. Stateful persistence/hysteresis is a separate production task."""
    out=[]
    t=profile['thresholds']
    checks=[('too_cold','temperature_c',t['cold_enter_c'],lambda x,y:x<y),
            ('too_hot','temperature_c',t['hot_enter_c'],lambda x,y:x>y),
            ('low_humidity','humidity_pct',t['humidity_enter_pct'],lambda x,y:x<y),
            ('low_light','light_lux',t['light_enter_lux'],lambda x,y:x<y)]
    for name,key,threshold,fn in checks:
        value=valid_metric(packet,key)
        if value is not None and fn(value,threshold): out.append(name)
    soil=packet.get('soil',{})
    s=soil.get('pct') if isinstance(soil,dict) and soil.get('valid') is True and soil.get('calibrated') is True else None
    if isinstance(s,(int,float)) and not isinstance(s,bool) and math.isfinite(s):
        dry=profile['soil']['dry_enter_pct']; wet=profile['soil']['wet_enter_pct']
        if dry is not None and s<dry:out.insert(0,'thirsty')
        if wet is not None and s>wet:out.insert(0,'too_wet')
    return out

def assess(packet,profile,model=None):
    """Model contract: predict_issues(dict)->list[str]. ML output is advisory only."""
    rules=classify_rules(packet,profile)
    if model is not None and profile.get('classification',{}).get('model_enabled'):
        suggestions=model.predict_issues(packet)
        allowed={'thirsty','too_wet','low_light','too_cold','too_hot','low_humidity'}
        if not isinstance(suggestions,list) or not set(suggestions).issubset(allowed):
            raise ValueError('model returned invalid issue codes')
        # Using ML results for informational display requires independent validation.
        issues=suggestions
    else: issues=rules
    soil=packet.get('soil',{})
    calibrated=isinstance(soil,dict) and soil.get('calibrated') is True and soil.get('valid') is True
    valid_count=sum(valid_metric(packet,k) is not None for k in ('temperature_c','humidity_pct','light_lux'))
    if valid_count < 3: status='invalid'
    elif not calibrated: status='uncalibrated'
    else: status='ok'
    state='unknown' if status!='ok' else (issues[0] if issues else 'happy')
    mood='regular' if status!='ok' else ('sad' if any(x in issues for x in ('thirsty','too_wet','too_hot','too_cold')) else ('regular' if issues else 'happy'))
    return {'data_status':status,'state':state,'mood':mood,'issues':issues,
            'reason':('Soil calibration or sensor validity pending' if status!='ok' else ('Detected: '+', '.join(issues) if issues else 'No active issues'))[:119]}
