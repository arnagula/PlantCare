import base64,copy,json,os,unittest
from unittest.mock import patch,Mock
from plantcare import contracts as c
from plantcare.profile import default
from plantcare.service import Service
from plantcare.storage import MemoryStore,DynamoStore
from tools.scenarios import packet
from tools.run_demo import run
from aws import handler,api
T=c.timestamp('2026-11-12T15:00:00.000Z')
class Adapters(unittest.TestCase):
 def test_ingress_enqueues_only_trusted_mode(self):
  e={'source_topic':'plantcare/team3/sim/pothos1/telemetry','raw_payload':base64.b64encode(json.dumps(packet(T,1)).encode()).decode()}
  with patch.dict(os.environ,EXPECTED_MODE='simulated'),patch.object(handler,'enqueue') as queue:
   handler.ingress(e,None);self.assertEqual(queue.call_args.args[:2],('simulated','telemetry'))
   e['source_topic']='plantcare/team3/pothos1/telemetry'
   with self.assertRaises(c.Rejected):handler.ingress(e,None)
 def test_wire_size(self):
  e={'source_topic':'plantcare/team3/sim/pothos1/telemetry','raw_payload':base64.b64encode(b' '*4097).decode()}
  with patch.dict(os.environ,EXPECTED_MODE='simulated'):
   with self.assertRaises(c.Rejected):handler.ingress(e,None)
 def test_worker_single_record(self):
  app=Mock()
  with patch.dict(os.environ,EXPECTED_MODE='simulated'),patch.object(handler,'service',return_value=app):
   handler.worker({'Records':[{'body':json.dumps({'kind':'tick','payload':{},'received_at':T})}]},None);app.handle.assert_called_once()
 def test_fifo_template(self):
  r=json.load(open('template.yaml'))['Resources']
  for name in ('Live','Sim'):
   self.assertTrue(r[name+'Queue']['Properties']['FifoQueue']);self.assertEqual(r[name+'Worker']['Properties']['Events']['Queue']['Properties']['BatchSize'],1)
 def test_worker_put_permission(self):
  r=json.load(open('template.yaml'))['Resources']
  for name in ('Live','Sim'):
   statements=r[name+'Worker']['Properties']['Policies'][0]['Statement'];self.assertIn('dynamodb:PutItem',statements[0]['Action'])
 def test_sim_publish_isolation(self):
  r=json.load(open('template.yaml'))['Resources']['SimWorker']['Properties']['Policies'][0]['Statement']
  self.assertTrue(all('/sim/' in x['Fn::Sub'] for x in r[1]['Resource']))
 def test_api_auth_required(self):self.assertEqual(api.handler({'rawPath':'/api/state'},None)['statusCode'],401)
 def test_all_mutation_routes_jwt(self):
  events=json.load(open('template.yaml'))['Resources']['Api']['Properties']['Events']
  for e in events.values():
   if e['Properties']['Method']=='POST':self.assertNotIn('Auth',e['Properties'])
 def test_state_api(self):
  app=Service(MemoryStore(),lambda *a:None,default('simulated'));app.handle('telemetry',packet(T,1),T)
  e={'rawPath':'/api/state','queryStringParameters':{'mode':'simulated'},'requestContext':{'authorizer':{'jwt':{'claims':{'sub':'operator'}}},'http':{'method':'GET'}}}
  with patch.object(api,'service',return_value=app),patch.object(api.time,'time',return_value=T):
   r=api.handler(e,None);self.assertEqual(r['statusCode'],200);self.assertEqual(json.loads(r['body'])['data_status'],'ok')
 def test_api_no_profile_path(self):
  e={'rawPath':'/api/reload','requestContext':{'authorizer':{'jwt':{'claims':{'sub':'operator'}}},'http':{'method':'POST'}}}
  with patch.object(api,'service',return_value=Mock()):self.assertEqual(api.handler(e,None)['statusCode'],404)
 def test_condition_producer_contract(self):
  app=Service(MemoryStore(),lambda *a:None,default('simulated'));c.condition(app.get_state(T),'simulated');app.handle('telemetry',packet(T,1),T);c.condition(app.get_state(T),'simulated')
 def test_success_end_to_end(self):
  trace,store=run();self.assertEqual(trace[-1]['stage'],'READY');self.assertEqual(trace[-1]['state'],'happy');self.assertTrue(any(t['stage']=='OBSERVING' for t in trace));self.assertTrue(any(k.startswith('COMMAND#') for m,k in store.records))
 def test_failure_end_to_end(self):
  trace,_=run(True);self.assertEqual(trace[-1]['fault'],'insufficient_rise')
 def test_all_generated_events_validate(self):
  _,store=run()
  for (mode,key),event in store.records.items():
   if key.startswith('EVENT#'):c.event(event,'simulated')
 def test_no_simulation_firmware(self):
  from tools.generate_firmware_config import generate
  with self.assertRaises(ValueError):generate(default('simulated'))
 def test_live_unqualified_header(self):
  from tools.generate_firmware_config import generate
  self.assertIn('calibrated = false',generate(default()))

class OtherContracts(unittest.TestCase):pass
VALID_COMMAND=dict(schema=1,mode='live',command_id='cmd',action='water',target_boot_id='boot',config_id='cfg',issued_at=c.utc(T),expires_at=c.utc(T+10),duration_ms=2000,reason='manual')
VALID_EVENT=dict(schema=1,mode='live',device_id='sensor-01',boot_id='b',event_seq=1,command_id='cmd',action='water',status='completed',ts=c.utc(T+2),started_at=c.utc(T),ended_at=c.utc(T+2),actual_duration_ms=2000,baseline_soil_pct=20,pump_on=False,reason_code=None)
VALID_STATUS=dict(schema=1,mode='live',client='sensor',boot_id='b',status='online',ts=c.utc(T))
for name,validator,payload in [('command',c.command,VALID_COMMAND),('event',c.event,VALID_EVENT),('status',c.status,VALID_STATUS)]:
 for key in payload:
  def missing(self,key=key,validator=validator,payload=payload):
   p=copy.deepcopy(payload);del p[key]
   with self.assertRaises(c.Rejected):validator(p)
  setattr(OtherContracts,'test_'+name+'_missing_'+key,missing)

class SDK(unittest.TestCase):
 def setUp(self):
  import boto3
  from botocore.stub import Stubber
  self.client=boto3.client('dynamodb',region_name='us-east-1',aws_access_key_id='test',aws_secret_access_key='test');self.stub=Stubber(self.client);self.store=DynamoStore(self.client,'PlantCareTest')
 def test_consistent_read_shape(self):
  self.stub.add_response('get_item',{},dict(TableName='PlantCareTest',Key={'pk':{'S':'live'},'sk':{'S':'STATE'}},ConsistentRead=True))
  with self.stub:self.assertIsNone(self.store.load('live'))
 def test_transaction_shape(self):
  from botocore.stub import ANY
  self.stub.add_response('transact_write_items',{}, {'TransactItems':ANY})
  with self.stub:self.store.commit('live',0,{'engine':None},{'EVENT#x':{'ts':'x'}})
 def test_query_shape(self):
  from botocore.stub import ANY
  self.stub.add_response('query',{'Items':[]},dict(TableName='PlantCareTest',KeyConditionExpression='pk = :m AND sk BETWEEN :a AND :b',ExpressionAttributeValues=ANY,ConsistentRead=True,Limit=2000))
  with self.stub:self.assertEqual(self.store.page('live','READING#soil_pct#',c.utc(T),c.utc(T+10),2000),([],None))
