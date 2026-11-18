import argparse,json
from pathlib import Path
from plantcare.profile import validate

def generate(p,demo=False):
    validate(p)
    if p['mode']!='live':raise ValueError('Simulation calibration must never generate live firmware')
    s=p['soil'];w=p['watering'];name='demo' if demo else 'normal';timing=p['timing'][name]
    text=['#pragma once','#include "../shared/SafetyCore.h"','namespace settings {']
    text+=['constexpr bool calibrated = '+str(s['evidence_approved']).lower()+';', 'constexpr char profile[] = '+json.dumps(name)+';', 'constexpr char calibrationId[] = '+json.dumps(s['calibration_id'] or '')+';']
    for key,value in {'rawDry':s['raw_dry'] or 0,'rawWet':s['raw_wet'] or 1,'sampleMs':timing['sample_s']*1000,'responseMs':(w[name+'_response_wait_s'] or 6)*1000}.items():text.append(f'constexpr double {key} = {value};')
    text.append('inline plantcare::Config config(){return {'+','.join([str(w['qualified']).lower(),'"live"',json.dumps(w['config_id'] or 'cfg-unqualified'),str(w['hard_max_ms'] or 0),str(w['dose_ms'] or 0),str(int((w[name+'_cooldown_s'] or 0)*1000)),str(s['dry_enter_pct'] or 0)])+'};}')
    return '\n'.join(text+['}'])+'\n'
if __name__=='__main__':
    a=argparse.ArgumentParser();a.add_argument('--profile',default='profiles/live.json');a.add_argument('--demo',action='store_true');args=a.parse_args();Path('firmware/sensor_controller/Config.h').write_text(generate(json.loads(Path(args.profile).read_text()),args.demo))
