# Progress

## Prompt 01 — Bootstrap and architecture

Completed October 14, 2026. User committed as `1c24de8`; the user subsequently
authorized Prompt 02. Historical verification details follow.

Created a new local Git repository in `nfl-prediction-app`, separate from the parent
planning file. No commit, remote, push, publication, or scheduled task was created.

Implemented an editable Python package, `nfl` CLI, environment settings with loopback
validation, and a typed FastAPI health endpoint. Created a React/TypeScript/Vite
connection dashboard with loading, failure, retry, and success states. Added Python
lint/format configuration, strict frontend type checks, backend smoke tests,
PowerShell helpers, ignore rules, architecture, contracts, and setup instructions.

### Versions verified

| Tool / primary dependency | Version |
|---|---|
| Git | 2.55.0.windows.3 |
| Python | 3.13.2 |
| uv | 0.13.1 |
| Node.js | 24.14.1 |
| npm | 11.11.0 |
| FastAPI | 0.143.1 |
| Uvicorn | 0.54.0 |
| Pydantic | 2.14.1 |
| pydantic-settings | 2.16.0 |
| Typer | 0.27.3 |
| pytest | 9.1.1 |
| HTTPX | 0.28.1 |
| Ruff | 0.17.0 |
| React / React DOM | 19.3.1 |
| TypeScript | 7.0.2 |
| Vite | 8.3.4 |
| Vite React plugin | 6.1.2 |

Installed stable package-manager releases, not prereleases. Node meets Vite's
reported engine requirement (`^20.19.0 || >=22.12.0`). Python dependencies resolved
and execute on Python 3.13.2. Full transitive versions are recorded in `uv.lock`
and `frontend/package-lock.json`; npm direct versions are exact. Python is currently
restricted to 3.13 to match the verified environment.

### Verification results

Commands run from repository root unless indicated:

- `py -3.13 -m uv sync`: resolved/installed 32 packages and created `uv.lock`.
- Frontend `npm.cmd install --save-exact react react-dom`, then
  `npm.cmd install --save-dev --save-exact typescript vite @vitejs/plugin-react @types/react @types/react-dom @types/node`:
  installed successfully; npm reported zero vulnerabilities.
- `.\.venv\Scripts\ruff.exe check .`: passed.
- `.\.venv\Scripts\ruff.exe format --check .`: all 10 Python files formatted.
- `.\.venv\Scripts\python.exe -m pytest`: 2 passed, no warnings. Tests cover the
  health response contract and rejection of public network binding.
- `.\.venv\Scripts\nfl.exe version`: `0.1.0`.
- `npm.cmd --prefix frontend run build`: strict TypeScript checks and Vite production
  build passed. Added Vite client types after the initial CSS-import type check failed.
- Live process smoke check: launched `nfl serve` and Vite with Node, requested
  `http://127.0.0.1:8000/api/health`, `http://127.0.0.1:5173/`, and
  `http://127.0.0.1:5173/api/health`. All returned HTTP 200; direct and proxied health
  bodies reported `status: ok`. Processes were stopped afterward.

### Limitations and local observations

- PowerShell execution policy blocks `.ps1` helpers. System policy was not changed;
  the README provides equivalent direct commands that were verified.
- Standalone `uv` is not on PATH; use `py -3.13 -m uv`.
- Browser rendering was not visually inspected. The build and real HTTP/proxy path
  were verified; manual UI review remains useful.
- No data coverage, source licensing, prediction quality, or model performance has
  been verified. No data/model/storage dependencies have been installed prematurely.
- No chart library is needed for the connection-only screen. Add one at dashboard stage.

### Next unfinished stage

Prompt 02: audit free NFL data and define actual source contracts and availability
matrix. Probe small real artifacts and document attribution, timestamps, and gaps.

Suggested commit: `chore: bootstrap local NFL prediction app and architecture`

## Prompt 02 — Free source audit and contracts

Completed October 14, 2026 (America/Chicago); user committed as `f6aef9c` and
authorized Prompt 03. The dated evidence uses October 15 UTC retrieval
timestamps, which are still October 14 locally.

### Changes and findings

- Added `nfl audit-sources`: metadata discovery for seven nflverse releases,
  bounded CSV probes for 2020–2026, and one small schedule-file check. It does not
  ingest historical datasets. No new dependencies or lockfile changes were needed.
- Added dated JSON evidence and `docs/data_sources.md`: 49 annual CSV assets
  present, plus schedule coverage for all seven seasons; 48/50 schema probes
  verified. Injury 2025/2026 has no `date_modified`, so those two probes explicitly
  report `schema_gap`. The command intentionally exits 1 when gaps are detected.
- Current injury files do exist and have recent updates. Historical pregame
  publication/revision timing remains unproven; current status presence is not a
  promise of complete injury coverage. Defined prospective snapshots, validated
  manual import fallback, and a no-injury baseline.
- Schedules have no preseason rows. 2026 has 272 scheduled rows and 79 with both
  scores recorded; scores alone do not establish the finalization contract.
- Documented cadence, IDs/crosswalks, raw/normalized schemas, availability rules,
  and dataset attribution/redistribution status. PFR provider terms could not be
  verified (data-use page returned 403); nfldata schedule licensing and specific
  upstream rights remain review items before redistribution.
- Added validated `SourceManifest` and exported JSON Schema. Unknown publication
  and availability times stay null. Prefix checksums cannot claim season coverage.
- Anchored `/data/` and `/artifacts/` ignore rules to repository root so application
  code under `src/nfl_prediction/data/` is tracked and linted. Downloads stay ignored.
- Updated README and architecture. Parent planning document was not modified.

### Verification

- `.\.venv\Scripts\nfl.exe audit-sources --current-season 2026 --output docs/source_audit_2026-10-14.json`:
  final live run completed in about 9 seconds with 48/50 verified and exit 1 for
  the two documented optional injury timestamp gaps. No network/source errors.
  CSV bytes read: 3,210,941 annual-sample bytes plus 2,184,486 schedule bytes.
  Metadata transfers are additional. The 2026 team stats file fit within its probe
  cap, so all 158 rows were checked; other annual data was prefix-sampled only.
- Additional three-row source inspections confirmed canonical versus PFR game IDs
  and GSIS player identifiers. No raw player records were saved in Git.
- `.\.venv\Scripts\ruff.exe check .`: passed.
- `.\.venv\Scripts\ruff.exe format --check .`: passed.
- `.\.venv\Scripts\python.exe -m pytest`: 8 passed. Coverage includes truncated CSV
  tails, prefix checksum scope, ignored HTTP Range limits, metadata-error versus
  missing-asset distinction, timezone-aware manifests, and availability evidence,
  along with the existing API/localhost tests.
- `.\.venv\Scripts\nfl.exe audit-sources --help`: command/options registered.
- Exported `docs/source_manifest.schema.json` from the validated Pydantic model.
- `git diff --check`: passed. No commits, pushes, or publications were performed.

### Remaining limitations / next stage

This completes the source-audit stage, not full ingestion. Most annual probes
examine only the first three rows; no full-season completeness or null-rate claims
are made. Asset URLs/tags are mutable and source versions can be corrected later.
Historical evaluation based on today's corrected stats/rosters must be labeled
approximate where original availability cannot be proven. Preseason remains
unsupported. No prediction metrics exist yet.

Prompt 03 is next: one-season ingestion smoke run, immutable raw downloads,
normalized Parquet, SQLite migrations, DuckDB queries, repeatability and coverage
validation. Continue without requiring optional injury timestamps; retain gaps.

Suggested commit: `docs: audit free NFL sources and define data contracts`

## Prompt 03 — Historical ingestion and storage

Completed October 14, 2026 (America/Chicago). Awaiting user review and commit;
do not proceed to Prompt 04 until the user resumes.

### Changes

- Added direct verified schedule CSV and season/weekly roster, player/team stats,
  and PBP Parquet adapters. Only selected PBP/stat columns enter normalized tables;
  original full downloads remain immutable with SHA-256 lineage.
- Added `nfl ingest` (default six completed seasons plus current season), repeated
  `--season` selection for smoke/subset runs, `--force-refresh`, and `nfl data-counts`.
- Added checksum-verified URL caching, conditional requests for schedules/current
  sources, bounded retries/timeouts, and explicit size limits. New source bytes
  retain prior versions; unchanged source/normalization inputs reuse snapshots.
- Added canonical IDs, original team labels, alias normalization, UTC kickoff
  conversion, game-type preservation, type/count checks, duplicate checks, and
  cross-source game/team/week/result reconciliation. Historical trades retain
  their game-time team. Unknown IDs are never invented.
- Added separate rejection Parquet files for unresolved GSIS IDs. Full-file
  validation discovered blank/missing IDs not visible in the earlier prefix probes.
  Initial smoke attempts correctly failed before any publication; handling was
  refined to preserve and explicitly report these unresolved rows.
- Added normalized Parquet snapshots, full output checksums, null/coverage reports,
  SQLAlchemy-backed SQLite ingestion metadata and Alembic migration 0001, and
  ephemeral DuckDB queries over published Parquet. No duplicated authoritative
  analytical data is stored in SQLite or a persistent DuckDB database.
- Added an OS ingestion lock and all-season publication transaction. Source errors,
  partial downloads, conflicting records or interrupted runs cannot select a
  half-written normalized snapshot. Prepared unpublished data is recoverable.
- Added generated, explicitly synthetic offline fixtures and operations/recovery
  documentation. Real data and local databases remain ignored in Git.

### Real coverage

All seven published seasons have 32 teams in team statistics. Counts below are
from real files, independently checked through DuckDB against published snapshots.

| Season | Completed games | Schedule rows | Player rows | Team rows | PBP rows | Season roster rows | Weekly roster rows |
|---|---:|---:|---:|---:|---:|---:|---:|
| 2020 | 269 | 269 | 17,581 | 538 | 47,705 | 3,067 | 44,124 |
| 2021 | 285 | 285 | 18,947 | 570 | 49,922 | 2,960 | 46,670 |
| 2022 | 284 | 284 | 18,809 | 568 | 49,434 | 3,133 | 46,136 |
| 2023 | 285 | 285 | 18,621 | 570 | 49,665 | 3,089 | 45,650 |
| 2024 | 285 | 285 | 18,961 | 570 | 49,492 | 3,215 | 46,572 |
| 2025 | 285 | 285 | 19,400 | 570 | 48,771 | 3,133 | 46,820 |
| 2026 | 79 | 272 | 5,501 | 158 | 13,842 | 3,040 | 15,307 |

Total: **1,772 completed games**, 117,820 identified-player stat rows and 308,831
PBP rows. The 193 remaining 2026 schedule rows have no recorded result and do not
enter play/stat training data. No scored-but-unfinalized games were found in this
run. Every completed game had a unique END_GAME marker and matching schedule/PBP
scores, including overtime endings with clock remaining. No duplicate records or
schema changes from the audited column baseline were found.

Unresolved-ID rejection counts (not silently dropped or assigned fake identities):

| Season | Season roster | Weekly roster | Player stats |
|---|---:|---:|---:|
| 2020 | 1 | 6 | 21 |
| 2021 | 1 | 26 | 22 |
| 2022 | 1 | 27 | 22 |
| 2023 | 1 | 5 | 22 |
| 2024 | 1 | 7 | 22 |
| 2025 | 4 | 29 | 22 |
| 2026 | 1 | 7 | 5 |

Observed players with multiple historical game teams: 49, 75, 69, 61, 75, 88, and
0 respectively. These are coverage observations, not a validated transaction log.
Per-column missingness, all week/type/team coverage, snapshot fingerprints and
measured run reports are in `docs/ingestion_verification_2026-10-14.json`.

### Verification and measured costs

- `py -3.13 -m uv add pandas pyarrow duckdb sqlalchemy alembic tzdata` resolved
  and installed stable compatible releases and updated uv.lock. Versions: pandas
  3.0.6, PyArrow 26.0.0, DuckDB 1.5.6, SQLAlchemy 2.1.4, Alembic 1.20.0,
  tzdata 2026.5 (IANA timezone support on Windows).
- `.\.venv\Scripts\nfl.exe ingest --season 2025 --current-season 2026`:
  smoke run passed with 285 reconciled games after rejection handling; successful
  cached-source run took 1.070 seconds. This is not a cold-download timing.
- `.\.venv\Scripts\nfl.exe ingest --current-season 2026`: first full expansion
  passed in 26.829 seconds, downloading 120,607,965 bytes in addition to already
  cached 2025 smoke sources. Final validation pass from cached sources took
  7.438 seconds with zero downloaded bytes after completion checks were tightened.
- Repeated identical full command: **1.697 seconds**, zero downloaded bytes,
  30 historical cache hits and 6 HTTP revalidations. All seven snapshot IDs were
  identical and reused; no duplicate normalized snapshot was created.
- `.\.venv\Scripts\nfl.exe data-counts 2025` and `... data-counts 2026`: passed;
  an additional independent verification queried all seven seasons through DuckDB
  and matched every dataset count to its publication summary. Alembic revision 0001.
- Local data storage at final verification: **166,866,570 bytes (~159 MiB)**,
  including raw downloads, retained earlier validation snapshots, reports and
  metadata. This excludes installed dependencies. No versions were deleted to
  reduce the measurement; SQLite sizes may change slightly after checkpoints.
- `.\.venv\Scripts\ruff.exe check .` and `... ruff.exe format --check .`: passed.
- `.\.venv\Scripts\python.exe -m pytest`: **23 passed**. Tests cover complete-run
  publication atomicity, identical reruns, source corrections and old snapshots,
  changed schedules and per-season reuse, missing IDs, aliases, conflicting keys,
  timezone conversion, overtime/finality evidence, checksum corruption, conditional
  requests/force refresh, retries, partial downloads and concurrent-run locking,
  alongside the existing health/audit/manifest tests.
- `git diff --check`: passed. No frontend changes required a new frontend build.
  No commit, push, publication, or scheduled task was performed.

### Limits and next stage

Data ingestion is usable; forecasting is not implemented. Schedule completion is
derived from cross-checked terminal PBP evidence, not a separate authoritative
final-status API. This source omits preseason and does not expose an authoritative
cancellation feed. It must not fabricate missing games or cancellation records.
Current rosters are observations, not proof of historical pregame membership;
corrected historical statistics still cannot prove original publication times.
Source manifests intentionally retain conservative coverage and null historical
availability; normalized coverage validation does not invent that timing.

Optional snaps and injuries are not ingested here. Source redistribution review
items from Prompt 02 remain in force. Incremental refresh is at source/season
level; historical corrected files require explicit `--force-refresh`. Interrupted
staging artifacts can remain unselected for later inspection. Backup is manual.

Prompt 04 is next: prospective pregame schedule/roster/injury snapshots, cutoff-aware
queries, structured availability tracking and the validated manual injury import.

Suggested commit: `feat(data): ingest and validate historical NFL datasets`
