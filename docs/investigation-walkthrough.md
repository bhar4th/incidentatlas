# Investigate pool pressure

## Scenario

`pool-pressure` is a synthetic trace/log/metric/deployment recording. It includes a checkout dependency chain, connection-pool signals, timeout symptoms, and deployment context. The expected cause/service is stored separately in `fixtures/labels.json` for evaluation only.

## Reproduce

```bash
python -m incidentatlas analyze --scenario pool-pressure --strategy balanced --output reports/pool-balanced.json
python -m incidentatlas analyze --scenario pool-pressure --strategy graph --output reports/pool-graph.json
```

Open the reports and inspect `hypotheses`, their feature values, evidence IDs, and uncertainties. Changing a strategy changes weighting; it does not create new observations.

## Review questions

1. Are there both utilization/waiter metrics and timeout observations?
2. Which services show propagated symptoms through observed dependencies?
3. Did a deployment precede the supporting signal, and is a configuration diff available?
4. Are there healthy observations that weaken a sustained-failure explanation?
5. What evidence is missing before someone could call this the root cause?

A useful report answers these questions with event IDs. It does not claim that a nearby deployment caused the failure simply because the timestamps are close.

## Review the interface

Start the local server and open **http://127.0.0.1:8100**. Confirm **Local API connected**. In **Evidence**, select a trace in the request waterfall and click a span to inspect its source record. The span positions are computed from actual recorded timestamps and durations.

Save the investigation, add a note, update review status, and reload the page. The **Cases** view restores the SQLite record and labels its storage source. A browser-only demo instead stores cases in localStorage. Exporting from the interface downloads JSON; the API below supports Markdown as well.

With an optional provider configured, **Review prioritization** requests a choice among existing hypotheses. If no provider is configured, the API returns the deterministic explanation.

## Save a case through the API

```bash
python -m incidentatlas serve --port 8100
```

In a second terminal:

```bash
python scripts/api-demo.py
```

This loads the scenario, ingests it into a local workspace, runs an analysis, creates a case, adds a note, and prints the case/export URL. Repeated ingestion demonstrates duplicate handling. The helper creates a new case each time; its case creation is not an idempotent operation.

## Import telemetry

Use the event shape in `fixtures/scenarios.json` as a starting point. Keep real credentials, personal information, and confidential request bodies out of test fixtures. POST `{ "events": [...] }` to `/api/ingest?workspace=my-demo`; then analyze `{ "workspace": "my-demo", "strategy": "balanced" }` through `/api/analyze`.

A small OTLP JSON example is included:

```bash
python -m incidentatlas analyze --input fixtures/sample-otlp.json
```

The sample produces normalized span/log/metric evidence without requiring a live collector. Browser file import supports normalized events only; the Python CLI/API handles OTLP JSON.

A custom metric name does not automatically gain diagnostic meaning. Add a documented rule and regression fixtures when introducing a new diagnostic signal.

## Controls

Run `python -m incidentatlas evaluate` to inspect all scenarios. Healthy and sparse telemetry controls check abstention for these explicit fixtures. Absence of a hypothesis does not prove health; it can mean the rules lack suitable evidence.
