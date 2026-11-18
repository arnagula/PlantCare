"""Complete simulated telemetry; production telemetry comes from real sensors."""
from plantcare.contracts import utc

def packet(t,seq,soil=50,temp=23,rh=60,lux=1500,profile='demo',boot='sim-boot'):
    return dict(schema=1,mode='simulated',profile=profile,device_id='sim-sensor-01',boot_id=boot,seq=seq,ts=utc(t),uptime_ms=seq*2000,sample_interval_s=2 if profile=='demo' else 60,config_id='sim-config',temperature_c={'value':temp,'valid':temp is not None},humidity_pct={'value':rh,'valid':rh is not None},light_lux={'value':lux,'valid':lux is not None},soil={'raw':int(300+soil*4) if soil is not None else None,'raw_valid':soil is not None,'pct':soil,'valid':soil is not None,'calibrated':True,'calibration_id':'sim-soil'},pump={'on':False,'armed':False,'fault':None,'active_command_id':None,'cooldown_remaining_s':0})
