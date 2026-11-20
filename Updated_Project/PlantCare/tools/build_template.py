"""Generate a reviewable SAM template; does not create any AWS resources."""
import json
from pathlib import Path
R={}
def ref(x):return {'Ref':x}
def arn(x):return {'Fn::GetAtt':[x,'Arn']}
def sub(x):return {'Fn::Sub':x}
def resource(name,typ,props,**extra):R[name]={'Type':typ,'Properties':props,**extra}
def statement(actions,resources):return {'Effect':'Allow','Action':actions,'Resource':resources}
resource('History','AWS::DynamoDB::Table',dict(BillingMode='PAY_PER_REQUEST',AttributeDefinitions=[{'AttributeName':x,'AttributeType':'S'} for x in ('pk','sk')],KeySchema=[{'AttributeName':'pk','KeyType':'HASH'},{'AttributeName':'sk','KeyType':'RANGE'}],PointInTimeRecoverySpecification={'PointInTimeRecoveryEnabled':True}),DeletionPolicy='Retain',UpdateReplacePolicy='Retain')
for mode,name in [('live','Live'),('simulated','Sim')]:
    resource(name+'DLQ','AWS::SQS::Queue',{'FifoQueue':True,'MessageRetentionPeriod':1209600})
    resource(name+'Queue','AWS::SQS::Queue',{'FifoQueue':True,'VisibilityTimeout':180,'RedrivePolicy':{'deadLetterTargetArn':arn(name+'DLQ'),'maxReceiveCount':5}})
    resource(name+'DeadLetterAlarm','AWS::CloudWatch::Alarm',{'Namespace':'AWS/SQS','MetricName':'ApproximateNumberOfMessagesVisible','Dimensions':[{'Name':'QueueName','Value':{'Fn::GetAtt':[name+'DLQ','QueueName']}}],'Statistic':'Maximum','Period':60,'EvaluationPeriods':1,'Threshold':0,'ComparisonOperator':'GreaterThanThreshold','TreatMissingData':'notBreaching'})
    prefix='plantcare/team3/'+('pothos1/' if mode=='live' else 'sim/pothos1/')
    variables={'EXPECTED_MODE':mode,'HISTORY_TABLE':ref('History'),'IOT_DATA_ENDPOINT':ref('IoTDataEndpoint'),'BACKEND_GENERATION':ref('BackendGeneration'),'LIVE_QUEUE':ref('LiveQueue'),'SIM_QUEUE':ref('SimQueue')}
    pub=[sub('arn:${AWS::Partition}:iot:${AWS::Region}:${AWS::AccountId}:topic/'+prefix+x) for x in ('condition','watering/command','control/command','status/backend')]
    resource(name+'Worker','AWS::Serverless::Function',dict(CodeUri='.',Runtime='python3.12',Handler='aws.handler.worker',Timeout=30,Environment={'Variables':variables},Policies=[{'Statement':[statement(['dynamodb:GetItem','dynamodb:PutItem'],arn('History')),statement('iot:Publish',pub),statement('iot:RetainPublish',[pub[0],pub[3]])]}],Events={'Queue':{'Type':'SQS','Properties':{'Queue':arn(name+'Queue'),'BatchSize':1}}}))
    events={}
    for i,tail in enumerate(('telemetry','watering/event','control/event','status/sensor','status/display')):
        events['Topic'+str(i)]={'Type':'IoTRule','Properties':{'Sql':"SELECT encode(*, 'base64') AS raw_payload, topic() AS source_topic FROM '"+prefix+tail+"'",'AwsIotSqlVersion':'2016-03-23'}}
    resource(name+'Ingress','AWS::Serverless::Function',dict(CodeUri='.',Runtime='python3.12',Handler='aws.handler.ingress',Timeout=15,Environment={'Variables':variables},Policies=[{'Statement':[statement('sqs:SendMessage',arn(name+'Queue'))]}],Events=events))
    for role in ('sensor','display'):
        clientid='team3-'+('sim-' if mode=='simulated' else '')+role
        publishes=['status/'+role]+(['telemetry','watering/event','control/event'] if role=='sensor' else [])
        subscribes=['watering/command','control/command'] if role=='sensor' else ['condition','status/backend']
        topicarn=lambda kind,tail:sub('arn:${AWS::Partition}:iot:${AWS::Region}:${AWS::AccountId}:'+kind+'/'+prefix+tail)
        resource(name+role.title()+'Policy','AWS::IoT::Policy',{'PolicyDocument':{'Version':'2012-10-17','Statement':[statement('iot:Connect',sub('arn:${AWS::Partition}:iot:${AWS::Region}:${AWS::AccountId}:client/'+clientid)),statement('iot:Publish',[topicarn('topic',x) for x in publishes]),statement('iot:RetainPublish',[topicarn('topic','status/'+role)]),statement('iot:Subscribe',[topicarn('topicfilter',x) for x in subscribes]),statement('iot:Receive',[topicarn('topic',x) for x in subscribes])]}})
resource('Heartbeat','AWS::Serverless::Function',dict(CodeUri='.',Runtime='python3.12',Handler='aws.handler.heartbeat',Timeout=65,Environment={'Variables':{'LIVE_QUEUE':ref('LiveQueue'),'SIM_QUEUE':ref('SimQueue')}},Policies=[{'Statement':[statement('sqs:SendMessage',[arn('LiveQueue'),arn('SimQueue')])]}],Events={'Pulse':{'Type':'Schedule','Properties':{'Schedule':'rate(1 minute)'}}}))
resource('HttpApi','AWS::Serverless::HttpApi',{'Auth':{'DefaultAuthorizer':'Jwt','Authorizers':{'Jwt':{'IdentitySource':'$request.header.Authorization','JwtConfiguration':{'issuer':ref('JwtIssuer'),'audience':[ref('JwtAudience')]}}}}})
events={}
# Preserve the logical IDs of the existing private routes.
for i,(path,method) in enumerate([('/api/state','GET'),('/api/history','GET'),('/api/watering','GET'),('/api/request','GET'),('/api/watering','POST'),('/api/watering/arm','POST'),('/api/watering/disarm','POST'),('/api/watering/reset','POST'),('/api/water','POST'),('/api/arm','POST'),('/api/disarm','POST'),('/api/reset_fault','POST')], start=3):
    props={'ApiId':ref('HttpApi'),'Path':path,'Method':method}
    events['Route'+str(i)]={'Type':'HttpApi','Properties':props}
resource('Api','AWS::Serverless::Function',dict(CodeUri='.',Runtime='python3.12',Handler='aws.api.handler',Timeout=30,Environment={'Variables':{'HISTORY_TABLE':ref('History'),'IOT_DATA_ENDPOINT':ref('IoTDataEndpoint'),'BACKEND_GENERATION':ref('BackendGeneration'),'LIVE_QUEUE':ref('LiveQueue'),'SIM_QUEUE':ref('SimQueue')}},Policies=[{'Statement':[statement(['dynamodb:GetItem','dynamodb:Query','dynamodb:PutItem'],arn('History')),statement('sqs:SendMessage',[arn('LiveQueue'),arn('SimQueue')])]}],Events=events))
demo_events = {
    name: {'Type': 'HttpApi', 'Properties': {
        'ApiId': ref('HttpApi'), 'Path': path, 'Method': 'GET',
        'Auth': {'Authorizer': 'NONE'},
    }}
    for name, path in [('Home', '/'), ('Script', '/app.js'), ('Styles', '/style.css'),
                       ('Telemetry', '/api/demo/telemetry')]
}
demo_read = statement('dynamodb:GetItem', arn('History'))
demo_read['Condition'] = {'ForAllValues:StringEquals': {'dynamodb:LeadingKeys': ['live']},
                          'Null': {'dynamodb:LeadingKeys': 'false'}}
resource('Demo', 'AWS::Serverless::Function', dict(
    CodeUri='.', Runtime='python3.12', Handler='aws.demo.handler', Timeout=5,
    Environment={'Variables': {'HISTORY_TABLE': ref('History')}},
    Policies=[{'Statement': [demo_read]}], Events=demo_events,
))
for mode,name in [('live','Live'),('simulated','Sim')]:
    R[name+'Worker']['Properties']['Policies'][0]['Statement'][0]['Condition']={'ForAllValues:StringEquals':{'dynamodb:LeadingKeys':[mode]}}
for name,value in R.items():
    if value['Type']=='AWS::Serverless::Function':value['Metadata']={'BuildMethod':'makefile'}
template={'AWSTemplateFormatVersion':'2010-09-09','Transform':'AWS::Serverless-2016-10-31','Parameters':{k:{'Type':'String',**({'Default':'deployment-1'} if k=='BackendGeneration' else {})} for k in ('IoTDataEndpoint','JwtIssuer','JwtAudience','BackendGeneration')},'Resources':R,'Outputs':{'Dashboard':{'Value':sub('https://${HttpApi}.execute-api.${AWS::Region}.${AWS::URLSuffix}/')}}}
Path('template.yaml').write_text(json.dumps(template,indent=2)+'\n')
