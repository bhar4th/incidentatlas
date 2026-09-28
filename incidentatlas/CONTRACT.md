# IncidentAtlas v0.1 API/data contract

Fixture bundles in `fixtures/scenarios.json` are `{scenarios: [{id,title,description,started_at,ended_at,events:[Event]}]}`. Truth is **only** in `fixtures/labels.json`, read only by the evaluator. Analysis never reads labels. `fixtures/demo-results.json` contains actual generated `{generated_at, strategy, results: {scenarioId: Analysis}, evaluation: Evaluation}`.

Event: `{id,timestamp,service,kind,severity,name,message,attributes,trace_id?,span_id?,parent_span_id?,duration_ms?,value?,unit?}`. ISO UTC timestamps; kind is `log|span|metric|deployment`; severity `debug|info|warning|error|critical`; attrs scalar JSON. Metrics have `name,value,unit`; spans have `name,duration_ms` and attributes optionally `span.kind` (`server|client`) and `peer.service`; deployment attrs may include `version`, `change`, `component`. Input normalization also accepts supported OTLP JSON resourceSpans, resourceLogs, resourceMetrics.

`analyze(events, strategy='balanced', start=None, end=None)` returns:
```
{
  analysis_id, strategy, window:{start,end}, summary,
  stats:{events,services,traces,error_events,deployments,late_events},
  graph:{nodes:[{id,label,event_count,error_count}],edges:[{source,target,calls,error_count,max_duration_ms,evidence_ids:[]}]},
  timeline:[{id,timestamp,service,kind,severity,name,message,...}],
  hypotheses:[{
    id,cause,service,title,score,score_label:'heuristic score',
    explanation,supporting_evidence:[{event_id,reason}],
    contradicting_evidence:[{event_id,reason}],
    missing_evidence:[],diagnostic_checks:[],
    factors:{signal,temporal,graph,keywords},
    evidence_ids:[],related_services:[]
  }],
  evidence:{eventId:Event}, uncertainties:[],
  method:{version,weights:{signal,temporal,graph,keywords},complexity,ground_truth_used:false}
}
```
Cause identifiers: `connection_pool_exhaustion`, `downstream_latency`, `retry_storm`, `configuration_regression`. Healthy/no substantial evidence has zero hypotheses; incomplete data explicitly produces uncertainty. Strategies `balanced`, `temporal`, `graph`, `keyword` alter **heuristic ranking**, not probability. All causal explanations are qualified and tied to IDs. Each fixture has at most 60 events for demo clarity.

HTTP root serves `web/`. JSON routes (stdlib server and FastAPI):
- `GET /api/health`
- `GET /api/scenarios` → `{scenarios:[{id,title,description,started_at,ended_at,event_count}]}`
- `GET /api/scenarios/{id}` → scenario including normalized events
- `POST /api/ingest` `{events:[...]}` or OTLP JSON; optional `workspace` query, default `demo`; returns `accepted,duplicates,conflicts,invalid,late,errors`.
- `POST /api/analyze` `{scenario_id? ,events?,workspace?,strategy?,start?,end?}` → Analysis; if neither scenario nor events, load workspace from SQLite.
- `POST /api/evaluate` `{strategy?}` → `{strategy,scenarios:[{scenario_id,expected_cause,expected_service,predicted_cause,predicted_service,rank,top1,top3,unsupported_evidence_count,latency_ms}],metrics:{...}}` (evaluation alone loads labels).
- `GET /api/cases` → `{cases:[{id,title,created_at,updated_at,status,scenario_id,strategy,note_count}]}`
- `POST /api/cases` `{title,analysis,scenario_id?}` → case incl persisted analysis. Analysis evidence IDs validated.
- `GET /api/cases/{id}` → case `{id,title,...,analysis,notes:[]}`
- `PATCH /api/cases/{id}` `{status?:'open'|'reviewing'|'resolved',note?:string}` → case.
- `GET /api/cases/{id}/export?format=json|markdown` → complete report.
- `POST /api/explain` `{analysis}` → optional verified LLM summary if environment configured; offline returns supported deterministic summary and mode `deterministic`.
- `GET /api/events?workspace=demo` → normalized saved events.

Errors: JSON `{error:message}` with 400 validation / 404 missing resource / 409 conflict / 413 oversized body. Body limit 5 MiB. Workspace/case data is local; server binds localhost by default and has no production auth. No tools execute against production systems.
