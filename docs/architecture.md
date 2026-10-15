# Architecture

A single local repository contains a Python prediction engine/API and a React,
TypeScript, Vite frontend. Only the bootstrap stage exists today. No predictions,
data adapters, models, scheduled jobs, fantasy tools, or betting tools exist yet.

## Current modules

- `settings.py`: validated environment settings; loopback binding only.
- `cli.py`: version and API startup commands.
- `api/app.py`: typed read-only health endpoint at `/api/health`.
- `frontend/src`: connection dashboard with loading, success, failure, and retry states.
- `scripts`: development and verification commands for PowerShell.

Vite binds to 127.0.0.1:5173 and proxies `/api` to 127.0.0.1:8000. Both dev and
preview use this proxy. The API defaults to 127.0.0.1:8000. There are no mutation
routes or authentication in this stage. Hosting and multi-user access are deferred.
If NFL_PORT changes, update the Vite proxy target to match.

## Planned storage ownership

- Immutable raw downloads and normalized versioned Parquet own analytical datasets
  and source lineage under ignored `data/` paths.
- DuckDB queries Parquet; it does not own a competing copy of operational entities.
- SQLite will own ingestion metadata, snapshot references, forecast versions/locks,
  result revisions, rosters entered by the user, and the virtual credit ledger.
- Ignored `artifacts/` stores models and evaluation outputs; manifests link artifacts
  to data hashes and dependency versions.

API operational reads use SQLite or immutable analytical snapshots. Scheduled
writers must not compete with API requests for writable DuckDB handles. Storage
libraries and migrations arrive only when their stages need them.

## Execution boundaries

The CLI will orchestrate data, feature, model, simulation, and reconciliation modules.
API handlers stay thin and never train models or download large datasets. CPU
execution is the default. Retraining remains an explicit separate operation.
Windows scheduled tasks require explicit user action in a later stage.
