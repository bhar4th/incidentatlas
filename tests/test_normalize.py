import copy
import unittest
from incidentatlas.normalize import normalize_event,normalize_payload,epoch

class NormalizationTests(unittest.TestCase):
    def event(self,**kw):
        return {'id':'e1','timestamp':'2026-09-26T10:00:00-05:00','service':'checkout','kind':'log','message':'test',**kw}
    def test_timezone_is_canonical_utc(self):
        self.assertEqual(normalize_event(self.event())['timestamp'],'2026-09-26T15:00:00.000Z')
    def test_stable_content_identity(self):
        e=self.event();del e['id']
        self.assertEqual(normalize_event(e)['id'],normalize_event(dict(reversed(list(e.items()))))['id'])
    def test_invalid_events_are_reported(self):
        good,bad=normalize_payload({'events':[self.event(),self.event(timestamp='invalid'),self.event(kind='metric',value=float('nan'))]})
        self.assertEqual(len(good),1);self.assertEqual(len(bad),2)
    def test_naive_timestamp_rejected(self):
        with self.assertRaises(ValueError):normalize_event(self.event(timestamp='2026-09-26T00:00:00'))
    def test_negative_duration_rejected(self):
        with self.assertRaises(ValueError):normalize_event(self.event(kind='span',duration_ms=-1))
    def test_conflicting_ids_in_payload_do_not_overwrite(self):
        good,bad=normalize_payload([self.event(),self.event(message='changed')])
        self.assertEqual(good[0]['message'],'test');self.assertEqual(len(bad),1)
    def test_otlp_trace_conversion(self):
        raw={'resourceSpans':[{'resource':{'attributes':[{'key':'service.name','value':{'stringValue':'inventory'}}]},'scopeSpans':[{'spans':[{'traceId':'abc','spanId':'def','name':'query','kind':2,'startTimeUnixNano':'1000000000','endTimeUnixNano':'2000000000','status':{'code':2}}]}]}]}
        events,errors=normalize_payload(raw)
        self.assertFalse(errors);self.assertEqual(events[0]['service'],'inventory');self.assertEqual(events[0]['duration_ms'],1000);self.assertEqual(events[0]['severity'],'error')
    def test_otlp_log_conversion(self):
        events,errors=normalize_payload({'resourceLogs':[{'scopeLogs':[{'logRecords':[{'timeUnixNano':'1000000000','severityNumber':17,'body':{'stringValue':'failure'}}]}]}]})
        self.assertFalse(errors);self.assertEqual(events[0]['message'],'failure');self.assertEqual(events[0]['severity'],'error')
    def test_otlp_metric_histogram_is_mean_not_percentile(self):
        events,errors=normalize_payload({'resourceMetrics':[{'scopeMetrics':[{'metrics':[{'name':'duration','unit':'ms','histogram':{'dataPoints':[{'timeUnixNano':'1000000000','count':'2','sum':30}]}}]}]}]})
        self.assertFalse(errors);self.assertEqual(events[0]['name'],'duration.mean');self.assertEqual(events[0]['value'],15)
    def test_unsupported_metric_explicit_error(self):
        good,bad=normalize_payload({'resourceMetrics':[{'scopeMetrics':[{'metrics':[{'name':'latency','exponentialHistogram':{}}]}]}]})
        self.assertEqual(good,[]);self.assertEqual(len(bad),1)
    def test_malformed_otlp_structure_has_validation_error(self):
        with self.assertRaisesRegex(ValueError,'malformed OTLP'):
            normalize_payload({'resourceSpans':[42]})
