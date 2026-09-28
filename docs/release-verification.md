# Release verification — v0.1.0

Verified on 2026-09-26 in the development workspace.

49 Python tests passed with the optional FastAPI dependencies installed. Browser parity passed for 24 saved fixture results and 120 fresh Python/browser comparisons, plus import validation checks.

## Browser acceptance

- IncidentAtlas unconfigured model returns evidence explanation.
- IncidentAtlas nested trace waterfall and raw evidence drill-down.
- IncidentAtlas SQLite case, status and note persist with cleared browser storage.
- IncidentAtlas runs all four strategies over six regression scenarios.
- IncidentAtlas healthy control abstains.
- IncidentAtlas mobile investigation fits viewport.
- IncidentAtlas mobile evidence fits viewport.
- IncidentAtlas static demo computes traces and saves browser case.
- No uncaught browser errors.

Chromium was exercised at desktop and 390-pixel mobile widths. API-backed histories were restored after clearing localStorage.

## Remaining verification limits

- Real model provider calls were not made; adapter behavior is covered by mocked responses and unconfigured fallbacks.
- Docker and Compose files are included but Docker execution was not available in this environment.
- GitHub Actions workflows are included; no GitHub-hosted CI run is claimed.
- Synthetic fixtures exercise supported behavior; they do not establish production accuracy or throughput.
