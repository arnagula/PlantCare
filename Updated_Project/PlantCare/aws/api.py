"""Authenticated HTTP API; requests enter the same FIFO as device events."""
import json
import uuid
from pathlib import Path
import time
from .handler import service,enqueue
from plantcare.contracts import require,timestamp,utc,Rejected

ROOT=Path(__file__).resolve().parents[1]/'dashboard'
def response(code,body,content_type='application/json'):
    return dict(statusCode=code,headers={'content-type':content_type,'cache-control':'no-store','content-security-policy':"default-src 'self'; connect-src 'self'; script-src 'self'; style-src 'self'; frame-ancestors 'none'",'x-content-type-options':'nosniff'},body=json.dumps(body,allow_nan=False) if content_type=='application/json' else body)

def handler(event,context):
    path=event.get('rawPath','/'); method=event.get('requestContext',{}).get('http',{}).get('method','GET')
    if method=='GET' and path in ('/','/app.js','/style.css'):
        name={'/':'index.html','/app.js':'app.js','/style.css':'style.css'}[path]
        return response(200,(ROOT/name).read_text(),{'/':'text/html','/app.js':'text/javascript','/style.css':'text/css'}[path])
    claims=event.get('requestContext',{}).get('authorizer',{}).get('jwt',{}).get('claims',{})
    if not claims.get('sub'):return response(401,{'error':'unauthorized'})
    try:
        q=event.get('queryStringParameters') or {};mode=q.get('mode','live');require(mode in ('live','simulated'),'mode');app=service(mode);now=time.time()
        if method=='GET' and path=='/api/state':return response(200,app.get_state(now))
        if method=='GET' and path=='/api/request':
            require(isinstance(q.get('request_id'),str) and len(q['request_id'])<=64,'request_id')
            r=app.store.get(mode,'REQUEST#'+q['request_id'])
            return response(200 if r else 202,r['result'] if r else {'status':'pending'})
        if method=='GET' and path in ('/api/history','/api/watering'):
            start=q.get('start',utc(now-3600));end=q.get('end',utc(now));require(timestamp(start)<=timestamp(end),'range')
            limit=int(q.get('limit','2000'));require(1<=limit<=2000,'page_limit')
            if path=='/api/history':
                metric=q.get('metric','soil_pct');require(metric in ('soil_raw','soil_pct','temperature_c','humidity_pct','light_lux'),'metric');prefix='READING#'+metric+'#'
            else: prefix='LOG#'
            # Time cursor includes deterministic key through the store page adapter.
            rows,cursor=app.store.page(mode,prefix,start,end,limit,q.get('cursor'))
            return response(200,{'rows':rows,'cursor':cursor})
        actions={'/api/watering':'water','/api/watering/arm':'arm','/api/watering/disarm':'disarm','/api/watering/reset':'reset_fault','/api/water':'water','/api/arm':'arm','/api/disarm':'disarm','/api/reset_fault':'reset_fault'}
        if method=='POST' and path in actions:
            require(not event.get('isBase64Encoded'),'encoding');raw=event.get('body','');require(len(raw.encode())<=4096,'size');p=json.loads(raw)
            require(isinstance(p,dict) and set(p)<= {'request_id','inspected'},'request_fields')
            request_id=p.get('request_id');require(isinstance(request_id,str) and 0<len(request_id)<=64,'request_id')
            action=actions[path];p['action']=action
            if action=='reset_fault': require(p.get('inspected') is True,'inspected')
            prior=app.store.get(mode,'REQUEST#'+request_id)
            if prior:
                if prior['request']!=p:return response(409,{'error':'request_id_conflict'})
                return response(200,prior['result'])
            reserved=app.store.get(mode,'SUBMISSION#'+request_id)
            if reserved:
                if reserved['request']!=p:return response(409,{'error':'request_id_conflict'})
                if reserved['code']==409:return response(409,reserved['result'])
                enqueue(mode,'request',p) # safe retry after an ambiguous enqueue result
                return response(200,reserved['result'])
            blocked=app.get_state(now)['availability'][action]
            result={'error':blocked} if blocked else {'status':'queued','request_id':request_id,'command_id':str(uuid.uuid5(uuid.NAMESPACE_URL,mode+':'+request_id))}
            reservation={'request':p,'code':409 if blocked else 202,'result':result}
            chosen,created=app.store.reserve(mode,'SUBMISSION#'+request_id,reservation)
            if chosen['request']!=p:return response(409,{'error':'request_id_conflict'})
            if chosen['code']==409:return response(409,chosen['result'])
            enqueue(mode,'request',p)
            return response(202 if created else 200,chosen['result'])
        return response(404,{'error':'not_found'})
    except (Rejected,ValueError,KeyError,TypeError):return response(400,{'error':'malformed'})
