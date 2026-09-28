"""Deterministic incident hypotheses from observable signals only.

No fixture labels, scenario IDs or hidden ground truth enter this module.
Scores combine explicit features; they are NOT probabilities or causal proof.
"""
from __future__ import annotations
from bisect import bisect_left, bisect_right
from collections import defaultdict, deque
import hashlib
import json
import math
from .normalize import canonical, epoch, normalize_payload, timestamp

STRATEGIES = {
    "balanced": {"signal": .55, "temporal": .15, "graph": .20, "keywords": .10},
    "temporal": {"signal": .45, "temporal": .35, "graph": .10, "keywords": .10},
    "graph": {"signal": .45, "temporal": .10, "graph": .35, "keywords": .10},
    "keyword": {"signal": .45, "temporal": .10, "graph": .10, "keywords": .35},
}
ERROR_LEVELS = {"error", "critical"}


class EvidenceIndex:
    """O(N log N) build; service/time lookup O(log n + k), trace lookup O(k)."""
    def __init__(self, events):
        self.by_id = {e["id"]:e for e in events}
        self.by_service = defaultdict(list)
        self.by_trace = defaultdict(list)
        for e in events:
            self.by_service[e["service"]].append(e)
            if e.get("trace_id"): self.by_trace[e["trace_id"]].append(e)
        self.times = {}
        for service,items in self.by_service.items():
            items.sort(key=lambda x:(x["timestamp"],x["id"]))
            self.times[service] = [epoch(e["timestamp"]) for e in items]

    def window(self, service, start, end):
        times = self.times.get(service,[])
        return self.by_service.get(service,[])[bisect_left(times,start):bisect_right(times,end)]

    def trace(self, trace_id):
        return self.by_trace.get(trace_id,[])


def service_graph(events):
    nodes, edges = {}, {}
    span_lookup = {(e.get("trace_id"),e.get("span_id")):e for e in events if e["kind"]=="span" and e.get("span_id")}
    for e in events:
        node = nodes.setdefault(e["service"],{"id":e["service"],"label":e["service"],"event_count":0,"error_count":0})
        node["event_count"] += 1
        node["error_count"] += int(e["severity"] in ERROR_LEVELS)
    observed = set()
    observed_errors = set()
    for e in events:
        if e["kind"]!="span": continue
        source,target = e["service"], e["attributes"].get("peer.service")
        parent = span_lookup.get((e.get("trace_id"),e.get("parent_span_id"))) if e.get("parent_span_id") else None
        if not target and parent and parent["service"]!=e["service"]:
            source,target = parent["service"],e["service"]
        if not isinstance(target,str) or not target or target==source: continue
        nodes.setdefault(target,{"id":target,"label":target,"event_count":0,"error_count":0})
        edge = edges.setdefault((source,target),{"source":source,"target":target,"calls":0,"error_count":0,"max_duration_ms":0,"evidence_ids":[]})
        # Client + server spans from one call share parent relationship. Count once.
        call_id = (source,target,e.get("trace_id"),parent.get("span_id") if parent and e["service"]==target and parent["service"]==source else e.get("span_id",e["id"]))
        if call_id not in observed:
            edge["calls"] += 1
            observed.add(call_id)
        if e["severity"] in ERROR_LEVELS and call_id not in observed_errors:
            edge["error_count"] += 1
            observed_errors.add(call_id)
        edge["max_duration_ms"] = max(edge["max_duration_ms"],e.get("duration_ms",0))
        edge["evidence_ids"].append(e["id"])
    return {"nodes": sorted(nodes.values(),key=lambda x:x["id"]),"edges":sorted(edges.values(),key=lambda x:(x["source"],x["target"]))}


def upstream_services(graph, service):
    reverse = defaultdict(set)
    for edge in graph["edges"]: reverse[edge["target"]].add(edge["source"])
    seen, todo = {service}, deque([service])
    while todo:
        node = todo.popleft()
        for p in sorted(reverse[node]):
            if p not in seen: seen.add(p); todo.append(p)
    return sorted(seen-{service})


def metric_value_ms(event):
    return event.get("value",0) * (1000 if event.get("unit") in {"s","seconds"} else 1)


def _evidence(event, reason):
    return {"event_id":event["id"],"reason":reason}


def _dedup(items):
    return list({e["event_id"]:e for e in items}.values())


def _candidate(cause,service,title,support,contradictions,signal,keywords,checks,missing,ix,graph):
    support = _dedup(support)
    anchor = min(epoch(ix.by_id[x["event_id"]]["timestamp"]) for x in support)
    nearby = ix.window(service,anchor-600,anchor+120)
    deployments = [e for e in nearby if e["kind"]=="deployment" and epoch(e["timestamp"])<=anchor]
    temporal = .35
    if deployments:
        last = deployments[-1]
        elapsed = round(anchor-epoch(last["timestamp"]))
        temporal = max(.40,1-elapsed/900)
        support.append(_evidence(last,f"A deployment on {service} preceded the first supporting signal by {elapsed} seconds; timing alone does not establish causation."))
    upstream = upstream_services(graph,service)
    affected = [s for s in upstream if any(e["severity"] in ERROR_LEVELS for e in ix.window(s,anchor-30,anchor+300))]
    propagation = min(1,.25+.25*len(affected))
    if not affected:
        missing.append("No observed upstream error propagation in the correlation window.")
    missing.append("No intervention or controlled production experiment confirms causality.")
    refs = [x["event_id"] for x in support]
    reasons = " ".join(f"{x['reason']} [{x['event_id']}]" for x in support[:3])
    explanation = f"{title} is a possible explanation for the observed symptoms. {reasons}"
    return {"id":f"{cause}:{service}","cause":cause,"service":service,"title":title,
            "score":0,"score_label":"heuristic score","explanation":explanation,
            "supporting_evidence":support,"contradicting_evidence":_dedup(contradictions),
            "missing_evidence":list(dict.fromkeys(missing)),"diagnostic_checks":checks,
            "factors":{"signal":min(1,signal),"temporal":round(temporal,4),"graph":propagation,"keywords":min(1,keywords)},
            "evidence_ids":refs,"related_services":affected}


def hypotheses_for_service(service,ix,graph):
    events = ix.by_service[service]
    metrics = [e for e in events if e["kind"]=="metric"]
    logs = [e for e in events if e["kind"]=="log"]
    spans = [e for e in events if e["kind"]=="span"]
    results = []
    def text(e): return (e["name"]+" "+e["message"]).lower()
    pool = [e for e in metrics if (e["name"]=="db.pool.utilization" and e["value"]>=.85) or (e["name"]=="db.pool.pending" and e["value"]>=1)]
    pool_logs = [e for e in logs if any(s in text(e) for s in ("pool exhausted","pool timeout","acquire connection timeout","connection pool exhausted"))]
    if pool or pool_logs:
        support = [_evidence(e,f"{e['name']} measured {e['value']:g}{' '+e.get('unit','') if e.get('unit') else ''}.") for e in pool]
        support += [_evidence(e,f"The service logged: {e['message']}") for e in pool_logs]
        first = min(epoch(ix.by_id[e["event_id"]]["timestamp"]) for e in support)
        contra = [_evidence(e,f"Pool utilization was {e['value']:g} during the incident window, which weakens a sustained-exhaustion explanation.") for e in metrics if e["name"]=="db.pool.utilization" and e["value"]<.6 and abs(epoch(e["timestamp"])-first)<=120]
        results.append(_candidate("connection_pool_exhaustion",service,"Connection pool pressure",support,contra,.65+.2*bool(pool)+.15*bool(pool_logs),.9*bool(pool_logs)+.1,
            ["Compare active connections and waiters with the configured pool limit.","Inspect long-running queries and connection release paths.","Compare pool configuration with the preceding deployment."],
            [] if pool and pool_logs else ["Both connection-pool metrics and timeout logs would strengthen this finding."],ix,graph))
    latency_metrics = [e for e in metrics if ("duration" in e["name"] or "latency" in e["name"]) and metric_value_ms(e)>=750]
    slow_spans = [e for e in spans if e.get("duration_ms",0)>=750 and e["attributes"].get("span.kind","server")=="server"]
    if latency_metrics or len(slow_spans)>=2:
        support = [_evidence(e,f"{e['name']} measured {e['value']:g} {e.get('unit','')}.") for e in latency_metrics]
        support += [_evidence(e,f"Server span {e['name']} took {e['duration_ms']:g} ms.") for e in slow_spans[:4]]
        first = min(epoch(ix.by_id[e["event_id"]]["timestamp"]) for e in support)
        contra = [_evidence(e,f"A nearby server span completed in {e['duration_ms']:g} ms; the slowdown was not universal.") for e in spans if e["attributes"].get("span.kind","server")=="server" and e.get("duration_ms",math.inf)<100 and abs(epoch(e["timestamp"])-first)<=120][:3]
        results.append(_candidate("downstream_latency",service,"Elevated service latency",support,contra,.55+.15*bool(latency_metrics)+.15*bool(slow_spans),.25,
            ["Inspect the longest child spans to distinguish local work from downstream waits.","Compare latency against a representative baseline and request volume.","Check external dependencies before attributing the delay to this service."],
            ["The 750 ms threshold is a demo rule, not a service-specific SLO.","Latency may be a symptom of another resource or dependency failure."],ix,graph))
    retries = [e for e in metrics if e["name"] in {"http.client.retry.rate","retry.rate"} and e["value"]>=10]
    retry_spans = [e for e in spans if isinstance(e["attributes"].get("retry.attempt"), (int,float)) and e["attributes"]["retry.attempt"]>=2]
    retry_logs = [e for e in logs if "retry" in text(e) and e["severity"] in {"warning","error","critical"}]
    if retries or len(retry_spans)>=3:
        support = [_evidence(e,f"Retry rate reached {e['value']:g} {e.get('unit','')}.") for e in retries]
        support += [_evidence(e,f"A client span records retry attempt {e['attributes']['retry.attempt']}.") for e in retry_spans[:3]]
        support += [_evidence(e,f"The service logged: {e['message']}") for e in retry_logs[:2]]
        contra = [_evidence(e,f"Recorded retry rate was {e['value']:g}; amplification may be intermittent.") for e in metrics if e["name"] in {"http.client.retry.rate","retry.rate"} and e["value"]<2]
        results.append(_candidate("retry_storm",service,"Retry amplification",support,contra,.7+.15*bool(retries)+.15*bool(retry_spans),.9 if retry_logs else .4,
            ["Compare retry attempts with original request rate and downstream error rate.","Review backoff, retry budgets, and timeout interaction.","Replay bounded traffic in an isolated environment to test the amplification hypothesis."],
            ["Retries may be a consequence of an earlier downstream failure."],ix,graph))
    config_logs = [e for e in logs if any(s in text(e) for s in ("invalid configuration","missing configuration","configuration validation failed","unknown config","invalid endpoint"))]
    config_metrics = [e for e in metrics if e["name"]=="config.validation.errors" and e["value"]>0]
    if config_logs or config_metrics:
        support = [_evidence(e,f"The service logged: {e['message']}") for e in config_logs]
        support += [_evidence(e,f"Configuration validation reported {e['value']:g} errors.") for e in config_metrics]
        contra = [_evidence(e,"A successful configuration validation was also observed; compare instance and version labels.") for e in metrics if e["name"]=="config.validation.errors" and e["value"]==0]
        results.append(_candidate("configuration_regression",service,"Configuration validation failure",support,contra,.7+.15*bool(config_logs)+.15*bool(config_metrics),1 if config_logs else .3,
            ["Compare validated settings between the failing and healthy instances.","Check required environment variables and endpoint schemes.","Verify a corrected configuration in the test environment before proposing a rollout."],
            ["A deployment association needs a configuration diff or version-specific evidence."],ix,graph))
    return results


def analyze(raw_events, strategy="balanced", start=None, end=None):
    if strategy not in STRATEGIES: raise ValueError(f"strategy must be one of {', '.join(STRATEGIES)}")
    if start: start = timestamp(start)
    if end: end = timestamp(end)
    if start and end and start>end: raise ValueError("start must be before or equal to end")
    normalized, errors = normalize_payload(raw_events)
    late_ids = {e["id"] for e in raw_events if isinstance(e,dict) and e.get("late")} if isinstance(raw_events,list) else set()
    events_by_id = {e["id"]:e for e in normalized}
    duplicates = len(normalized)-len(events_by_id)
    events = [dict(e,late=e["id"] in late_ids) for e in events_by_id.values() if (not start or e["timestamp"]>=start) and (not end or e["timestamp"]<=end)]
    events.sort(key=lambda x:(x["timestamp"],x["id"]))
    ix, graph = EvidenceIndex(events),service_graph(events)
    weights = STRATEGIES[strategy]
    hypotheses = [h for service in sorted(ix.by_service) for h in hypotheses_for_service(service,ix,graph)]
    for h in hypotheses:
        penalty = min(.2,len(h["contradicting_evidence"])*.05)
        h["score"] = round(max(0,math.fsum(h["factors"][k]*weights[k] for k in weights)-penalty)*100,1)
    hypotheses.sort(key=lambda x:(-x["score"],x["id"]))
    uncertainties = ["Scores are uncalibrated heuristics. A high score does not establish a root cause.","Missing telemetry can hide alternative explanations."]
    if not any(e["kind"]=="span" for e in events): uncertainties.append("No trace spans were supplied; dependency and propagation evidence is unavailable.")
    if not any(e["kind"]=="metric" for e in events): uncertainties.append("No metric observations were supplied; signal checks rely on logs and spans.")
    if errors: uncertainties.append(f"{len(errors)} invalid/conflicting input records were excluded.")
    if duplicates: uncertainties.append(f"{duplicates} identical duplicate events were collapsed.")
    if late_ids: uncertainties.append("Late arrivals were retained and sorted by event time, not arrival time.")
    if any(abs(e["attributes"].get("clock.skew_ms",0))>1000 for e in events if isinstance(e["attributes"].get("clock.skew_ms",0),(int,float))): uncertainties.append("Reported clock skew exceeds 1 second; timestamp ordering may be misleading.")
    if any(e["severity"] in ERROR_LEVELS for e in events) and not hypotheses: uncertainties.append("Errors are present, but supported diagnostic rules found no specific explanation.")
    summary = f"{len(hypotheses)} evidence-backed hypotheses across {len(ix.by_service)} observed services." if hypotheses else "No supported diagnostic hypothesis in the selected evidence. This does not prove the system is healthy."
    identity = hashlib.sha256((strategy+json.dumps(events,sort_keys=True)+str(start)+str(end)).encode()).hexdigest()[:16]
    result = {"analysis_id":"analysis_"+identity,"strategy":strategy,"window":{"start":start or (events[0]["timestamp"] if events else None),"end":end or (events[-1]["timestamp"] if events else None)},
      "summary":summary,"stats":{"events":len(events),"services":len(ix.by_service),"traces":len(ix.by_trace),"error_events":sum(e["severity"] in ERROR_LEVELS for e in events),"deployments":sum(e["kind"]=="deployment" for e in events),"late_events":sum(e["late"] for e in events)},
      "graph":graph,"timeline":events,"hypotheses":hypotheses,"evidence":ix.by_id,"uncertainties":uncertainties,
      "method":{"version":"rules-v0.1","weights":weights,"complexity":"Index O(N log N); service-time query O(log n + k); each upstream traversal O(V + E).","ground_truth_used":False},"rejected_events":errors}
    validate_analysis(result)
    return result


def validate_analysis(analysis):
    if not isinstance(analysis,dict) or not isinstance(analysis.get("evidence"),dict) or not isinstance(analysis.get("hypotheses"),list) or analysis.get("strategy") not in STRATEGIES:
        raise ValueError("invalid analysis object")
    evidence = analysis["evidence"]
    for h in analysis["hypotheses"]:
        if not isinstance(h,dict): raise ValueError("hypothesis must be an object")
        support = h.get("supporting_evidence",[])
        if not isinstance(support,list) or not support: raise ValueError("hypothesis has no supporting evidence")
        if not isinstance(h.get("contradicting_evidence",[]),list) or not isinstance(h.get("evidence_ids",[]),list):
            raise ValueError("evidence references must be arrays")
        if any(not isinstance(x,dict) for x in support+h.get("contradicting_evidence",[])):
            raise ValueError("evidence references must be objects")
        refs = [x.get("event_id") for x in support + h.get("contradicting_evidence",[])] + h.get("evidence_ids",[])
        if any(not isinstance(ref,str) or ref not in evidence for ref in refs): raise ValueError("analysis references unsupported evidence id")
        if isinstance(h.get("score"),bool) or not isinstance(h.get("score"),(int,float)) or not 0<=h["score"]<=100: raise ValueError("score must be a heuristic between 0 and 100")
    return True
