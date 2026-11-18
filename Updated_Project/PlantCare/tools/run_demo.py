"""Deterministic no-cloud scenario through the actual coordinator, engine and journal."""
import argparse,json
from plantcare.contracts import timestamp
from plantcare.profile import default
from plantcare.storage import MemoryStore
from plantcare.service import Service
from plantcare.simulator import Actuator
from tools.scenarios import packet

def run(no_rise=False):
    p=default('simulated');p['demo_daylight']=True;store=MemoryStore();messages=[];app=Service(store,lambda *a:messages.append(a),p);device=Actuator(p);start=timestamp('2026-11-12T15:00:00.000Z');trace=[]
    for i in range(20):
        now=start+2*i;s=packet(now,i+1,soil=20 if no_rise or i<8 else 50);device.sample=s
        event=device.tick(now)
        if event:app.handle('event',event,now)
        s['pump'].update(on=device.current is not None,armed=device.armed,active_command_id=device.current['command_id'] if device.current else None,fault='local_fault' if device.fault else None,cooldown_remaining_s=max(0,device.cool_until-now))
        app.handle('telemetry',s,now)
        if i==0:app.handle('request',{'action':'arm','request_id':'demo-arm'},now)
        while messages:
            topic,payload,retain=messages.pop(0)
            if topic.endswith('/command'):
                assert not retain
                e=device.accept(payload,now)
                if e:app.handle('event',e,now)
        state=app.get_state(now);trace.append({'second':2*i,'state':state['state'],'stage':state['watering']['stage'],'fault':state['watering']['fault']})
    return trace,store
if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--no-rise',action='store_true');args=parser.parse_args();print(json.dumps(run(args.no_rise)[0],indent=2))
