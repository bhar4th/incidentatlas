import io
import json
import unittest
from unittest.mock import patch
from incidentatlas.llm import explain
from incidentatlas.engine import analyze
from incidentatlas.evaluate import get_scenario
ENV={'INCIDENTATLAS_LLM_URL':'https://example.invalid/chat/completions','INCIDENTATLAS_LLM_MODEL':'test-model','INCIDENTATLAS_LLM_API_KEY':'not-real'}
class LLMTests(unittest.TestCase):
    def setUp(self):self.analysis=analyze(get_scenario('pool-pressure')['events'])
    def response(self,content):return io.BytesIO(json.dumps({'choices':[{'message':{'content':json.dumps(content)}}]}).encode())
    def test_offline_needs_no_key(self):
        with patch.dict('os.environ',{},clear=True):self.assertEqual(explain(self.analysis)['mode'],'deterministic')
    def test_only_existing_hypotheses_can_be_selected(self):
        hid=self.analysis['hypotheses'][1]['id']
        with patch.dict('os.environ',ENV,clear=True),patch('urllib.request.urlopen',return_value=self.response({'hypothesis_ids':[hid]})):
            r=explain(self.analysis)
        self.assertEqual(r['mode'],'llm-selected');self.assertEqual(r['summary'],self.analysis['hypotheses'][1]['explanation'])
    def test_unsupported_model_claim_is_rejected(self):
        with patch.dict('os.environ',ENV,clear=True),patch('urllib.request.urlopen',return_value=self.response({'hypothesis_ids':[self.analysis['hypotheses'][0]['id']],'claim':'Production is fixed'})):
            r=explain(self.analysis)
        self.assertEqual(r['mode'],'deterministic');self.assertNotIn('Production is fixed',r['summary'])
    def test_fabricated_id_is_rejected(self):
        with patch.dict('os.environ',ENV,clear=True),patch('urllib.request.urlopen',return_value=self.response({'hypothesis_ids':['invented']})):
            self.assertEqual(explain(self.analysis)['mode'],'deterministic')
    def test_timeout_falls_back(self):
        with patch.dict('os.environ',ENV,clear=True),patch('urllib.request.urlopen',side_effect=TimeoutError):
            self.assertEqual(explain(self.analysis)['mode'],'deterministic')
    def test_remote_insecure_url_rejected_without_request(self):
        with patch.dict('os.environ',ENV|{'INCIDENTATLAS_LLM_URL':'http://example.invalid'},clear=True),patch('urllib.request.urlopen') as req:
            self.assertEqual(explain(self.analysis)['mode'],'deterministic');req.assert_not_called()
