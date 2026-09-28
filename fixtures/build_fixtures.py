"""Rebuild small, explicitly synthetic incident recordings; no random outcomes."""
import json
from datetime import datetime,timedelta,timezone
from pathlib import Path
ROOT=Path(__file__).parent
T=datetime(2026,9,26,14,0,tzinfo=timezone.utc)
def ts(s): return (T+timedelta(seconds=s)).isoformat(timespec='milliseconds').replace('+00:00','Z')

def scenario(sid,title,description):
    return {'id':sid,'title':title,'description':description,'started_at':ts(0),'ended_at':ts(480),'events':[]}
def add(s,t,service,kind,name,**kw):
    event={'id':f"{s['id']}-{len(s['events'])+1:03d}",'timestamp':ts(t),'service':service,'kind':kind,'severity':'info','name':name,'message':'','attributes':{}}
    event.update(kw); s['events'].append(event); return event
def metric(s,t,service,name,value,unit='1'): return add(s,t,service,'metric',name,value=value,unit=unit)
def log(s,t,service,msg,severity='error'): return add(s,t,service,'log','application.event',message=msg,severity=severity)
def deploy(s,t,service,version,change): return add(s,t,service,'deployment','deployment.completed',message=f'Deployed {version}',attributes={'version':version,'change':change})
def call(s,t,source,target,duration,error=False,retry=0):
    trace=f"{s['id']}-trace-{len(s['events']):03d}"
    client=add(s,t,source,'span',f'GET /{target}',trace_id=trace,span_id=trace+'-c',duration_ms=duration,severity='error' if error else 'info',attributes={'span.kind':'client','peer.service':target,'retry.attempt':retry})
    add(s,t+.003,target,'span',f'/{target}',trace_id=trace,span_id=trace+'-s',parent_span_id=client['span_id'],duration_ms=max(1,duration-4),severity='error' if error else 'info',attributes={'span.kind':'server','http.response.status_code':503 if error else 200})
def chain(s,t,services,duration,error=False):
    # CLIENT -> remote SERVER -> CLIENT -> remote SERVER, in one trace.
    # Each inner call starts later and completes before its enclosing server span.
    trace=f"{s['id']}-trace-{len(s['events']):03d}"
    parent=None
    for depth,(source,target) in enumerate(zip(services,services[1:])):
        offset=depth*.025
        client_id=trace+f'-c{depth}'
        server_id=trace+f'-s{depth}'
        client=add(s,t+offset,source,'span',f'GET /{target}',trace_id=trace,span_id=client_id,duration_ms=duration-depth*55,severity='error' if error else 'info',attributes={'span.kind':'client','peer.service':target})
        if parent: client['parent_span_id']=parent
        add(s,t+offset+.003,target,'span',f'/{target}',trace_id=trace,span_id=server_id,parent_span_id=client_id,duration_ms=duration-depth*55-8,severity='error' if error else 'info',attributes={'span.kind':'server','http.response.status_code':503 if error else 200})
        parent=server_id

def baseline(s):
    for svc in ['gateway','checkout','inventory','payments']:
        metric(s,0,svc,'http.server.duration.p95',75,'ms')
        metric(s,0,svc,'http.server.error.rate',0,'errors/s')
    call(s,10,'gateway','checkout',65)
    call(s,11,'checkout','inventory',25)
    call(s,12,'checkout','payments',35)

scenarios=[]
s=scenario('pool-pressure','Checkout stalls after inventory release','Checkout errors rise after an inventory deployment. Compare database evidence with upstream symptoms.'); baseline(s)
metric(s,15,'inventory','db.pool.utilization',.28); deploy(s,180,'inventory','2.8.1','Pool maximum changed from 20 to 4.'); deploy(s,170,'payments','4.2.3','Updated request logging format.')
metric(s,205,'inventory','db.pool.utilization',1); metric(s,206,'inventory','db.pool.pending',42,'connections'); log(s,207,'inventory','Acquire connection timeout: connection pool exhausted after 2000 ms.')
for t in [210,240,270]:
    chain(s,t,['gateway','checkout','inventory'],2090,True)
metric(s,225,'inventory','http.server.duration.p95',2100,'ms');metric(s,227,'checkout','http.server.error.rate',18,'errors/s');log(s,230,'checkout','Inventory request exceeded deadline.');metric(s,235,'payments','http.server.duration.p95',72,'ms')
scenarios.append(s)
s=scenario('downstream-latency','Payment authorizations slow down','Payment and checkout latency increase together. Identify the deepest observed slow service.');baseline(s)
deploy(s,170,'fraud','1.9.0','Switched rules lookup to remote feature store.')
for t in [210,240,270]:
    chain(s,t,['gateway','checkout','payments','fraud'],2010,True)
metric(s,220,'fraud','http.server.duration.p95',1900,'ms');metric(s,221,'payments','http.server.duration.p95',1960,'ms');metric(s,222,'checkout','http.server.duration.p95',2050,'ms');log(s,225,'payments','Authorization deadline exceeded while waiting for fraud response.');metric(s,230,'inventory','db.pool.utilization',.30)
scenarios.append(s)
s=scenario('retry-amplification','A burst becomes a sustained overload','Request attempts continue growing after a short payment outage. Inspect retries and original traffic.');baseline(s)
deploy(s,180,'checkout','3.5.0','Retry max attempts increased to 6; backoff disabled.');metric(s,205,'checkout','http.client.retry.rate',480,'attempts/s');metric(s,205,'checkout','http.server.request.rate',80,'requests/s');log(s,207,'checkout','Retry budget exceeded; retry attempt 6 after 503.','warning')
for i,t in enumerate([210,215,220,225]):
    call(s,t,'checkout','payments',450,True,retry=i+2)
call(s,230,'gateway','checkout',2800,True);metric(s,232,'payments','http.server.error.rate',120,'errors/s');metric(s,234,'payments','db.pool.utilization',.32);metric(s,240,'checkout','http.server.duration.p95',2850,'ms')
scenarios.append(s)
s=scenario('config-regression','Orders fail on the new release','A new checkout version starts returning errors while other service checks remain normal.');baseline(s)
deploy(s,180,'checkout','3.6.0','PAYMENTS_ENDPOINT changed to unsupported scheme htttp://payments.');log(s,185,'checkout','Invalid configuration: PAYMENTS_ENDPOINT has invalid endpoint scheme htttp.');metric(s,186,'checkout','config.validation.errors',1,'errors');log(s,190,'checkout','Configuration validation failed before payment client initialization.')
for t in [210,240,270]: call(s,t,'gateway','checkout',35,True)
metric(s,215,'payments','http.server.duration.p95',60,'ms');metric(s,215,'inventory','db.pool.utilization',.23);metric(s,218,'checkout','http.server.error.rate',34,'errors/s')
scenarios.append(s)
s=scenario('healthy-baseline','Steady traffic, no known injected failure','A control recording checks whether the engine invents a specific problem from ordinary activity.');baseline(s)
deploy(s,180,'inventory','2.8.0','Updated documentation metadata.')
for t in [210,240,270]:
    call(s,t,'checkout','inventory',32);call(s,t+1,'checkout','payments',55);call(s,t+2,'gateway','checkout',85)
metric(s,220,'inventory','db.pool.utilization',.35);metric(s,225,'checkout','http.client.retry.rate',.1,'attempts/s');log(s,230,'checkout','Health check passed.','info')
scenarios.append(s)
s=scenario('partial-telemetry','Errors with incomplete telemetry','Only a few application logs are available. The engine should acknowledge the evidence gap.');log(s,210,'checkout','Request failed: operation aborted.');log(s,214,'checkout','Request failed: operation aborted.');log(s,220,'gateway','Upstream returned an error.');scenarios.append(s)
labels={
 'pool-pressure':{'cause':'connection_pool_exhaustion','service':'inventory','kind':'known_injection'},
 'downstream-latency':{'cause':'downstream_latency','service':'fraud','kind':'known_injection'},
 'retry-amplification':{'cause':'retry_storm','service':'checkout','kind':'known_injection'},
 'config-regression':{'cause':'configuration_regression','service':'checkout','kind':'known_injection'},
 'healthy-baseline':{'cause':None,'service':None,'kind':'healthy_control'},
 'partial-telemetry':{'cause':None,'service':None,'kind':'insufficient_evidence'},
}
(ROOT/'scenarios.json').write_text(json.dumps({'synthetic':True,'schema_version':'1.0','scenarios':scenarios},indent=2)+'\n')
(ROOT/'labels.json').write_text(json.dumps({'warning':'Evaluation labels only. Never supplied to analyze().','labels':labels},indent=2)+'\n')
print('Wrote',len(scenarios),'synthetic scenarios with',sum(len(s['events']) for s in scenarios),'events')
