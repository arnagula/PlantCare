"""Serialized durable application owner, with a persisted at-least-once publish outbox."""
import copy
import json
import uuid
from .contracts import telemetry, event, status, require, timestamp, utc, Rejected
from .engine import Engine, empty_rule
from .watering import Watering, ACTIVE
from .profile import validate

class Service:
    def __init__(self,store,publish,profile,generation='deployment-1'):
        self.store=store; self.publish=publish; self.profile=validate(profile); self.mode=profile['mode']; self.generation=generation
        self.prefix='plantcare/team3/'+('pothos1/' if self.mode=='live' else 'sim/pothos1/')
    def load(self):
        state=self.store.load(self.mode)
        if not state: state=dict(version=0,generation=self.generation,backend_boot_id=str(uuid.uuid4()),report_seq=0,engine=None,water=None,outbox=[],last_condition=None,last_now=None,connections={},profile=self.profile)
        return state
    def flush(self):
        state=self.load()
        if not state['outbox']: return
        for item in state['outbox']:
            self.publish(item['topic'],item['payload'],item['retain'])
        state['outbox']=[]
        self.store.commit(self.mode,state['version'],state,{})
    def report(self,state,engine,water,now):
        s=engine.state['sample']; report=engine.assess(now); watering=water.snapshot(now)
        if watering['stage']=='FAULT': report.update(state='watering_fault',mood='sad',reason=('Check watering system: inspect reservoir, tubing and sensor. Low rise is a heuristic.' if watering['fault']=='insufficient_rise' else watering['fault']))
        elif watering['stage'] in ('COMMAND_PENDING','RUNNING'): report.update(state='watering',mood='regular',reason='Watering transaction in progress')
        elif watering['stage']=='OBSERVING': report.update(state='checking_moisture',mood='regular',reason='Checking post-dose moisture rise')
        state['report_seq']+=1
        return dict(schema=1,mode=self.mode,profile=s['profile'] if s else 'normal',ts=utc(now),report_seq=state['report_seq'],backend_boot_id=state['backend_boot_id'],profile_revision=self.profile['profile_revision'],sample_ts=s['ts'] if s else None,source={k:s[k] for k in ('device_id','boot_id','seq')} if s else None,freshness_timeout_s=engine.timeout(),watering=watering,**report)
    def handle(self,kind,payload,now,received_at=None):
        self.flush(); state=self.load(); self.profile=validate(state.get('profile',self.profile)); records={}; engine=Engine(self.profile,state['engine']); water=Watering(self.profile,state['water']); sample=engine.state['sample']; initial_stage=water.state['stage']
        if state['generation']!=self.generation:
            if water.state['stage'] in ACTIVE or water.state['control']: water.fault('backend_restart')
            else: water.state['stage']='DISARMED'
            if sample: water.state['cool_until']=max(water.state['cool_until'],now+water.cooldown(sample))
            state.update(generation=self.generation,backend_boot_id=str(uuid.uuid4()),report_seq=0)
        if state['last_now'] is not None and now<state['last_now']: water.fault('clock_invalid')
        result={'status':'accepted'}
        try:
            if kind=='telemetry':
                telemetry(payload,self.mode,received_at if received_at is not None else now)
                identity='SAMPLE#'+json.dumps([payload['device_id'],payload['boot_id'],payload['seq']],separators=(',',':'))
                old=self.store.get(self.mode,identity)
                if old:
                    require(old['payload']==payload,'conflicting_duplicate')
                    return {'status':'duplicate'}
                engine.update(payload,now); sample=engine.state['sample']
                water.state['profile']=sample['profile']; water.sample(sample,now)
                records[identity]=dict(payload=payload,ts=payload['ts'],received_at=utc(received_at if received_at is not None else now))
                values={k:(payload[k]['value'],payload[k]['valid']) for k in ('temperature_c','humidity_pct','light_lux')}
                values.update(soil_raw=(payload['soil']['raw'],payload['soil']['raw_valid']),soil_pct=(payload['soil']['pct'],payload['soil']['valid']))
                for metric,(value,valid) in values.items():
                    records['READING#'+metric+'#'+payload['ts']+'#'+identity]=dict(ts=payload['ts'],received_at=utc(received_at if received_at is not None else now),mode=self.mode,metric=metric,value=value,valid=valid,unit={'temperature_c':'C','humidity_pct':'%RH','light_lux':'lux','soil_pct':'%','soil_raw':'raw'}[metric],calibrated=payload['soil']['calibrated'] if metric.startswith('soil_') else True,source=identity,sample_interval_s=payload['sample_interval_s'])
            elif kind=='event':
                event(payload,self.mode)
                require(timestamp(payload['ts'])<=now+5,'future_event')
                require(payload['device_id']==('sensor-01' if self.mode=='live' else 'sim-sensor-01'),'device_id')
                identity='EVENTID#'+json.dumps([payload['device_id'],payload['boot_id'],payload['event_seq']],separators=(',',':'))
                old=self.store.get(self.mode,identity)
                if old:
                    require(old==payload,'conflicting_event'); return {'status':'duplicate'}
                known=self.store.get(self.mode,'COMMANDID#'+payload['command_id'])
                require(known is not None and known['target_boot_id']==payload['boot_id'] and known['action']==payload['action'],'unknown_event')
                current=water.state['command'] if payload['action']=='water' else water.state['control']
                if current and current['command_id']==payload['command_id']:
                    previous=water.dump()
                    try:water.event(payload,now)
                    except (Rejected,KeyError,TypeError,ValueError):
                        water=Watering(self.profile,previous)
                        raise
                records[identity]=payload
                stored_event={**payload,'received_at':utc(received_at if received_at is not None else now)}
                records['EVENT#'+payload['ts']+'#'+identity]=stored_event
                records['LOG#'+payload['ts']+'#'+identity]=stored_event
            elif kind=='status':
                status(payload,self.mode)
                if payload['ts'] is not None: require(timestamp(payload['ts'])<=now+5,'future_status')
                state['connections'][payload['client']]={'payload':payload,'received_at':utc(now)}
            elif kind=='request':
                request_id=payload.get('request_id'); require(isinstance(request_id,str) and 0<len(request_id)<=64,'request_id')
                key='REQUEST#'+request_id; prior=self.store.get(self.mode,key)
                if prior:
                    require(prior['request']==payload,'request_id_conflict'); return prior['result']
                cmd=water.request(payload.get('action'),sample,now,request_id,payload.get('inspected') is True)
                result={'status':'queued','command_id':cmd['command_id']}
                records[key]=dict(ts=utc(now),request=payload,result=result)
                records['COMMAND#'+utc(now)+'#'+cmd['command_id']]={**cmd,'request_id':request_id,'status':'queued','fault':None}
                records['COMMANDID#'+cmd['command_id']]=cmd
                records['LOG#'+utc(now)+'#'+cmd['command_id']]=dict(ts=utc(now),status='queued',**cmd)
                state['outbox'].append(dict(topic=self.prefix+('watering/' if cmd['action']=='water' else 'control/')+'command',payload=cmd,retain=False))
            elif kind=='reload':
                require(water.state['stage'] not in ACTIVE|{'COOLDOWN'} and not water.state['control'],'busy')
                new=validate(payload); require(new['mode']==self.mode,'mode')
                require(new['profile_revision']!=self.profile['profile_revision'],'profile_revision')
                self.profile=new;state['profile']=new;engine=Engine(new);sample=None
                water.profile=new
                if water.state['stage']!='FAULT':water.state['stage']='DISARMED'
                records['PROFILE#'+utc(now)]=dict(ts=utc(now),profile=new)
            elif kind!='tick': raise Rejected('kind')
        except (Rejected,KeyError,TypeError,ValueError) as exc:
            result={'status':'rejected','reason':str(exc)[:119]}
            records['REJECTION#'+utc(now)+'#'+str(uuid.uuid4())]=dict(ts=utc(now),kind=kind,reason=str(exc)[:119])
            if kind=='request' and isinstance(payload,dict) and isinstance(payload.get('request_id'),str) and 0<len(payload['request_id'])<=64 and self.store.get(self.mode,'REQUEST#'+payload['request_id']) is None:
                records['REQUEST#'+payload['request_id']]=dict(ts=utc(now),request=payload,result=result)
        before=initial_stage
        if water.tick(sample,now): engine.state['rules']['thirsty']=empty_rule()
        assessed=engine.assess(now)
        if water.state['stage']=='READY' and 'thirsty' in assessed['issues'] and assessed['data_status']=='ok' and not water.block('water',sample,now):
            cmd=water.request('water',sample,now,'auto-'+str(uuid.uuid4()),automatic=True)
            records['COMMAND#'+utc(now)+'#'+cmd['command_id']]=cmd
            records['COMMANDID#'+cmd['command_id']]=cmd
            records['LOG#'+utc(now)+'#'+cmd['command_id']]=dict(ts=utc(now),status='queued',**cmd)
            state['outbox'].append(dict(topic=self.prefix+'watering/command',payload=cmd,retain=False))
        if water.state['stage']!=before:
            records['LOG#'+utc(now)+'#outcome-'+str(uuid.uuid4())]=dict(ts=utc(now),action='water',status=water.state['stage'],reason_code=water.state['fault'],command_id=water.snapshot(now)['command_id'],response=water.state.get('response'),baseline=water.state['baseline'],completed_at=water.state['completed'])
        report=self.report(state,engine,water,now)
        signature={k:report[k] for k in ('data_status','invalid_fields','state','mood','issues','watering')}
        signature['watering']={k:v for k,v in signature['watering'].items() if k!='cooldown_remaining_s'}
        if signature!=state['last_condition']:
            records['CONDITION#'+utc(now)+'#'+str(state['report_seq'])]=report
            state['last_condition']=signature
        state.update(engine=engine.dump(),water=water.dump(),last_now=now)
        state['outbox'].append(dict(topic=self.prefix+'condition',payload=report,retain=True))
        state['outbox'].append(dict(topic=self.prefix+'status/backend',payload=dict(schema=1,mode=self.mode,client='backend',boot_id=state['backend_boot_id'],status='online',ts=utc(now)),retain=True))
        self.store.commit(self.mode,state['version'],state,records)
        self.flush()
        return result
    def get_state(self,now):
        state=self.load(); self.profile=validate(state.get('profile',self.profile)); engine=Engine(self.profile,state['engine']); water=Watering(self.profile,state['water'])
        report=self.report(state,engine,water,now); sample=engine.state['sample']
        report.update(values=sample,connections=state['connections'],availability={a:water.block(a,sample,now,a=='reset_fault') for a in ('water','arm','disarm','reset_fault')})
        return report
