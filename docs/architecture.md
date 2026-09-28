# Architecture and algorithms

## Event boundary

The normalized event includes `id`, timezone-aware `timestamp`, `service`, `kind`, `severity`, `name`, `message`, and scalar `attributes`. Spans may include trace/span/parent IDs and duration. Metrics require a finite value. Deployment events can carry version and change details.

The normalizer accepts either this explicit event form or a bounded OTLP JSON subset. It converts timestamp units, maps severity, preserves IDs where available, and creates stable IDs from normalized content otherwise. Unsupported metric variants are rejected rather than assigned invented summaries. Histograms with count and sum yield a mean plus observation count; they do not yield a p95.

The event store compares canonical content for duplicate IDs. Identical resubmissions are counted as duplicates, while conflicting content does not overwrite the first stored event. Events more than 30 seconds behind the ingestion high-water mark are flagged late and retained. This is an arrival-quality flag, not event-time watermarking for a distributed stream processor.

## Evidence indexes

`EvidenceIndex` groups events by service and trace. Each service's event list is sorted by `(timestamp, id)`, with a parallel numeric timestamp list. `bisect_left`/`bisect_right` find a service-time interval; the output contains all matching events, not a sampled summary.

| Operation | Cost and qualification |
| --- | --- |
| Build indexes | `O(N log N)` worst-case sort bound, with `O(N)` storage. |
| Service-time lookup | `O(log n + k)` for `n` events in the selected service and `k` returned events. |
| Trace lookup | Expected constant-time key lookup plus `O(k)` to consume the matching events. |
| Build observed graph | Expected `O(N)` dictionary processing plus deterministic output sorting. |
| Traverse upstream graph | `O(V + E)` traversal before sorting presentation results. |

These are component costs. End-to-end analysis also normalizes, sorts, builds candidates, examines evidence, serializes output, and may repeatedly traverse service dependencies. There is no claim that complete investigation is simply `O(log N)` or linear in all cases.

## Observed dependencies

The graph uses `peer.service` where present and cross-service parent/child span relationships otherwise. Client/server observations of a call are deduplicated for the call count. Edges retain evidence IDs. Missing traces can hide dependencies; a graph is an observation of the supplied window, not an authoritative infrastructure inventory.

## Hypotheses

Four diagnostic families produce candidates:

- Connection-pool utilization/pending metrics and pool timeout logs.
- Elevated latency metrics and slow server spans.
- Retry-rate metrics, retry attempts, and retry logs.
- Configuration validation errors and related logs.

Each candidate contains supporting, contradicting, and missing evidence, plus diagnostic checks. Strategies weight four features: direct signal, temporal context, observed upstream propagation, and keywords. Contradicting observations reduce scores. Heuristics are intentionally inspectable; thresholds such as a 750 ms latency trigger are demo rules, not learned service-specific SLOs.

The engine does not consume fixture labels or scenario names. Labels are loaded only by the evaluator. A supported hypothesis is a possible explanation, not a causal finding. No intervention, counterfactual experiment, or learned causal graph is implemented.

## Model boundary

The optional compatible chat-completions request contains up to twelve existing candidate hypotheses and their evidence summaries. It asks the model to return only `hypothesis_ids`. IDs must be unique, valid, and limited to three; no other keys are accepted. Displayed explanations are then looked up from the deterministic engine. Provider-generated prose is not rendered as incident evidence.

A missing configuration, invalid response, or provider failure produces deterministic fallback. This limits the model's ability to invent displayed facts, but does not guarantee the selected existing hypothesis is correct. The request has a ten-second timeout and a bounded response read.

## Persistence and transport

SQLite stores normalized event payloads, analysis snapshots, cases, and notes. Composite indexes cover workspace/service/time and workspace/trace queries. A lock protects the local shared connection, and WAL is enabled. Analysis loads the selected local data into memory.

The standard-library server and optional FastAPI adapter share the same service layer. Both serve the local interface and application routes. The standard-library path allows a no-install core demonstration. The FastAPI adapter is a transport option, not a separate analysis engine.

The browser engine computes interactive investigations and is checked against the Python engine for supported fixtures and input boundaries. The interface connects to the local API for durable case creation, note/status updates, and optional model review. Startup restores saved SQLite cases. Without a server connection, browser-only cases use localStorage. Case labels distinguish the two storage sources, and browser-only records are not automatically imported into SQLite. Neither mode supplies shared-team authorization.

The evidence view groups spans by trace ID and draws a waterfall from each span's recorded start timestamp and duration. Clicking a bar opens the original observation, including parent-span metadata when present. Relative timing helps inspect a request; it does not repair missing spans or clock skew.

## Deliberate v0.1 choices

- **Explicit diagnostic rules** make wrong assumptions inspectable and testable.
- **Separate labels** prevent the inference path from trivially reading the known answer.
- **SQLite** keeps the demo reproducible; production telemetry storage is future work.
- **Qualified explanations** expose gaps instead of presenting confident root causes.
- **Read-only investigation** keeps diagnosis separate from any future remediation execution.
