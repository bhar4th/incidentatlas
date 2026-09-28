import importlib.util
import tempfile
import unittest
from pathlib import Path

HAS_API=importlib.util.find_spec('fastapi') is not None and importlib.util.find_spec('httpx') is not None
@unittest.skipUnless(HAS_API,'optional FastAPI/httpx dependencies not installed')
class APITests(unittest.TestCase):
    def setUp(self):
        from fastapi.testclient import TestClient
        from incidentatlas.api import create_app
        self.tmp=tempfile.TemporaryDirectory();self.client=TestClient(create_app(Path(self.tmp.name)/'db.sqlite3'));self.client.__enter__()
    def tearDown(self):self.client.__exit__(None,None,None);self.tmp.cleanup()
    def test_health_and_scenarios(self):
        self.assertEqual(self.client.get('/api/health').status_code,200)
        self.assertEqual(len(self.client.get('/api/scenarios').json()['scenarios']),6)
    def test_analyze_case_note_and_export_workflow(self):
        r=self.client.post('/api/analyze',json={'scenario_id':'pool-pressure','strategy':'graph'});self.assertEqual(r.status_code,200)
        a=r.json();self.assertEqual(a['hypotheses'][0]['service'],'inventory')
        c=self.client.post('/api/cases',json={'title':'Investigation','analysis':a,'scenario_id':'pool-pressure'});self.assertEqual(c.status_code,200)
        cid=c.json()['id'];r=self.client.patch('/api/cases/'+cid,json={'note':'Investigating pool configuration.','status':'reviewing'})
        self.assertEqual(r.json()['status'],'reviewing');self.assertEqual(len(r.json()['notes']),1)
        report=self.client.get('/api/cases/'+cid+'/export?format=markdown');self.assertEqual(report.status_code,200);self.assertIn('Supporting observations',report.text)
    def test_bad_strategy_is_400(self):
        self.assertEqual(self.client.post('/api/analyze',json={'events':[],'strategy':'imaginary'}).status_code,400)
    def test_invalid_json_is_400(self):
        self.assertEqual(self.client.post('/api/analyze',content='{').status_code,400)
    def test_missing_scenario_is_404(self):
        self.assertEqual(self.client.get('/api/scenarios/missing').status_code,404)
    def test_ingest_and_analyze_saved_workspace(self):
        r=self.client.post('/api/ingest?workspace=test',json={'events':[{'timestamp':'2026-09-26T00:00:00Z','service':'api','kind':'log','message':'Invalid configuration: missing endpoint','severity':'error'}]})
        self.assertEqual(r.json()['accepted'],1)
        self.assertEqual(self.client.post('/api/analyze',json={'workspace':'test'}).json()['hypotheses'][0]['cause'],'configuration_regression')
    def test_payload_size_limit(self):
        r=self.client.post('/api/analyze',content=' '*((5*1024*1024)+1))
        self.assertEqual(r.status_code,413)
    def test_malformed_otlp_and_workspace_are_400(self):
        self.assertEqual(self.client.post('/api/ingest',json={'resourceSpans':[42]}).status_code,400)
        self.assertEqual(self.client.post('/api/analyze',json={'workspace':[]}).status_code,400)
