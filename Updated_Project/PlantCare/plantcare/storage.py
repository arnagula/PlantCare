"""Atomic state plus journal storage. One FIFO message group per plant/mode."""
import copy
import json

class Conflict(RuntimeError): pass

class MemoryStore:
    def __init__(self): self.states={}; self.records={}
    def load(self,mode): return copy.deepcopy(self.states.get(mode))
    def get(self,mode,key): return copy.deepcopy(self.records.get((mode,key)))
    def commit(self,mode,version,state,records):
        old=self.states.get(mode)
        if (old['version'] if old else 0)!=version: raise Conflict('version')
        for key,value in records.items():
            prior=self.records.get((mode,key))
            if prior is not None and prior!=value: raise Conflict('immutable_record')
        for key,value in records.items(): self.records[(mode,key)]=copy.deepcopy(value)
        self.states[mode]=copy.deepcopy({**state,'version':version+1})
    def reserve(self,mode,key,payload):
        prior=self.records.get((mode,key))
        if prior is not None:return copy.deepcopy(prior),False
        self.records[(mode,key)]=copy.deepcopy(payload)
        return payload,True
    def page(self,mode,prefix,start,end,limit,cursor=None):
        offset=int(cursor or 0)
        rows=self.history(mode,prefix,start,end)
        chunk=rows[offset:offset+limit]
        return chunk,str(offset+limit) if offset+limit<len(rows) else None
    def history(self,mode,prefix,start,end,limit=400000):
        return [copy.deepcopy(v) for (m,k),v in sorted(self.records.items()) if m==mode and k.startswith(prefix) and start<=v.get('ts','')<=end][:min(limit,400000)]

class DynamoStore:
    def __init__(self,client,table): self.client=client; self.table=table
    def key(self,mode,key): return {'pk':{'S':mode},'sk':{'S':key}}
    def get(self,mode,key):
        r=self.client.get_item(TableName=self.table,Key=self.key(mode,key),ConsistentRead=True).get('Item')
        return json.loads(r['body']['S']) if r else None
    def load(self,mode): return self.get(mode,'STATE')
    def commit(self,mode,version,state,records):
        body={**state,'version':version+1}
        put=dict(TableName=self.table,Item={**self.key(mode,'STATE'),'body':{'S':json.dumps(body,allow_nan=False)},'version':{'N':str(version+1)}},ConditionExpression='attribute_not_exists(pk)' if version==0 else '#v = :v')
        if version: put.update(ExpressionAttributeNames={'#v':'version'},ExpressionAttributeValues={':v':{'N':str(version)}})
        transaction=[{'Put':put}]
        for key,value in records.items():
            transaction.append({'Put':dict(TableName=self.table,Item={**self.key(mode,key),'body':{'S':json.dumps(value,allow_nan=False)}},ConditionExpression='attribute_not_exists(pk)')})
        if len(transaction)>100: raise ValueError('transaction item limit')
        self.client.transact_write_items(TransactItems=transaction)
    def history(self,mode,prefix,start,end,limit=400000):
        limit=min(limit,400000); result=[]; cursor=None
        while len(result)<limit:
            args=dict(TableName=self.table,KeyConditionExpression='pk = :m AND sk BETWEEN :a AND :b',ExpressionAttributeValues={':m':{'S':mode},':a':{'S':prefix+start},':b':{'S':prefix+end+'~'}},ConsistentRead=True,Limit=min(2000,limit-len(result)))
            if cursor: args['ExclusiveStartKey']=cursor
            response=self.client.query(**args)
            result.extend(json.loads(x['body']['S']) for x in response.get('Items',[]))
            cursor=response.get('LastEvaluatedKey')
            if not cursor: break
        return result
    def reserve(self,mode,key,payload):
        try:
            self.client.put_item(TableName=self.table,Item={**self.key(mode,key),'body':{'S':json.dumps(payload)}},ConditionExpression='attribute_not_exists(pk)')
            return payload,True
        except self.client.exceptions.ConditionalCheckFailedException:
            return self.get(mode,key),False
    def page(self,mode,prefix,start,end,limit,cursor=None):
        import base64
        args=dict(TableName=self.table,KeyConditionExpression='pk = :m AND sk BETWEEN :a AND :b',ExpressionAttributeValues={':m':{'S':mode},':a':{'S':prefix+start},':b':{'S':prefix+end+'~'}},ConsistentRead=True,Limit=limit)
        if cursor:
            key=json.loads(base64.urlsafe_b64decode(cursor).decode())
            if key.get('pk')!={'S':mode} or not prefix+start<=key.get('sk',{}).get('S','')<=prefix+end+'~':raise ValueError('cursor')
            args['ExclusiveStartKey']=key
        r=self.client.query(**args);key=r.get('LastEvaluatedKey')
        return [json.loads(x['body']['S']) for x in r.get('Items',[])],base64.urlsafe_b64encode(json.dumps(key).encode()).decode() if key else None
