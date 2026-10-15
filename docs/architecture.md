# Architecture

A single local repository contains a Python prediction engine/API and a React,
TypeScript, Vite frontend. Bootstrap, source discovery, and historical ingestion
exist today. No predictions, models, scheduled jobs, fantasy tools, or betting
tools exist yet.

Prompt 04 adds prospective schedule/roster/availability observations and strict
local cutoff queries; see `pregame_snapshots.md` for selection policies.

## Current modules

- `settings.py`: validated environment settings; loopback binding only.
- `cli.py`: version and API startup commands.
- `api/app.py`: typed read-only health endpoint at `/api/health`.
- `data/audit.py`: bounded public-source metadata and sample probes, without ingestion.
- `data/manifests.py`: validated source-lineage and historical-availability contract.
- `data/downloads.py`: immutable full downloads, caching, retry and integrity checks.
- `data/normalize.py`: explicit type/ID/alias mappings and cross-source reconciliation.
- `data/ingest.py`: single-writer orchestration and immutable snapshot preparation.
- `data/snapshots.py`: captures, manual availability validation and as-of reads.
- `features/pipeline.py`: weekly frozen team/player features and source eligibility.
- `evaluation/harness.py`: expanding season folds and training-only preprocessing.
- `storage/database.py` and packaged Alembic migrations: SQLite run/cache/publication metadata.
- `storage/analytics.py`: in-memory DuckDB reads of published Parquet snapshots.
- `frontend/src`: connection dashboard with loading, success, failure, and retry states.
- `scripts`: development and verification commands for PowerShell.

Vite binds to 127.0.0.1:5173 and proxies `/api` to 127.0.0.1:8000. Both dev and
preview use this proxy. The API defaults to 127.0.0.1:8000. There are no mutation
routes or authentication in this stage. Hosting and multi-user access are deferred.
If NFL_PORT changes, update the Vite proxy target to match.

## Storage ownership

- Immutable raw downloads and normalized versioned Parquet own analytical datasets
  and source lineage under ignored `data/` paths.
- DuckDB queries Parquet; it does not own a competing copy of operational entities.
- SQLite owns ingestion metadata, cache/source-manifest references, immutable
  snapshot catalog and active season pointers. Future stages add forecast locks,
  result revisions, user roster entry and the virtual credit ledger.
- Ignored `artifacts/` stores models and evaluation outputs; manifests link artifacts
  to data hashes and dependency versions.
- SQLite append-only observation batches own prospective schedule, roster and
  structured availability history (migration 0002). They preserve observation and
  local recording times; strict queries never backdate imported reports.

API operational reads use SQLite or immutable analytical snapshots. Scheduled
writers must not compete with API requests for writable DuckDB handles. Storage
libraries and migrations arrive only when their stages need them.

## Execution boundaries

The CLI will orchestrate data, feature, model, simulation, and reconciliation modules.
`nfl audit-sources` writes metadata/header evidence; it never populates operational
stores. `nfl ingest` loads verified schedule, season/weekly roster, player/team stat,
and selected PBP sources. It validates complete snapshot directories before one
SQLite transaction publishes every requested season. See operations.md for exact
atomicity, cache/recovery policy and completion evidence. The repository-root `/data/` is
ignored, while `src/nfl_prediction/data/` is tracked application code.

API handlers stay thin and never train models or download large datasets. CPU
execution is the default. Retraining remains an explicit separate operation.
Windows scheduled tasks require explicit user action in a later stage.
