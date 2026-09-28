# IncidentAtlas browser replay engine

Dependency-free, synchronous JavaScript port of the Python `rules-v0.1` analyzer.
It runs the same deterministic investigation rules on the supplied telemetry.
It never imports fixture labels, consumes precomputed findings, calls a model,
or makes a network request.

```js
import {analyze, parseImport} from './engine.mjs';

const events = parseImport(await file.text());
const result = analyze(events, {
  strategy: 'balanced', // balanced | temporal | graph | keyword
  start: null,         // optional timezone-bearing ISO timestamp
  end: null,
});

// Telemetry-loss experiments recompute everything from the remaining evidence.
const withoutTraces = analyze(events.filter(event => event.kind !== 'span'));
```

`analyze` returns the contract in `incidentatlas/CONTRACT.md`: scored hypotheses,
supporting and contradicting evidence, graph, timeline, uncertainty, statistics,
and rejected records. Scores are uncalibrated heuristics, not probabilities.

Browser import supports **normalized JSON only**, either an events array or
`{"events": [...]}`. `parseImport` enforces a 5 MiB UTF-8 limit and 100,000 event
limit. Read the original file size before `file.text()` too, to avoid allocating
very large files. Use the Python ingestion API for the supported OTLP subset.
The browser engine does not implement persistence or live ingestion.

Event-time windows are inclusive. Duplicate IDs with identical normalized
content collapse; conflicting content is rejected and reported. Missing
telemetry reduces available evidence and can remove diagnostic findings.

## Verify parity

From the project root:

```sh
node browser/test-parity.mjs
```

This compares every field of all 6 bundled scenarios under all 4 strategies
against `fixtures/demo-results.json`, and additionally checks live Python
results for missing spans, logs-only input, restricted time windows, duplicate
and invalid rows, and empty input. Python 3 and Node 18+ are required for this
test; the engine itself needs only a modern browser.

Python and JavaScript use different numeric type and date parsers. Bundled
normalized scenarios are parity-tested in full. Inputs should use ordinary
ISO 8601 timestamps and numeric scalar fields. Browser import intentionally
does not promise byte-identical identities for every exotic float spelling
or Python-only accepted timestamp format.
