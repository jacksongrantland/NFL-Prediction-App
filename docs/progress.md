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

Completed October 14, 2026 (America/Chicago); awaiting user review and commit.
Stop here until the user resumes. The dated evidence uses October 15 UTC retrieval
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
