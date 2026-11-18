"""TLS/QoS-1 simulator. Deliberately has no live mode or live topic option."""
import argparse,json,queue,ssl,time
from plantcare.profile import default
from plantcare.contracts import utc
from plantcare.simulator import Actuator
from tools.scenarios import packet

def readings(scenario,elapsed,device):
    values={}
    if scenario in ('dry_response','no_rise'):
        values['soil']=50 if scenario=='dry_response' and device.marker['id'] and not device.current else 20
    elif scenario=='four_second_dip':values['lux']=800 if elapsed<4 else 1500
    elif scenario=='twelve_second_dip':values['lux']=800 if elapsed<12 else 1500
    elif scenario=='hysteresis':values['lux']=800 if elapsed<12 else (1200 if elapsed<24 else 1500)
    elif scenario=='multiple':values.update(temp=28,rh=40,lux=800)
    elif scenario=='invalid':values.update(temp=None,lux=800)
    elif scenario in ('day','night'):values['lux']=800
    elif scenario in ('thirsty','too_wet','low_light','too_cold','too_hot','low_humidity'):
        key,value={'thirsty':('soil',20),'too_wet':('soil',90),'low_light':('lux',800),'too_cold':('temp',15),'too_hot':('temp',28),'low_humidity':('rh',40)}[scenario];values[key]=value
    return values

def main():
    import paho.mqtt.client as mqtt
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--endpoint',required=True);p.add_argument('--ca',required=True);p.add_argument('--cert',required=True);p.add_argument('--key',required=True);p.add_argument('--scenario',choices=['happy','four_second_dip','twelve_second_dip','hysteresis','multiple','invalid','day','night','thirsty','too_wet','low_light','too_cold','too_hot','low_humidity','dry_response','no_rise'],default='happy');p.add_argument('--seconds',type=int,default=90);a=p.parse_args()
    prefix='plantcare/team3/sim/pothos1/';profile=default('simulated');device=Actuator(profile,boot='sim-'+str(time.time_ns()));incoming=queue.Queue();events=[];seq=0
    client=mqtt.Client(mqtt.CallbackAPIVersion.VERSION2,client_id='team3-sim-sensor',clean_session=True,protocol=mqtt.MQTTv311)
    status=dict(schema=1,mode='simulated',client='sensor',boot_id=device.boot,status='offline',ts=None)
    client.will_set(prefix+'status/sensor',json.dumps(status),qos=1,retain=True);client.tls_set(a.ca,a.cert,a.key,tls_version=ssl.PROTOCOL_TLS_CLIENT);client.reconnect_delay_set(1,30)
    def connected(c,userdata,flags,reason,properties):
        if reason.is_failure:return
        c.subscribe([(prefix+'watering/command',1),(prefix+'control/command',1)])
        c.publish(prefix+'status/sensor',json.dumps({**status,'status':'online','ts':utc(time.time())}),qos=1,retain=True)
    client.on_connect=connected
    def received(c,userdata,message):
        if len(message.payload)<=4096:
            try:incoming.put(json.loads(message.payload))
            except (ValueError,UnicodeError):print('Malformed command ignored')
    client.on_message=received;client.connect(a.endpoint,8883,keepalive=30);client.loop_start();start=time.monotonic();next_sample=start;pending=None
    try:
        while time.monotonic()-start<a.seconds:
            now=time.time();elapsed=time.monotonic()-start
            event=device.tick(now)
            if event:events.append(event)
            if time.monotonic()>=next_sample:
                seq+=1;s=packet(now,seq,boot=device.boot,**readings(a.scenario,elapsed,device));device.sample=s
                s['pump'].update(on=device.current is not None,armed=device.armed,fault='local_fault' if device.fault else None,active_command_id=device.current['command_id'] if device.current else None,cooldown_remaining_s=max(0,device.cool_until-now))
                info=client.publish(prefix+'telemetry',json.dumps(s),qos=1,retain=False)
                if info.rc==mqtt.MQTT_ERR_SUCCESS:print('QUEUED',device.boot,seq,flush=True)
                next_sample+=2
            while not incoming.empty():
                try:event=device.accept(incoming.get_nowait(),now)
                except (KeyError,TypeError,ValueError):event=None
                if event:events.append(event)
            if pending and pending.is_published():events.pop(0);pending=None
            if events and pending is None and client.is_connected():
                e=events[0];pending=client.publish(prefix+('watering/event' if e['action']=='water' else 'control/event'),json.dumps(e),qos=1,retain=False)
                if pending.rc!=mqtt.MQTT_ERR_SUCCESS:pending=None
            time.sleep(.05)
    finally:
        # Stop accepting commands, drain a current simulated dose, then publish final events.
        if device.current:
            time.sleep(device.current['duration_ms']/1000);e=device.tick(time.time())
            if e:events.append(e)
        for e in events:
            info=client.publish(prefix+('watering/event' if e['action']=='water' else 'control/event'),json.dumps(e),qos=1,retain=False);info.wait_for_publish(timeout=5)
        client.publish(prefix+'status/sensor',json.dumps({**status,'ts':utc(time.time())}),qos=1,retain=True).wait_for_publish(timeout=5);client.disconnect();client.loop_stop()
if __name__=='__main__':main()
