# Roadmap and reviewable PRs

The project targets a working core followed by substantial integration, evaluation, and scale work. The original “70%” request is a planning target, not a measured claim. No historical team size or development duration is asserted.

## Shipped scope

- Bounded JSON/OTLP normalization and duplicate/conflict/late-event handling.
- Service/time indexes, observed dependency graph, and four diagnostic families.
- Evidence-linked explanations, uncertainties, alternative weighting, and controls.
- Local API, browser workspace, saved cases, notes, and report export.
- Separate-label synthetic regression evaluation, query-index benchmark, and browser/Python differential checks.
- Optional model selection restricted to existing hypotheses.

## Planned PR tickets

| Ticket | Proposed owner | Deliverable | Acceptance criteria |
| --- | --- | --- | --- |
| IA-01: Live instrumented demo | Engineer A | Small instrumented application and repeatable fault injection in Docker. | Each fault can start/stop/reset; fresh telemetry is generated; healthy baseline and injected cause recorded separately; no production target accepted. |
| IA-02: Collector integration | Engineer A | Documented OTLP receiver/Collector path with backpressure. | Real exporter interoperability tests; supported signal matrix; batch limits; duplicate retry behavior; unsupported metrics explicitly rejected. |
| IA-03: Independent evaluation set | Engineer B | Unseen incident scenarios with distractors and overlapping symptoms. | Labels excluded from analysis; tuning/test split documented; per-case findings, abstention, and failures published. |
| IA-04: Adaptive signal rules | Shared | Baseline-aware thresholds with versioned rule configuration. | Sparse-baseline abstention; regression tests; fixed rule versus adaptive comparison; explanations expose the baseline and threshold. |
| IA-05: Kubernetes changes | Engineer A | Read-only events/deployments/config metadata ingestion. | Least-privilege manifest; allowlisted namespaces; secret-value exclusion; reconnect/deduplication tests; gaps shown in UI. |
| IA-06: Telemetry storage adapter | Engineer A | ClickHouse-backed event query path with bounded retention. | Query parity with SQLite fixtures; migration/retention tests; raw ingestion and query measurements; documented resource costs. |
| IA-07: Investigation jobs | Engineer B | Cancelable asynchronous analyses with progress and restart recovery. | Source window/strategy bound to each result; bounded queue; cancellation cleanup; meaningful partial-state UI. |
| IA-08: Team review boundary | Engineer B | Authentication, workspace authorization, and audit events. | Cross-workspace denial tests, note attribution, export access checks, and no tokens in telemetry or logs. |
| IA-09: Runbook simulation | Shared | Approval-based diagnostic actions in an isolated environment. | Read-only default; per-action allowlist; human approval tied to exact inputs; cancellation and audit; never presented as production remediation. |
| IA-10: Broader browser/Python parity | Shared | Seeded fuzz and large-input differential tests beyond the existing fixture and boundary checks. | Compare ranking/evidence/uncertainties; timestamp/number edge cases; documented unsupported differences; preserve current parity checks in CI. |

Engineer A/B are suggested ownership roles for future collaboration. Both should review meaningful changes and record actual contributions in PRs.

## Definition of done

A feature includes its working user flow, meaningful failure cases, reproducible evidence, documented limits, and reviewable implementation. A new detector must expose why it fired and what would weaken it. A new integration must distinguish missing data from healthy behavior. A performance claim must include workload, hardware, and raw measurements.
