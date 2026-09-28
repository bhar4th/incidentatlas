# Security and operating boundaries

IncidentAtlas v0.1 is a local development and demonstration tool. It has no production authentication, authorization, tenant isolation, or formal security audit. Keep the server bound to loopback; the supplied Compose file publishes its port only on `127.0.0.1`.

## Data handling

Imported source, telemetry, analysis results, cases, or run history may contain confidential data. Local persisted data is not encrypted by the application. Use synthetic examples by default, restrict access to the host, and remove sensitive content before sharing exported reports or patches. Never put API keys in browser source or committed configuration.

## Execution boundary

The shipped analysis works on data and source snapshots. It does not execute imported repository scripts, apply patches to remote repositories, run production diagnostic commands, or modify infrastructure. Future integrations that introduce these actions need explicit permission boundaries and separate review.

## Reporting a concern

Report a security issue privately to the maintainer through the repository's private vulnerability reporting feature if enabled. If no private channel is available, open an issue asking for a private contact without publishing exploit details, credentials, or affected data. Do not claim a disclosure response time before a maintainer has committed to one.

## Dependency and deployment notes

Use the pinned dependency/lockfiles, inspect dependency updates, and keep your runtime patched. Binding to `0.0.0.0` inside Docker is necessary for the mapped port; do not change the host mapping to public exposure without adding and testing an appropriate authenticated deployment boundary. These notes are not a production deployment guide.
