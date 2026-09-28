import tempfile
import unittest
from pathlib import Path
from incidentatlas.store import Store
from incidentatlas.engine import analyze
from incidentatlas.evaluate import get_scenario
from incidentatlas.service import Service

class StoreTests(unittest.TestCase):
    def setUp(self):self.tmp=tempfile.TemporaryDirectory();self.path=Path(self.tmp.name)/'db.sqlite3';self.store=Store(self.path)
    def tearDown(self):self.store.close();self.tmp.cleanup()
    def ev(self,**kw):return {'id':'a','timestamp':'2026-09-26T14:00:00Z','service':'checkout','kind':'log','message':'okay',**kw}
    def test_idempotence_and_conflict(self):
        self.assertEqual(self.store.ingest([self.ev()])['accepted'],1)
        self.assertEqual(self.store.ingest([self.ev()])['duplicates'],1)
        self.assertEqual(self.store.ingest([self.ev(message='changed')])['conflicts'],1)
        self.assertEqual(self.store.events()[0]['message'],'okay')
    def test_late_event_retained_and_sorted(self):
        self.store.ingest([self.ev(timestamp='2026-09-26T14:05:00Z')])
        result=self.store.ingest([self.ev(id='earlier')])
        self.assertEqual(result['late'],1);self.assertEqual(self.store.events()[0]['id'],'earlier');self.assertTrue(self.store.events()[0]['late'])
        self.assertEqual(analyze(self.store.events())['stats']['late_events'],1)
    def test_workspace_isolation(self):
        self.store.ingest([self.ev()],'one');self.store.ingest([self.ev(message='other')],'two')
        self.assertEqual(self.store.events('one')[0]['message'],'okay');self.assertEqual(self.store.events('two')[0]['message'],'other')
    def test_case_persists_reopen_and_notes(self):
        case=self.store.create_case('Review pool pressure',analyze(get_scenario('pool-pressure')['events']),'pool-pressure')
        self.store.update_case(case['id'],'reviewing','Compare old and new pool limits.')
        self.store.close();self.store=Store(self.path)
        saved=self.store.case(case['id'])
        self.assertEqual(saved['status'],'reviewing');self.assertEqual(len(saved['notes']),1);self.assertEqual(saved['analysis'],case['analysis'])
    def test_invalid_case_status_rejected(self):
        with self.assertRaises(ValueError):self.store.update_case('missing','deleted')
    def test_invalid_ingest_does_not_drop_valid_records(self):
        result=self.store.ingest([self.ev(),{'id':'bad'}]);self.assertEqual(result['accepted'],1);self.assertEqual(result['invalid'],1)
    def test_markdown_export_contains_evidence(self):
        from incidentatlas.service import report_markdown
        case=self.store.create_case('Review',analyze(get_scenario('pool-pressure')['events']))
        report=report_markdown(case)
        self.assertIn('Scores are heuristics',report);self.assertIn(case['analysis']['hypotheses'][0]['evidence_ids'][0],report)
