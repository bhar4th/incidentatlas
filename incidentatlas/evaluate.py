"""Small synthetic regression suite, not an external/generalization benchmark."""
import json
import time
import sys
import os
from pathlib import Path
from .engine import analyze,STRATEGIES
from .store import now
FIXTURES=Path(os.environ.get('INCIDENTATLAS_FIXTURES', str(Path(__file__).resolve().parent.parent/'fixtures')))
if not FIXTURES.exists():
    FIXTURES=Path(sys.prefix)/'share'/'incidentatlas'/'fixtures'

def scenarios():
    return json.loads((FIXTURES/'scenarios.json').read_text())['scenarios']

def get_scenario(identifier):
    for s in scenarios():
        if s['id']==identifier: return s
    raise KeyError('scenario not found')

def evaluate(strategy='balanced'):
    labels=json.loads((FIXTURES/'labels.json').read_text())['labels']
    rows=[]
    for s in scenarios():
        t=time.perf_counter()
        result=analyze(s['events'],strategy)
        ms=(time.perf_counter()-t)*1000
        expected=labels[s['id']]
        hs=result['hypotheses']
        ranking=next((i+1 for i,h in enumerate(hs) if h['cause']==expected['cause'] and h['service']==expected['service']),None)
        unsupported=sum(ref not in result['evidence'] for h in hs for ref in h['evidence_ids'])
        control_ok=(not hs) if expected['cause'] is None else None
        rows.append({'scenario_id':s['id'],'expected_cause':expected['cause'],'expected_service':expected['service'],
          'predicted_cause':hs[0]['cause'] if hs else None,'predicted_service':hs[0]['service'] if hs else None,
          'rank':ranking,'top1':ranking==1 if expected['cause'] else control_ok,'top3':bool(ranking and ranking<=3) if expected['cause'] else control_ok,
          'kind':expected['kind'],'unsupported_evidence_count':unsupported,'latency_ms':round(ms,3)})
    injected=[r for r in rows if r['kind']=='known_injection']
    controls=[r for r in rows if r['kind']!='known_injection']
    return {'strategy':strategy,'scenarios':rows,'metrics':{'injected_scenarios':len(injected),'control_scenarios':len(controls),
      'top1_accuracy':sum(r['top1'] for r in injected)/len(injected),'top3_recall':sum(r['top3'] for r in injected)/len(injected),
      'control_abstention_rate':sum(r['top1'] for r in controls)/len(controls),'unsupported_evidence_count':sum(r['unsupported_evidence_count'] for r in rows),
      'mean_latency_ms':round(sum(r['latency_ms'] for r in rows)/len(rows),3)},
      'limitations':['Six small synthetic fixtures; four known injected failures and two controls.','These cases also guide rule development; this is regression coverage, not held-out accuracy.','Evidence ID validity does not establish that a hypothesis is causally true.','Wall-clock latency depends on host hardware and current load.']}

def write_demo_results():
    all_results={strategy:{s['id']:analyze(s['events'],strategy) for s in scenarios()} for strategy in STRATEGIES}
    result={'generated_at':now(),'synthetic':True,'strategy':'balanced','results':all_results['balanced'],'strategy_results':all_results,
      'evaluation':evaluate(),'strategy_evaluations':{s:evaluate(s) for s in STRATEGIES}}
    (FIXTURES/'demo-results.json').write_text(json.dumps(result,indent=2)+'\n')
    return result
