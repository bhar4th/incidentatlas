# Evaluation and benchmarking

## Diagnostic regression evaluation

```bash
python -m incidentatlas evaluate --strategy balanced --output reports/evaluation-balanced.json
python -m incidentatlas evaluate --strategy temporal --output reports/evaluation-temporal.json
python -m incidentatlas evaluate --strategy graph --output reports/evaluation-graph.json
python -m incidentatlas evaluate --strategy keyword --output reports/evaluation-keyword.json
```

The suite has four known synthetic injected failures and two controls. The same small cases guide rule development. This is useful regression coverage, not held-out model accuracy, production incident recall, or a causal benchmark.

The evaluator reports top-one cause/service matches, top-three recall, control abstention, unsupported evidence references, and local analysis latency. An evidence-reference count of zero means cited IDs exist; it does not validate the reasoning. Mean latency is host-dependent. The shipped `fixtures/evaluation-results.json` records one run.

## Indexed lookup comparison

```bash
python -m incidentatlas benchmark --size 10000 --repeats 20 --output reports/lookup-10k.json
python -m incidentatlas benchmark --size 100000 --repeats 50 --output reports/lookup-100k.json
```

The harness generates synthetic repeated timestamps distributed across 100 services. It compares a full event scan with a service/time-index lookup and asserts equal result IDs. It reports index construction separately from warm lookup medians. `fixtures/benchmark-results.json` is a recorded local run.

The benchmark measures **lookup only**, not ingestion throughput, complete analysis, database query behavior, or user-facing p95. The index uses additional memory and construction time. A speedup applies only when the query workload amortizes those costs. The generator's accepted size is separate from HTTP ingestion limits.

## Improve the measurement

A future benchmark PR should include skewed service traffic, variable time ranges, late arrivals, missing traces, distinct event timestamps, warm/cold storage, memory use, raw samples, and end-to-end latency. Report Python version, CPU, operating system, event distribution, and strategy. Verify equal query outputs before comparing runtime.

A future diagnostic evaluation PR should freeze the current rule version, create unseen cases independently, include distractors and overlapping failures, and publish per-case failures rather than only an average score. Keep labels outside inference inputs and document any tuning on the evaluation set.
