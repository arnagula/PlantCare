"""Direct Live ingestion and FIFO Simulation ingestion."""
import base64
import json
import os
from pathlib import Path
import time
import uuid
from plantcare.contracts import integer, require
from plantcare.profile import validate
from plantcare.storage import DynamoStore
from plantcare.service import Service

def client(name):
    import boto3
    return boto3.client(name,**({'endpoint_url':'https://'+os.environ['IOT_DATA_ENDPOINT']} if name=='iot-data' else {}))

def profile(mode):
    require(mode in ('live','simulated'),'mode')
    return validate(json.loads((Path(__file__).resolve().parents[1]/'profiles'/(mode+'.json')).read_text()))

def service(mode):
    def publish(topic,payload,retain):
        client('iot-data').publish(topic=topic,qos=1,retain=retain,payload=json.dumps(payload,allow_nan=False,separators=(',',':')).encode())
    return Service(DynamoStore(client('dynamodb'),os.environ['HISTORY_TABLE']),publish,profile(mode),os.environ['BACKEND_GENERATION'])

def enqueue(mode,kind,payload,received_at=None):
    queue=os.environ['LIVE_QUEUE' if mode=='live' else 'SIM_QUEUE']
    return client('sqs').send_message(QueueUrl=queue,MessageGroupId=mode,MessageDeduplicationId=str(uuid.uuid4()),MessageBody=json.dumps(dict(kind=kind,payload=payload,received_at=received_at if received_at is not None else time.time()),allow_nan=False))

def ingress(event,context):
    mode=os.environ['EXPECTED_MODE']; prefix='plantcare/team3/'+('pothos1/' if mode=='live' else 'sim/pothos1/')
    topic=event.get('source_topic','');require(topic.startswith(prefix),'topic')
    tail=topic[len(prefix):]
    require(tail in ('telemetry','watering/event','control/event','status/sensor','status/display'),'topic')
    raw=base64.b64decode(event['raw_payload'],validate=True); require(len(raw)<=4096,'wire_size')
    payload=json.loads(raw);require(isinstance(payload,dict) and payload.get('mode')==mode,'mode')
    if tail in ('watering/event','control/event'):
        require((tail=='watering/event')==(payload.get('action')=='water'),'event_topic')
    if tail.startswith('status/'): require(payload.get('client')==tail.split('/')[1],'status_client')
    kind = 'telemetry' if tail == 'telemetry' else ('status' if tail.startswith('status/') else 'event')
    if mode == 'live':
        received_ms = event.get('received_ms')
        require(integer(received_ms, 1), 'received_ms')
        return service(mode).handle(kind, payload, time.time(), received_ms / 1000)
    return enqueue(mode, kind, payload)

def worker(event,context):
    mode=os.environ['EXPECTED_MODE']; app=service(mode)
    require(len(event['Records'])==1,'FIFO batch must be one')
    item=json.loads(event['Records'][0]['body'])
    return app.handle(item['kind'],item['payload'],time.time(),item['received_at'])

def heartbeat(event,context):
    # EventBridge runs once/minute. Bounded loop provides two-second stale checks.
    start=time.monotonic()
    for i in range(30):
        for mode in ('live','simulated'): enqueue(mode,'tick',{})
        delay=start+(i+1)*2-time.monotonic()
        if delay>0: time.sleep(delay)
