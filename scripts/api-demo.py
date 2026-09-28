"""Exercise the local saved-case workflow without third-party dependencies."""
import json
import os
import urllib.request

BASE = os.environ.get('INCIDENTATLAS_URL', 'http://127.0.0.1:8100').rstrip('/')

def request(path, payload=None, method=None):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(BASE + path, data=data, method=method or ('POST' if data else 'GET'), headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=20) as response:
        return json.load(response)

if __name__ == '__main__':
    scenario = request('/api/scenarios/pool-pressure')
    ingestion = request('/api/ingest?workspace=api-demo', {'events': scenario['events']})
    analysis = request('/api/analyze', {'workspace': 'api-demo', 'strategy': 'balanced'})
    case = request('/api/cases', {'title': 'Pool pressure: local API review', 'scenario_id': scenario['id'], 'analysis': analysis})
    request('/api/cases/' + case['id'], {'status': 'reviewing', 'note': 'Compare the pool metrics with timeout observations before drawing a causal conclusion.'}, 'PATCH')
    print(json.dumps({'ingestion': ingestion, 'case_id': case['id'], 'summary': analysis['summary'], 'leading_hypothesis': analysis['hypotheses'][0]['id'] if analysis['hypotheses'] else None, 'export_url': BASE + '/api/cases/' + case['id'] + '/export?format=markdown'}, indent=2))
