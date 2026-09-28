# Contributing to IncidentAtlas

Start with a concrete issue from [the roadmap](docs/roadmap.md) or a minimal reproduction. Keep a PR focused on one useful capability or correctness fix. Suggested two-person roles are planning aids; record actual ownership and reviews through your real commits and PRs.

## Local checks

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m unittest discover -s tests -v
python -m incidentatlas evaluate
node browser/test-parity.mjs
npm ci
npm run build:web
```

Use the committed dependency lockfiles and the documented runtimes. A browser bundle is committed for a straightforward demo; regenerate it when changing the interface or browser engine. Do not hand-edit minified output.

## Review expectations

- Explain the problem before describing implementation details.
- Include a reproducible fixture for an incorrect semantic/diagnostic result.
- Exercise the failure boundary, not only the success path.
- Distinguish supported, unknown, and failed behavior.
- Keep engine logic independent of display labels and known fixture answers.
- Measure before making performance claims; include the workload and raw samples.
- Keep documentation and API examples consistent with the implemented behavior.
- Use real contributions and normal commit timestamps; no fabricated project history is needed.

## Branch and commit examples

Use a descriptive branch such as `fix/stale-result-check` or `feat/verification-cancellation`. A commit subject should explain a specific change, for example `fix: reject stale source snapshots` or `feat: add bounded analysis cancellation`. Avoid packaging unrelated behavior into one PR.

## Fixtures and dependencies

Use synthetic or properly authorized, sanitized data. Never commit credentials, private customer data, production logs, or source you do not have permission to share. Explain why a new dependency is necessary and update the lockfile. Preserve bundled dependency license notices.

## Before opening a PR

Run the relevant checks, review the final diff including generated files, and describe any limits. A feature is complete when its advertised flow works and a reviewer can reproduce its meaningful result.
