# Architecture

The local application implements stages 01-15 with explicitly experimental models
and limited supported outputs. Python/FastAPI owns data/model/history operations;
React/TypeScript/Vite supplies a loopback dashboard. Free sources and local CPU are
the only runtime requirements beyond the installed software.

## Module boundaries

- data/audit.py discovers source coverage; downloads.py handles immutable caching,
  per-host pacing, retries and checksums; normalize.py/ingest.py validate and publish
  complete season snapshots atomically.
- data/snapshots.py records prospective schedule/roster/availability knowledge with
  observed_at and recorded_at. Unknown historical publication remains unknown.
- data/participation.py audits exact PFR/GSIS identity and conservative snap coverage.
- features/pipeline.py freezes completed prior-game features. Historical weekly
  cutoffs stay fixed; live future games may use now and a current observed roster.
- evaluation/harness.py defines chronological season folds and training-only transforms.
- models/games.py fits/evaluates/promotes CPU game baselines/regularized candidates.
- models/players.py and player_defaults.py provide empirical participation,
  opportunity/production baselines and earlier-fold default selection/inference.
- models/extended.py audits raw row lineage and evaluates team kicking/limited defense.
- models/simulation.py and simulation_io.py own seeded shared environments, football
  accounting, joint samples, summaries, integrity manifests and calibration diagnostics.
- storage/database.py and Alembic migrations own operational SQLite schema.
  storage/forecasts.py owns immutable versions, schedule observations, locks and
  actual revisions. It never backdates a live forecast.
- refresh.py orchestrates explicit ingest/capture/features/frozen inference/predict/
  publish/lock/reconcile steps with OS locks, atomic logs and catch-up schedule gating.
- fantasy.py scores joint samples, persists manual weekly roster versions and assigns
  exact eligible slots under kickoff locks. Unsupported contributions stay excluded.
- paper.py owns Decimal odds, integer minor-credit staking and compensating result
  corrections. It has no real-money or automatic wagering integration.
- api/reads.py opens SQLite read-only and reads immutable snapshots. Typed routes
  expose schedule, forecasts, actuals, evaluation, freshness and local tools.
  security.py protects local writes; trusted-host checks protect request hosts.
- frontend/src separates the app/dashboard, shared request helpers, fantasy and
  paper interfaces. Strict TypeScript and pinned Prettier checks apply.

## Storage authority

Raw blobs/source manifests and normalized versioned Parquet own analytical data.
DuckDB can query it without owning a second operational copy. SQLite owns active
season pointers, ingestion metadata, observation batches, forecast versions/locks,
actual corrections and the paper ledger. History tables reject update/delete via
triggers. Metadata/cache pointers remain mutable by the responsible writer.

Ignored artifacts contain fitted models, selected baseline definitions, immutable
joint samples and evaluation/calibration outputs with hashes and input lineage.
Ignored data/fantasy contains atomic manual-roster heads and content-addressed roster
history. No user roster is inferred from source data. The explicitly named
verification-oct21 roster/account are local test artifacts, not real league/bet history.

## Execution and trust

The CLI is the only ingestion/training/refresh entry point. HTTP requests never
train or download. Read requests do not create databases or run migrations. Local
JSON writes may save rosters/paper state and compute numerical comparisons from
verified samples, but require loopback Host/client, trusted origin, explicit local
header and body-size limits. Model pickle files are trusted local outputs only,
not an accepted download format.

Vite binds 127.0.0.1:5173 and proxies /api to 127.0.0.1:8000; preview uses the same
proxy. Settings reject public bind addresses. Development reload should watch only
src/nfl_prediction, not data/artifacts. API/data/model workers must not compete for
writable DuckDB handles. SQLite writers serialize critical publication/ledger steps.

Each immutable game publishes atomically and locks independently. A failed later
game does not erase earlier versions. A lock never silently reopens; rescheduling
a locked game preserves its record but excludes it from scored/lineup eligibility.
Actual/paper corrections append revisions rather than mutate prior evidence.

Daily/pregame schedules are implemented as an explicit CLI gate and optional manual
Task Scheduler recipe. No task, service, remote, push or hosting exists as a setup
side effect. A future hosted system requires separate auth, backups, job execution,
concurrency, secret management and source-rights review; see decisions.md.
