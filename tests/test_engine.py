import copy
import unittest
from unittest.mock import patch
from incidentatlas.engine import analyze,EvidenceIndex,STRATEGIES,validate_analysis
from incidentatlas.evaluate import evaluate,get_scenario,scenarios
from incidentatlas.normalize import epoch

class EngineTests(unittest.TestCase):
    def test_all_strategies_find_known_injections_and_abstain_controls(self):
        for strategy in STRATEGIES:
            with self.subTest(strategy=strategy):
                r=evaluate(strategy)
                self.assertEqual(r['metrics']['top1_accuracy'],1)
                self.assertEqual(r['metrics']['control_abstention_rate'],1)
                self.assertEqual(r['metrics']['unsupported_evidence_count'],0)
    def test_analysis_does_not_read_ground_truth_or_any_file(self):
        events=get_scenario('pool-pressure')['events']
        with patch('builtins.open',side_effect=AssertionError('analysis attempted file I/O')):
            result=analyze(events)
        self.assertFalse(result['method']['ground_truth_used'])
    def test_metadata_cannot_inject_expected_cause(self):
        events=copy.deepcopy(get_scenario('healthy-baseline')['events'])
        for e in events:e['attributes']['ground_truth']='connection_pool_exhaustion';e['attributes']['expected_service']='inventory'
        self.assertEqual(analyze(events)['hypotheses'],[])
    def test_evidence_ids_resolve_and_explanations_are_qualified(self):
        for s in scenarios():
            r=analyze(s['events'])
            for h in r['hypotheses']:
                self.assertIn('possible explanation',h['explanation'])
                self.assertEqual(h['score_label'],'heuristic score')
                for ref in h['supporting_evidence']+h['contradicting_evidence']:
                    self.assertIn(ref['event_id'],r['evidence'])
                for ref in h['supporting_evidence'][:3]:
                    self.assertIn('['+ref['event_id']+']',h['explanation'])
    def test_unrelated_deployment_is_not_support(self):
        r=analyze(get_scenario('pool-pressure')['events'])
        h=r['hypotheses'][0]
        deploy_services=[r['evidence'][x['event_id']]['service'] for x in h['supporting_evidence'] if r['evidence'][x['event_id']]['kind']=='deployment']
        self.assertEqual(deploy_services,['inventory'])
    def test_duplicates_do_not_amplify_scores(self):
        events=get_scenario('pool-pressure')['events']
        a,b=analyze(events),analyze(events+events)
        self.assertEqual(a['hypotheses'],b['hypotheses']);self.assertEqual(a['stats']['events'],b['stats']['events'])
    def test_event_order_is_irrelevant(self):
        events=get_scenario('pool-pressure')['events']
        self.assertEqual(analyze(events),analyze(list(reversed(events))))
    def test_time_window_excludes_future_information(self):
        result=analyze(get_scenario('pool-pressure')['events'],end='2026-09-26T14:02:00Z')
        self.assertEqual(result['hypotheses'],[])
    def test_partial_logs_produce_uncertainty(self):
        r=analyze(get_scenario('partial-telemetry')['events'])
        self.assertEqual(r['hypotheses'],[])
        self.assertTrue(any('No trace spans' in s for s in r['uncertainties']))
        self.assertTrue(any('Errors are present' in s for s in r['uncertainties']))
    def test_contradictory_evidence_reduces_score(self):
        events=copy.deepcopy(get_scenario('pool-pressure')['events'])
        before=analyze(events)['hypotheses'][0]
        events.append({'id':'counter','timestamp':'2026-09-26T14:03:30Z','service':'inventory','kind':'metric','name':'db.pool.utilization','value':.2})
        after=next(h for h in analyze(events)['hypotheses'] if h['id']==before['id'])
        self.assertLess(after['score'],before['score']);self.assertEqual(after['contradicting_evidence'][0]['event_id'],'counter')
    def test_index_window_matches_scan(self):
        events=get_scenario('pool-pressure')['events'];ix=EvidenceIndex(events)
        start,end=epoch('2026-09-26T14:03:20Z'),epoch('2026-09-26T14:04:00Z')
        actual=ix.window('inventory',start,end)
        expected=[e for e in events if e['service']=='inventory' and start<=epoch(e['timestamp'])<=end]
        self.assertEqual({e['id'] for e in actual},{e['id'] for e in expected})
    def test_unknown_evidence_is_rejected(self):
        r=analyze(get_scenario('pool-pressure')['events']);r['hypotheses'][0]['evidence_ids'].append('invented')
        with self.assertRaisesRegex(ValueError,'unsupported evidence'):validate_analysis(r)
    def test_no_events_is_valid_abstention(self):
        self.assertEqual(analyze([])['hypotheses'],[])
    def test_window_order_is_validated(self):
        with self.assertRaises(ValueError):analyze([],start='2026-09-26T15:00:00Z',end='2026-09-26T14:00:00Z')
    def test_graph_contains_real_span_evidence(self):
        r=analyze(get_scenario('downstream-latency')['events'])
        self.assertTrue(any(e['source']=='payments' and e['target']=='fraud' for e in r['graph']['edges']))
        for edge in r['graph']['edges']:
            for ref in edge['evidence_ids']:self.assertEqual(r['evidence'][ref]['kind'],'span')
    def test_edge_failures_count_calls_not_both_sides_of_span_pair(self):
        r=analyze(get_scenario('pool-pressure')['events'])
        for edge in r['graph']['edges']:
            self.assertLessEqual(edge['error_count'],edge['calls'])
    def test_nested_demo_trace_timing_and_call_deduplication(self):
        r=analyze(get_scenario('downstream-latency')['events'])
        traces={}
        for e in r['timeline']:
            if e['kind']=='span':traces.setdefault(e['trace_id'],[]).append(e)
        nested=[xs for xs in traces.values() if len(xs)==6]
        self.assertEqual(len(nested),3)
        for spans in nested:
            lookup={e['span_id']:e for e in spans}
            for e in spans:
                parent=lookup.get(e.get('parent_span_id'))
                if parent:
                    self.assertGreaterEqual(epoch(e['timestamp']),epoch(parent['timestamp']))
                    self.assertLessEqual(epoch(e['timestamp'])+e['duration_ms']/1000,epoch(parent['timestamp'])+parent['duration_ms']/1000)
        fraud_edge=next(e for e in r['graph']['edges'] if e['source']=='payments' and e['target']=='fraud')
        self.assertEqual(fraud_edge['calls'],3)
        self.assertEqual(fraud_edge['error_count'],3)
