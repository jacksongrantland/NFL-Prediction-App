# Progress

Current checkpoint: prompts 01-15 implemented locally as of October 21, 2026.
The dated historical checkpoints below are retained; later completion entries
supersede their earlier in-progress status. Models remain experimental, and
unsupported roles/preseason remain explicit. Existing origin configuration is
preserved; no push, purchase, deployment or scheduled-task installation was made.

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

## Prompt 03 audit fixes and Prompt 04 — Pregame observations

Completed October 15, 2026 (America/Chicago), following explicit user authorization
to fix the audit findings and proceed to Prompt 04. No commit, push, publication
or scheduled task was created. Prompt 05 has not started.

### Audit fixes

- Required schedule teams and game/stat/PBP context now reject nulls. Nullable
  comparisons fail closed during reconciliation rather than silently skipping
  unknown week/type/opponent values. Nullable roster week/type remain permitted.
- Truncated Content-Length transfers and HTTP IncompleteRead use bounded retries;
  exhausted attempts preserve the previous cache and remove temporary partials.
- Default ingestion explicitly reports skipped current seasons before their games
  start or when their schedule is not available, without fetching nonexistent
  annual stats. Historical seasons can still publish together. Skipped seasons
  never replace active pointers. Missing historical sources or started-season
  failures still fail atomically. Future schedules with TBD times can be recognized
  as unstarted using future source dates.

### Prompt 04 implementation

- Added `capture-pregame`, `import-availability` and `pregame-as-of` CLI commands.
  Direct audited schedule/roster/injury adapters preserve raw bytes, hashes,
  source manifests and observation versions. Capture needs no historical stats.
- SQLite migration 0002 adds append-only prospective observation batches with
  observed_at and local recorded_at. Triggers prevent update/delete. Required
  schedule/roster observations publish atomically; injury-only failures publish
  an explicit unavailable status while preserving useful independent progress.
- Separate injury designation, practice participation, roster status and inactivity
  fields. Injury designation never implies inactivity or a playing probability.
  Roster observations remain distinct from active lists and injury observations.
- Added a header-only CSV template and validated manual fallback. It checks
  timestamps, GSIS syntax, schedule/team membership, source URLs, explicit boolean
  inactivity, duplicates and malformed CSV. Invalid rows reject the entire import.
  Valid original CSV bytes are retained immutably by checksum.
- Strict queries require both observation and local recording by cutoff. Old
  manual reports imported today cannot rewrite yesterday's snapshot. Historical
  injury date_modified is metadata, not proof of original publication. Missing,
  stale, disabled, unavailable and unknown remain visible; the no_injury_data label
  permits a future no-injury baseline without claiming a trained model exists.
- Added snapshot policies/commands in docs/pregame_snapshots.md and updated README,
  architecture, contracts and operations. The parent planning file was untouched.

### Verification

- `.\.venv\Scripts\python.exe -m pytest`: **47 passed**, including the audit
  regressions, snapshot revisions, late/manual report leakage, unknown/stale fields,
  independent availability statuses, timezone offsets, immutable rows, optional
  source failures, required-source atomicity and invalid multirow import atomicity.
- `.\.venv\Scripts\ruff.exe check .` and `... ruff.exe format --check .`: passed.
- `npm.cmd --prefix frontend run build`: TypeScript and Vite build passed.
- `.\.venv\Scripts\nfl.exe capture-pregame --season 2026`: live free-source run
  passed (final run about 4.2 seconds): 272 schedule rows, 3,042 roster rows,
  1 quarantined unresolved roster ID, 1,697 injury rows and zero rejected injury
  mappings. Network verification used approved external network access after the
  sandbox denied sockets. No paid source was used.
- Real `pregame-as-of` CLI workflow for 2026_06_ARI_LA returned 188 roster/availability
  entries, 14 observed injury entries, and unknown for unreported players.
  An October 14 UTC cutoff correctly returned missing schedule data. Publication
  time and full injury coverage remain unknown. Small non-player evidence report:
  docs/pregame_verification_2026-10-15.json. Alembic revision 0002 verified.
- `git diff --check`: passed. Real data stays ignored; fixtures are synthetic and
  never enter the user's real observation store. No frontend behavior changed.

### Limitations and next stage

Recent local observation is not proof of recent source publication or complete
injury coverage. Free-feed publication timestamps remain null. Status text is
preserved without a trained interpretation. Manual sources are user assertions,
not independently authenticated reports; IDs are syntax-checked, not proof of
membership. Roster observations are not verified active lists or depth charts.
Today's corrected historical stats/rosters cannot establish original pregame
versions; historical evaluations must remain approximate where timing is unproven.

As-of reads currently load eligible season batches into memory; this is suitable
for initial local use but should be profiled/indexed further if daily history grows
large. No prediction, injury probability model, dashboard data view, or automatic
refresh schedule exists yet. Prompt 05 is next: cutoff-aware features and
chronological evaluation. Stop here pending user review; do not start Prompt 05.

Suggested commit: `feat(data): add pregame observation history and harden ingestion`

## Prompt 05 — Cutoff-aware features and chronological evaluation

Completed October 15, 2026 (America/Chicago). The user authorized working through
the remaining prompts and making a local commit after each completed checkpoint.
AGENTS.md records that override; remote publication remains prohibited.

Added versioned config/features.json, weekly frozen team scoring/conceding/rest
features, lagged QB/RB/WR/TE workload/production, prior-position shrinkage,
historical weekly roster membership, trade context, opponent/home-away inputs,
and explicit availability/role uncertainty. Available injury inputs require local
observation and recording by cutoff and retain batch/timestamp references.
No model was fitted or final-test metric inspected for this checkpoint.

Complete season/week groups share their earliest kickoff as cutoff. Only final
reconciled games with kickoff + 12 hours before cutoff contribute. This is an
explicit approximation because observed game-end timestamps and original source
publication histories are unavailable. Future outcomes cannot affect earlier
features. No career history is invented for rookies or missing identities.

Added expanding earlier-season training/validation manifests, latest eligible
completed season 2025 reserved as final test, all current-season rows excluded
from tuning/test, and training-only imputation/scaling checks. Player rows inherit
their complete game's partition. Artifacts contain source snapshots, definitions,
checksums, code identity, eligibility counts and split manifests. They remain ignored.

Verification from repository root:

- `nfl build-features --output artifacts/features-verified`: 51.829 seconds,
  1,965 game rows and 89,897 player rows from 2020–2026. Feature ID
  b25b87e6f7fa843952b65ef3d67e2589a727a6a83c339e4522b5858114ceed39.
- `nfl build-features --smoke --output artifacts/features-smoke-verified`:
  22.840 seconds, 1,127 game rows and 47,315 player rows from 2023–2026.
  Early development runs took 295–643 seconds; vectorized player stats and indexed
  historical roster lookups reduced the final implementation's measured runtime.
  Some development benchmarks overlapped; these are local observations, not limits.
- `nfl check-backtest artifacts/features-verified/b25b87e6f7fa843952b65ef3d67e2589a727a6a83c339e4522b5858114ceed39`:
  passed in 0.149 seconds, validation seasons 2021–2024 (285/284/285/285 games),
  final 2025 test untouched. Smoke harness also passed (2024 validation).
- `.\.venv\Scripts\python.exe -m pytest --ignore=tests/test_game_models.py`:
  51 passed (16.32 seconds), including future-outcome invariance, shifted features,
  historical trades, finality exclusions and training-only preprocessing. The
  explicitly ignored test file is independent Prompt 06 work, not part of this commit.
- Ruff lint and formatting checks passed; git diff --check passed.
- Installed/locked scikit-learn 1.9.1 with compatible CPU dependencies through uv.
  Package installation required approved access to the system Python/network.

All historical rows remain approximate corrected-source inputs; strict historical
row count is zero. No locally eligible injury batches matched these historical
weekly player features. Missing injury context remains unknown. Weekly rosters
are not verified active lists. The first available season has cold-start priors;
out-of-sample feature availability is not proof of prediction quality.

Prompt 06 is next: baseline comparisons, versioned game models and a single final
2025 evaluation after selection. No push, publication or scheduled task occurred.

Commit: `feat(ml): add cutoff-aware features and chronological evaluation`

## Prompt 06 — Evaluated versioned game models

Completed October 15, 2026 (America/Chicago), after Prompt 05 local commit de7d4df.

Added league/home-field and rolling-strength baselines, regularized logistic/ridge
models, and a bounded CPU histogram-boosting challenger. Fixed parameters/seed,
training-fold-only preprocessing, complete-season validation, and predeclared
log-loss selection (simplest within 0.005 of the best) avoid test-driven tuning.
Ties are a third outcome; playoff tie probability is zero. Rare regular-season
tie probability is a documented smoothed training prior, not an overtime model.
No post-test calibration or parameter adjustment was made.

Registry artifacts retain dependency/config/feature/data lineage, checksums,
training eligibility cutoff, validation predictions, joint home/away residuals,
seed and candidate/promotion status. Prepared registry directories publish after
complete writes. Explicit commands train, evaluate once, promote locally and
preview scheduled games without retraining or creating a published forecast.
Only trusted local joblib artifacts may be loaded.

### Measured results

Earlier validation: 1,139 games from 2021–2024, three ties. Multiclass log loss:
league 0.70524; rolling 0.67262; linear 0.66484; tree 0.67289. Linear was selected.
Its validation accuracy was 64.44%. Rolling had lower margin MAE (10.408 vs
10.598), so selection improved probability log loss, not every metric. The tree
did not improve the selected model. No market comparison was performed.

Selected model trained on 1,408 games from 2020–2024. Model ID:
7e7b55c635aa8de465f6efa2dc48138dc58f28d489d3f3f1547b4abe009d3956.
Internal full training/selection time was 0.984 seconds (CLI process about five
seconds including imports). Initial promotion status remains candidate.

The final 2025 test was scored once after selection: 285 games, one tie, accuracy
61.40%, log loss 0.66268, multiclass Brier 0.45563, margin MAE 10.1678 / RMSE
12.9796 points, team-score MAE 7.4899 / RMSE 9.3312 points. Seeded whole-week
bootstrap 95% interval for margin MAE: [9.2862, 11.1225]. Reliability bins expose
overconfidence in some buckets; no test-fitted correction was applied. Saved
evaluation is returned on repeat requests, not recomputed for selection.

### Verification

- `nfl models train-games artifacts/features-verified/b25b87e6f7fa843952b65ef3d67e2589a727a6a83c339e4522b5858114ceed39`:
  passed, all four candidates compared on earlier folds.
- `nfl models evaluate-games artifacts/models/7e7b55c635aa8de465f6efa2dc48138dc58f28d489d3f3f1547b4abe009d3956`:
  saved the above final test once. Full small metric/bin evidence is in
  docs/game_model_verification_2026-10-15.json; no raw player data is included.
- Real CLI `models preview-games` returned 193 future REG/POST previews with
  probabilities summing to one and explicit unpublished_preview labels.
- `.\.venv\Scripts\python.exe -m pytest`: 57 passed (14.75 seconds). New tests
  cover three-outcome probability conservation, playoff tie handling, tie scoring,
  training never seeing holdout games, one-time test reuse, promotion prerequisites
  and artifact corruption. No real data or downloaded model is used in tests.
- Ruff lint/format and git diff --check passed. Frontend unchanged.

Limitations: evaluations are approximate corrected-source analyses, not live
forecast performance. No learned injury adjustment or joint score/player model
exists yet. Expected scores are fractional and may disagree with the independent
win model until joint reconciliation in Prompt 08. Neutral-site context is not
modeled. Calibration and rare-tie quality need more evidence. No push, publication,
paid source, automatic retraining or scheduled task occurred.

Prompt 07 is next: supported offensive player participation/opportunity/production,
with honest coverage and availability limitations.

Commit: `feat(ml): train and evaluate versioned game prediction models`

## Prompt 07 — Participation audit and offensive baseline checkpoint (in progress)

October 15, 2026 (America/Chicago), after Prompt 06 commit 106120e. This is a
coherent smaller checkpoint permitted by the roadmap, **not completion of Prompt
07**. No production player model is promoted. Prompt 08 has not started.

Added a reproducible free nflverse snap-count audit with exact PFR-to-GSIS mapping,
conservative team snap-denominator checks, source manifests/checksums and atomic
normalized publication. Unverified absences remain unknown. Present offensive
participation and missing actual statistics are kept separate. Positive snap/stat
contradictions are excluded before forecasting rather than treated as zeros.

Added baseline participation probabilities from only prior known labels, prior
position shrinkage, forecast team opportunity volume, player opportunity shares
and production-per-opportunity. Active-on-offense conditional and unconditional
statistics are distinct, with empirical uncertainty ranges. Confirmed Out/inactive
inputs redistribute opportunities; questionable adds no invented coefficient.
Other-player opportunities, unknown roles/availability, unsupported cold starts and
participation/no-participation scenarios remain explicit. No learned injury or
player-production coefficients were invented. Source/feature/participation lineage
and validation residuals are saved in ignored artifacts. Preview checks hashes,
labels itself experimental/unpublished and sets recommended_for_decisions false.

### Verification and measured findings

- `nfl audit-participation`: real 2020–2026 snap Parquet files audited. Normalized
  participation ID 2a636a1923687bc8e9689c8249a3cb39e22e57c67e23dff30203341922bc9b91.
  Required source downloads/revalidation used approved network access. Team-games
  passing all conservative checks: 2020 194/538, 2021 233/570, 2022 25/568,
  2023 303/570, 2024 248/570, 2025 512/570, 2026 134/158. Many PFR rows lack
  a verified GSIS mapping; no name matches were used to hide these gaps.
- `nfl models offense-baselines artifacts/features-verified/b25b87e6f7fa843952b65ef3d67e2589a727a6a83c339e4522b5858114ceed39 data/participation/2a636a1923687bc8e9689c8249a3cb39e22e57c67e23dff30203341922bc9b91`:
  passed in 40.317 seconds internally, produced 89,897 projection rows, 41,822 known
  participation labels and 48,075 unknown. Positive-snap/missing-actual rows: 4,573;
  snap/stat contradictions excluded: eight. This is incomplete selected coverage.
- Fixed opportunity model ID:
  286d0d0f05f570b8d6e5d60c645232aa92bfb8e8fafc6e69e6fb9fdd52716b5a.
  Earlier validation seasons 2021–2024; 2025 experimental test recorded once.
  QB passing-yard MAE 122.864 versus lag comparator 73.169 (n=704), RB rushing
  21.103 versus 20.116 (n=1,806), WR receiving 22.047 versus 21.677 (n=2,644),
  TE receiving 15.886 versus 15.394 (n=1,391). The experiment underpredicts and
  is worse than the simpler comparator. It remains an unpromoted candidate.
- Participation test Brier 0.04315 on 7,342 eligible rows; selected coverage means
  this is not a full-roster estimate. Per-position/stat/workload MAE/bias and 80%
  interval coverage are saved, along with separate validation residuals. Small
  dated evidence: docs/offense_baseline_verification_2026-10-15.json.
- Real CLI preview for 2026_06_ARI_LA returned 47 explicitly experimental rows with
  availability scenarios. Unsupported roster/game queries stay explicit.
- New synthetic tests verify coverage-gated zero labels, ambiguous IDs, invalid
  counts, future-participation invariance, known-Out redistribution, unchanged
  questionable probabilities, signed yardage, opportunity conservation and missing
  actuals excluded rather than scored as zero.
- `.\.venv\Scripts\python.exe -m pytest`: 64 passed (17.66 seconds). Ruff lint
  and format checks passed (49 Python files); git diff --check passed. No frontend
  source changed. The browser remains the health screen from earlier stages.

### Next unfinished work

Finish Prompt 07: retain the simpler forecast where earlier validation favors it,
establish a defensible default, resolve/represent depth-role allocation, and validate
opponent-conditioned inputs where supported. The current experiment can allocate
too much volume to backups. Do not promote it or claim full player coverage.
Do not tune repeatedly against the already observed 2025 experimental test; preserve
it and declare new prospective evaluation eligibility for future model work.
No Prompt 08 simulation, dashboard changes, fantasy, wagering, push, publication,
paid source or Windows scheduled task was implemented in this checkpoint.

Checkpoint commit: `feat(ml): audit participation and evaluate offensive baselines`

## Prompt 07 completed — October 21, 2026

Completed the supported offensive baseline stage with explicit unknown depth roles,
unknown availability and incomplete participation coverage. Added `models
select-offense`: compare lag reference, capped lag, normalized opportunities and
bounded earlier-opponent context. Nested expanding validation selects only from
prior folds, preserves keyed OOF residuals, and reports MAE/bias/80% coverage/counts
by position/stat/workload. No learned challenger or injury coefficient was invented.
The observed 2025 experiment remains frozen and was not rescored.

Final earlier-fold selection retains the lag reference for QB/RB/WR/TE. Weighted
2021–2024 unconditional yardage MAE: QB passing 70.553 (n=2,625), RB rushing 20.669
(n=6,390), WR receiving 23.251 (n=9,522), TE receiving 16.599 (n=4,572). These match
the simpler reference; constrained/opponent alternatives did not justify replacing
it. Preserve the inferior allocation comparison as dated evidence. This is honest
baseline selection, not a claim of improvement or prospective readiness.

Team volume is predicted before allocating workload; the retained reference has an
explicit roster-lag floor when uncertain competing roles exceed historical volume.
This can inflate team volume and is documented in projections. Known-Out scenarios
redistribute work; uncertain starter promotion is never asserted. Other-player work
is conserved. Active-conditional versus probability-weighted unconditional fields,
missing actuals, unknown labels and unsupported cases retain prior contracts.

Real command: `nfl models select-offense
artifacts/features-verified/b25b87e6f7fa843952b65ef3d67e2589a727a6a83c339e4522b5858114ceed39
data/participation/2a636a1923687bc8e9689c8249a3cb39e22e57c67e23dff30203341922bc9b91
--output artifacts/player-defaults-verified`. Selected model:
`7327b7b7cbd433d543e71b1a24b17a49ff61889f1315dbc4641f80b23a7bcc1e`;
4,765 2026 projection rows. Dated evidence:
`offense_default_verification_2026-10-21.json`. Prospective 2026+ performance pending;
previews remain `recommended_for_decisions=false`.

Verification: existing and new leakage, lag retention, confirmed-Out redistribution,
unknown labels and mixed-position conservation tests pass; Ruff lint/format and
`git diff --check` pass. Next stage: Prompt 08 joint simulation.

## Prompt 08 completed - October 21, 2026

Wrote simulation_contract.md before implementation, then added seeded shared-environment
team-volume/player-allocation simulation, explicit other-player buckets, correlated
passing/receiving yards and TDs, signed yards, sacks/net passing, aggregate fumbles,
kicking/miscellaneous scoring, two-point plays and approximate overtime. Scores,
win probabilities and marginal/active-conditional player summaries come from the
same retained local draws. Raw game estimates and simulated means remain separate.

`nfl models simulate-week GAME_MODEL PLAYER_MODEL FEATURES 2024 1 --validation
--count 500` ran all 16 real validation games in 99.915 seconds. All 8,000 game draws
passed football accounting validation. Brier 0.421717, log loss 0.608410, margin MAE
8.4085 and 80% score interval coverage 90.625% (32 team outcomes). Dated evidence:
`simulation_verification_2026-10-21.json`. This is a small validation diagnostic,
not calibrated/prospective performance; broad QB intervals and unresolved roles
remain documented. A subsequent CLI smoke run uses 100 draws and validates before
publication; no forecast is published as pregame history by simulation commands.

Seeded tests cover score reconciliation, receiver/passer equality, opportunity
constraints, opposing sacks, postseason ties, Out players, repeatability and
rejection of corrupt draws. Full samples remain ignored; no sources were purchased,
pushed or published. Next: Prompt 09 immutable forecast versions and result history.

Prompt 08 checks: 72 backend tests passed (excluding the next-stage history tests);
Ruff lint/format and git diff whitespace checks passed. The final 100-draw CLI
smoke covered all 16 games in 42.114 seconds; validation Brier 0.409688, log loss
0.595905, score coverage 93.75%. Sampling counts/configs are reported separately.

## Prompt 09 completed - October 21, 2026

Added migration 0003, append-only forecast versions/schedule observations, immutable
per-game locks and provisional/settled/cancelled actual revisions. Writer-assigned
generation time rejects backdating; strict input cutoff, kickoff, delayed job and
reschedule rules are documented in forecast_history.md. SQLite triggers reject
history mutation. Late jobs cannot manufacture official pregame history. Explicit
retrospective versions are never eligible for locks. Corrected actuals retain every
revision and exact forecast/result pairs in the audit view, including player errors.

Added `nfl forecasts publish/lock/result/reconcile/audit`. Real command
`nfl forecasts reconcile 2026` imported 79 completed games from the existing validated
snapshot; it created no historical pregame forecasts. Six fake-clock/history tests
pass, including duplicate locks, late runs, missing forecasts, postponements,
timezones, backdating, immutable rows and result corrections. Next: Prompt 10
repeatable safe local refresh orchestration without installing a scheduled task.

Prompt 09 full verification: 78 backend tests passed (21.35 seconds), Ruff lint and
format checks passed, and git diff whitespace validation passed. No remote/push,
payment, deployment, or scheduled task was created.

## Prompt 10 completed - October 21, 2026

Added configurable `nfl refresh`, per-host free-source pacing, OS single-run lock,
atomic step logs/publication boundaries, daily/pregame schedule gating and catch-up
maintenance. Frozen evaluated/promoted game models and selected baseline definitions
are reused; refresh never retrains, reselects or re-evaluates the holdout. Schema and
checksum mismatches stop publication. Source failures preserve prior snapshots and
prevent dependent publication. Current observed rosters and now-cutoffs apply only
to future games, including partially started weeks. Later unknown snap coverage is
not fabricated. Unknown availability remains visible. Fresh schedule/roster inputs
and pre-kickoff generation are required for publication.

Added scripts/refresh.ps1, config/refresh.example.json and local_refresh.md with
manual Windows Task Scheduler setup, catch-up/offline limits and recovery. No task
was installed. The local config is ignored. Explicit local game promotion used the
existing completed evaluation; no new model fitting or paid service was used.

Real free 2026 ingestion (network allowed after sandbox socket restriction) downloaded
11,039,249 bytes and validated 93 completed games in 3.775 seconds. Current schedule,
roster and injury observations were captured; one unresolved roster row stayed
rejected. Two full cached-source refreshes completed in 85.599/85.901 seconds with
100 draws/game, each generating 14 genuinely pregame local versions, checking 93
past-game locks and reconciling 93 results. They never invented past pregame history.
The second run applies an explicit per-game horizon filter. Scheduled-mode cached
check returned `not_due` while safely running maintenance. Dated evidence:
refresh_verification_2026-10-21.json. Four new fake-clock/adapter tests cover schedule
windows, late/stale publication refusal, source failure boundaries, prospective-only
rosters and incompatible schemas. Next: Prompt 11 read API and dashboard.

Prompt 10 final verification: 82 backend tests passed (23.23 seconds); Ruff lint,
format and git diff whitespace checks passed. All commits and generated forecast
history remain local.

## Prompt 11 completed - October 21, 2026

Added typed read API, read-only SQLite access, bounded pagination/filters, game/player/
team forecasts, versions, revision-paired actual errors, evaluation and freshness.
Requests perform no migrations, model fitting, downloads or mutation. Added responsive
league/Cowboys schedule and game dashboard with score comparison SVG, player means/
intervals, conditional toggle, model/version audit, support/unknown/stale labels and
separate historical calibration/accuracy/error display. Empty/loading/error/retry
states are explicit; past games never acquire fake predictions.

Browser verified against the real local API: 14 week-7 games, Cowboys at Eagles,
55 player/other rows, saved versions, QB filtering, conditional toggle, a completed
Cowboys game showing actual 13-23 with no eligible forecast, and a 390px responsive
layout; viewport restored afterward. Browser console had no errors. Dated evidence:
dashboard_verification_2026-10-21.json. 84 backend tests passed (21.68 seconds), Ruff
lint/format and whitespace checks passed, and frontend strict checking/build passed.
One dependency deprecation warning is recorded for Starlette's current TestClient
httpx integration; it does not change app behavior. Next: Prompt 12 fantasy scoring
and eligible pregame lineup comparison.

## Prompt 12 completed - October 21, 2026

Added versioned configurable standard/half-PPR/PPR supported offensive scoring from
joint unrounded samples, exact QB/RB/WR/TE/FLEX assignment, explicit expected/floor/
upside objectives and numerical alternative comparisons. Unsupported fumble/two-point/
kicking/defensive contributions are excluded and clearly labeled as subtotals.
Manual weekly rosters save versioned local history. Individual kickoff, bench,
identity and slot locks prevent retroactive changes. Only eligible pregame/official
forecasts supply samples; missing official forecasts stay unsupported. Same-game
players cannot mix joint versions. Unknown availability/roles remain visible.

Added loopback Host/client, trusted origin, explicit local-header and bounded-JSON
write protection, without remote CORS access. Refactored React app entry for stable
hot reload. Real transient 11-player verification matched an exact seven-slot lineup
and increased supported expected points 36.0886 to 44.6866; no performance claim.
Browser saved/loaded an explicitly labeled verification-oct21 seven-player roster,
compared, applied and re-compared its lineup (56.91 expected, 34.18-83.54 interval,
then 0.00 improvement against itself). No user league/roster was inferred or connected.
No new browser errors after clean reload; earlier edit-time HMR errors were resolved.
Details: fantasy.md and fantasy_verification_2026-10-21.json. Next: Prompt 13 paper-only
virtual entries/ledger and corrected-result settlement.

Prompt 12 final checks: 90 backend tests passed (20.89 seconds), Ruff lint/format,
git diff whitespace and frontend strict checking/build passed. TestClient's existing
dependency deprecation warning remains documented; no runtime failure occurred.

## Prompt 13 completed - October 21, 2026

Added immutable manual moneyline/spread/total lines, Decimal odds/payout arithmetic,
integer minor virtual credits, serialized stake checks, duplicate prevention and
versioned actual/schedule-based settlement. Push/tie/cancellation/reschedule policies
are explicit. Corrections append compensating events and can expose virtual debt;
no balance rewrite or duplicate settlement is allowed. Ledger/entry records refer
to exact immutable forecast/line/evidence IDs. Refresh maintenance settles existing
entries only; it never wagers. No real-money/payment/account/odds-feed integration
exists. All HTTP writes remain loopback-protected.

Dashboard includes virtual account initialization, hypothetical manual odds and
joint-sample probability/EV estimates with Monte Carlo limitations, entries,
bankroll chart, ROI/count and settlement audit. Browser verification used a clearly
labeled verification-oct21 virtual account: seeded 1000.00, entered 10.00 pending,
remaining 990.00, zero settled entries/ROI. The default paper account remains empty.
No real funds, markets or settled performance were invented. Evidence:
paper_verification_2026-10-21.json; policies: paper_ledger.md.

95 backend tests passed (21.38 seconds); five targeted paper tests passed after the
final cutoff correction, including conservation, pushes, cutoff/duplicate rejection,
refunds, immutable rows and negative correction debt. Ruff lint/format and frontend
strict build passed. Next: Prompt 14 coverage audit and evaluated kicking/team
special-teams/defense additions, keeping unsupported roles explicit.

## Prompt 14 completed - October 21, 2026

Audited free existing raw/normalized 2020-2026 sources and added evaluated team
FG/PAT attempt/make and defensive sack/interception baselines. Exact raw row identity,
checksums, nonnegative/integer constraints, makes<=attempts and opponent reconciliation
are enforced. 3,572 team-game rows have no nulls in these fields; 56 defensive sack
credit disagreements remain excluded, not invented actuals. Earlier-fold selection
retains league FG, team PAT and opponent-aware defensive baselines. The first fixed
2025 additional-target test is frozen; offense's observed 2025 holdout was not reused.
Team FG-made MAE 1.005 (570), sack MAE 1.372 (561), INT MAE 0.690 (570), with explicit
bias/coverage and limitations. See team_component_verification_2026-10-21.json.

Integrated optional frozen team components into simulation/2 and fresh pregame
versions, preserving kick attempts/makes, score totals, opposing sacks/interceptions
and existing fantasy eligibility. The 16-game/100-draw real 2024 diagnostic ran in
13.829 seconds, Brier 0.469588, log loss 0.659358, score coverage 90.625%; Brier did
not improve over the prior small check. No calibration/decision-readiness claim.
Corrected reliability bin-edge double counting and verified seeded legacy samples
unchanged by loop optimization. Added causal, raw-integrity, kick/defense and PRE
rejection tests. The real current cached refresh created 14 pregame versions,
reconciled 93 games and left the paper test pending in 42.507 seconds; browser
verified new team summaries.

Audited individual roles/defenders/returners and missing PRE coverage. No individual
kicker/defender/returner, full DST fantasy, other-role assignment or preseason model
is fabricated. PRE is explicitly rejected. Coverage limits and future coherent
commit suggestions are in expanded_coverage.md. Next: Prompt 15 reproducibility,
CI, local release review, measured operations and resume-grounded documentation.

Prompt 14 final checks: 100 backend tests passed (16.02 seconds), Ruff lint/format,
frontend strict build and git diff whitespace checks passed. Full datasets/models
remain ignored and local. No new source purchases, remote, push, publication or
scheduled task was created.


## Prompt 15 completed - October 21, 2026

Reviewed the complete local app and corrected two release-level eligibility gaps:
comparisons must use the saved roster rather than bypassing kickoff locks with an
unsaved body; rescheduled locked versions remain immutable but are excluded from
scored/new-lineup eligibility. Added trusted Host protection for reads/writes and
regressions for untrusted hosts/oversized JSON. Replaced deprecated TestClient usage
with the existing HTTPX ASGI transport, avoiding a new Python dependency/warning.
Added a generated-fixture end-to-end flow spanning ingestion, causal baseline,
joint accounting, publication/lock, fantasy, virtual entry, actual correction and API.

Added pinned Prettier formatting/readable frontend source, EditorConfig/LF policy,
expanded check.ps1, and a Windows/Linux CI definition with official action commit
SHAs verified against public tags. CI uses locked installs and generated fixtures,
read-only repository permissions and no deployment steps. It has not run remotely:
the new workflow was not pushed. An existing origin remote was discovered during
review and preserved unchanged; no remote was created/changed or pushed by this work.

Clean dependency setup with existing runtimes and initially empty download caches:
Python 49 packages in 11.281s; frontend 27 packages in 3.171s. Both clean environments
passed their relevant checks; latest-source clean Python passed all 104 tests in
19.17s, and the clean frontend passed formatting/strict production build. The full
trusted check.ps1 passed all 104 tests in 19.26s, Ruff and frontend formatting/build.
Default Windows script policy blocks ordinary .ps1 invocation, so verification used
one process-scoped ExecutionPolicy Bypass; no user/machine policy was changed.
Direct equivalent commands remain documented. The new end-to-end test passed.

An explicit benchmark trained a separate game candidate in 0.835s wall/0.807s internal
without rescoring the held-out test, peak process working set 222,736,384 bytes.
A full 14-game/100-draw cached-source refresh ran in 62.215s, peak process working
set 847,671,296 bytes. Earlier expanded refresh was 42.507s; these are measured
runs under variable local IO/load, not a guaranteed speedup or runtime. Current data
file bytes 208,735,356; retained artifact bytes 240,078,131 after disposable setup
scratch cleanup. Full earlier ingestion and current free download timings retain
their actual cache/byte scope. Measurements: release_measurements_2026-10-21.json.

Saved/visually inspected real dashboard/detail screenshots; rewrote README with
supported scope, setup/run/reproduce/check commands, architecture, dated metrics,
learned parameters versus configuration, failed experiments, limitations and
operations. Added decisions.md and resume.md with claims grounded in actual local
results. Updated contracts/history/fantasy/recovery docs. A pattern review of release
text found no potential credential/private-key strings; it is not a formal security
audit. Data/models/secrets remain ignored. One unreferenced development draft with
outdated code metadata was marked unusable and quarantined after proving no saved
forecast referenced it. Published models/samples, user data and original environment
were preserved; four generated reproduction environments/caches were removed only
after resolved-path/link checks. Details: release_review_2026-10-21.json.

Final supported checkpoint is a local research release, not proof of prospective
accuracy, betting advantage, complete player coverage or hosting readiness. Individual
kicker/defender/returner roles, full DST fantasy, unsupported scoring contributions
and preseason remain explicitly unsupported as allowed by the coverage stage.
Authentication, consistent backups, durable hosted jobs, concurrency/load testing,
secret management and source redistribution review are future hosting prerequisites.
No money, external messages, real wagers, remote creation, push, publication,
deployment or Windows scheduled task was performed. All numbered implementation
prompts are complete for the documented supported baseline scope.

Local prompt commits before this final release checkpoint:
07 d68031b; 08 2d30235; 09 46c57bc; 10 4d4c61c; 11 a3d26b3;
12 c11801f; 13 8371280; 14 97f12e2. Prompt 15 is the following release commit.

Final release verification: 105 tests passed in 18.62 seconds; Ruff lint/format, pinned frontend formatting, strict TypeScript and Vite build all passed. Added a regression ensuring the authoritative forecast remains visible and scored when outside the latest 20 versions. Clean-environment verification above remains the earlier 104-test checkpoint.
