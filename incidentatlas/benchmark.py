"""Indexed time-window lookup versus full scan on equivalent synthetic events."""
import statistics
import time
from .engine import EvidenceIndex
from .normalize import epoch
from .evaluate import get_scenario


def benchmark(size=10000,repeats=20):
    if not 100<=size<=1_000_000: raise ValueError('size must be between 100 and 1000000')
    if not 1<=repeats<=1000: raise ValueError('repeats must be between 1 and 1000')
    base=get_scenario('pool-pressure')['events']
    events=[]
    for i in range(size):
        event=dict(base[i%len(base)]);event['id']=f'bench-{i}'
        event['service']=f"service-{i%100}"
        events.append(event)
    start=time.perf_counter();ix=EvidenceIndex(events);build=(time.perf_counter()-start)*1000
    start_time=epoch(base[0]['timestamp'])+200;end_time=start_time+30
    scanned,indexed=[],[]
    for _ in range(repeats):
        t=time.perf_counter();expected=[e for e in events if e['service']=='service-17' and start_time<=epoch(e['timestamp'])<=end_time];scanned.append((time.perf_counter()-t)*1000)
        t=time.perf_counter();actual=ix.window('service-17',start_time,end_time);indexed.append((time.perf_counter()-t)*1000)
        assert {e['id'] for e in expected}=={e['id'] for e in actual}
    return {'events':size,'services':100,'repeats':repeats,'matching_events':len(actual),'index_build_ms':round(build,3),
       'full_scan_median_ms':round(statistics.median(scanned),6),'indexed_query_median_ms':round(statistics.median(indexed),6),
       'results_equal':True,'limitations':['Synthetic repeated timestamps and evenly assigned services.','Index build and memory costs are separate from warm query time.','This benchmark covers lookup only, not total investigation latency.']}
