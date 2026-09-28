"""Transport-independent application service, used by FastAPI and stdlib HTTP."""
import json
from urllib.parse import parse_qs,urlparse
from .engine import analyze
from .evaluate import evaluate,get_scenario,scenarios
from .llm import explain
from .store import Store


def report_markdown(case):
    a=case['analysis']
    lines=[f"# {case['title']}",'',f"Case: {case['id']} · Status: {case['status']}",f"Created: {case['created_at']}",'',a['summary'],'',f"Strategy: {a['strategy']}. Scores are heuristics, not probabilities.",'','## Hypotheses']
    for h in a['hypotheses']:
        lines += ['',f"### {h['title']} — {h['service']} ({h['score']}/100)",'',h['explanation'],'','Supporting observations:']
        lines += [f"- [{e['event_id']}] {e['reason']}" for e in h['supporting_evidence']]
        lines += ['','Contradicting observations:']+[f"- [{e['event_id']}] {e['reason']}" for e in h['contradicting_evidence']]
        lines += ['','Missing evidence:']+['- '+x for x in h['missing_evidence']]
        lines += ['','Suggested diagnostic checks:']+['- '+x for x in h['diagnostic_checks']]
    lines += ['','## Limitations']+['- '+x for x in a['uncertainties']]
    lines += ['','## Notes']+[f"- {n['created_at']}: {n['body']}" for n in case['notes']]
    lines += ['','## Evidence record','', '```json',json.dumps(a['evidence'],indent=2),'```','']
    return '\n'.join(lines)


class Service:
    def __init__(self, db_path='.incidentatlas/state.sqlite3'):
        self.store=Store(db_path)

    def dispatch(self,method,url,body=None):
        parsed=urlparse(url); path=parsed.path.rstrip('/') or '/'; query=parse_qs(parsed.query)
        payload=body if body is not None else {}
        if method in {'POST','PATCH'} and not isinstance(payload,dict):
            raise ValueError('JSON body must be an object')
        if path=='/api/health' and method=='GET':
            return {'status':'ok','version':'0.1.0','storage':'sqlite','mode':'local','authentication':False}
        if path=='/api/scenarios' and method=='GET':
            return {'synthetic':True,'scenarios':[{k:v for k,v in s.items() if k!='events'}|{'event_count':len(s['events'])} for s in scenarios()]}
        if path.startswith('/api/scenarios/') and method=='GET': return get_scenario(path.split('/')[-1])
        if path=='/api/ingest' and method=='POST': return self.store.ingest(payload,query.get('workspace',['demo'])[0])
        if path=='/api/events' and method=='GET': return {'events':self.store.events(query.get('workspace',['demo'])[0])}
        if path=='/api/analyze' and method=='POST':
            if payload.get('scenario_id'):
                events=get_scenario(payload['scenario_id'])['events']
            elif 'events' in payload:
                if not isinstance(payload['events'],list): raise ValueError('events must be an array')
                events=payload['events']
            else: events=self.store.events(payload.get('workspace','demo'))
            return analyze(events,payload.get('strategy','balanced'),payload.get('start'),payload.get('end'))
        if path=='/api/evaluate' and method=='POST': return evaluate(payload.get('strategy','balanced'))
        if path=='/api/explain' and method=='POST': return explain(payload.get('analysis'))
        if path=='/api/cases' and method=='GET': return {'cases':self.store.cases()}
        if path=='/api/cases' and method=='POST': return self.store.create_case(payload.get('title'),payload.get('analysis'),payload.get('scenario_id'))
        parts=path.split('/')
        if len(parts)>=4 and parts[1:3]==['api','cases']:
            identifier=parts[3]
            if len(parts)==5 and parts[4]=='export' and method=='GET':
                case=self.store.case(identifier)
                fmt=query.get('format',['json'])[0]
                if fmt not in {'json','markdown'}: raise ValueError('format must be json or markdown')
                return report_markdown(case) if fmt=='markdown' else case
            if len(parts)==4:
                if method=='GET': return self.store.case(identifier)
                if method=='PATCH': return self.store.update_case(identifier,payload.get('status'),payload.get('note'))
        raise KeyError('route not found')
