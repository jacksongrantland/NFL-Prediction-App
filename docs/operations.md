# Local data operations

Run commands from the application root. Data is local and ignored by Git. No
scheduled task is installed and no automatic retraining or prediction exists yet.

See [`pregame_snapshots.md`](pregame_snapshots.md) for capture/import/query commands.
Migration 0002 adds append-only prospective observation history. Back up SQLite
and raw data together. Failed required-source captures/imports publish no partial
observations. Injury-only failures publish explicit unavailable status alongside
useful schedule/roster observations.

Prompt 03 audit fixes: missing required game context now fails validation;
truncated transfers retry up to three times. Default historical ingestion reports
skipped current seasons when their schedule is absent or the season has not
started, without fetching nonexistent stats. Skipped seasons never replace active
pointers and are not claimed as complete. Once scheduled games have started,
missing stats/finality still fail normally. Missing historical sources still fail
the atomic run. Schedule integrity is checked before deciding to skip.

## Install locked dependencies

```powershell
py -3.13 -m uv sync --locked
```

## Ingest and inspect

One-season smoke run:

```powershell
.\.venv\Scripts\nfl.exe ingest --season 2025 --current-season 2026
.\.venv\Scripts\nfl.exe data-counts 2025
```

Six completed seasons plus available current-season results:

```powershell
.\.venv\Scripts\nfl.exe ingest --current-season 2026
.\.venv\Scripts\nfl.exe data-counts 2026
```

Repeat `--season` to choose multiple seasons. Without `--current-season`, the CLI
uses the current UTC year, except January/February use the prior NFL season.
An explicit season is preferable for reproducing the dated verification. Future
seasons are rejected. Default storage root is `data`; `--data-dir PATH` selects
another local store.

Force re-fetch of every requested source, including completed historical seasons:

```powershell
.\.venv\Scripts\nfl.exe ingest --season 2025 --current-season 2026 --force-refresh
```

Force refresh bypasses cached validators, not validation. Different bytes create
new immutable blobs/snapshots. Identical content reuses the same normalized snapshot.
Historical raw files otherwise reuse their checksum-verified cache; schedules and
current-season sources use conditional HTTP requests. A change elsewhere in the
all-season schedule does not rebuild a historical snapshot whose own rows are
unchanged. Source-file changes within a season rebuild that season; incremental
refresh operates at source-file/season level, not row-level HTTP fetching.

## Storage and publication

- `data/raw/blobs/{sha256}.csv|parquet`: immutable complete downloaded bytes.
- `data/raw/manifests/{manifest_id}.json`: source hashes, sizes, retrieval times,
  schema fingerprints, lineage and conservative coverage/rights status.
- `data/normalized/{season}/{snapshot_id}/`: validated Parquet tables and
  `summary.json`. Summary records full-file output hashes, rows, null counts,
  teams, weeks, aliases' original labels, rejected IDs, and schema drift.
- `*_rejected.parquet`: roster/player-stat rows without usable GSIS identity.
  They are excluded from identified-player tables, never assigned fabricated IDs.
- `data/metadata.sqlite`: Alembic revision, ingestion runs, URL cache metadata,
  source-manifest references, immutable snapshot catalog and active season pointers.
- `data/ingestion.lock`: OS-backed single-writer lock file; the lock automatically
  releases after process exit. The file itself can remain.

Every source is downloaded and normalized before publication. A prepared snapshot
directory is renamed into place only when complete, then one SQLite transaction
publishes **all requested seasons** and marks the run successful. Failure in a
later season leaves all previously active pointers unchanged. Prepared but
unpublished snapshots can be reused on a retry; no partial directory is published.

The snapshot identity includes source content, season, normalization code hash and
pandas/PyArrow versions. Schedule content is fingerprinted for the requested season,
while its source manifest still hashes the complete raw file. Reused snapshots
retain their original manifest lineage. Conservative code/dependency changes may
rebuild snapshots; old versions stay intact. No competing copies of game/stat rows
are stored in SQLite or a writable DuckDB database. DuckDB uses an in-memory
connection to read the published immutable Parquet files.

## Validation and game completion

Required columns and types are checked before publication. Unknown team/game-type
codes, malformed IDs, conflicting duplicate keys, impossible counts, unknown game
references, schedule/stat context mismatches, and score inconsistencies fail the
run. Exact duplicates may be removed only with their raw record numbers recorded.
Unresolved roster/player identity rows are saved separately with counts. Source
game IDs remain unchanged even when team aliases (LA→LAR, JAC→JAX, WSH→WAS) are
normalized; raw team labels and historical game membership remain available.

A completed game needs a unique PBP `play_type_nfl=END_GAME` row, matching terminal
home/away scores in the schedule, and a known kickoff in the past. This handles
walk-off overtime with clock remaining. Completion is derived from these source
checks; it is not a claim that results can never be corrected. Completed games
must have two team-stat rows and identified player-stat coverage for both teams.
Only reconciled completed games enter normalized play/stat tables. All scheduled
games remain in `games.parquet`, with unknown/provisional/final status and evidence.
Historical seasons with scored-but-unfinalized games fail publication; current
season gaps are explicitly listed for later refresh.

The verified schedule source omits preseason and does not give an authoritative
cancellation feed. Missing/cancelled games are not invented. Preserve source
schedule revisions on refresh; pregame forecast reschedule/locking policies are
future work. Historical data remains approximate for strict as-of evaluation:
today's corrected source files do not establish their original availability.

## Recovery

- Downloads use a 45-second socket timeout, at most three attempts for transient
  connection failures/429/selected 5xx, and 1/2-second backoff. A source is capped
  at 256 MiB; errors never silently substitute old current-season data.
- Normal incomplete downloads remove their `.part` file. A killed process may
  leave `.part` or `.staging-*` artifacts. They are never selected by active pointers;
  rerun the same command. The next lock-holding run marks abandoned running records
  as interrupted. Leftover staging files may be inspected and manually cleaned later.
- A failed run records its error in `ingestion_runs` and retains prior published
  data. Fix the source/connection problem, then rerun. Do not edit normalized files
  to bypass validation.
- Raw and normalized cache hits verify checksums. Corruption fails clearly rather
  than overwriting an immutable artifact. Restore the matching bytes from a backup,
  or ingest into a fresh `--data-dir data-recovery` store for investigation.
- Keep raw data/manifests and SQLite metadata together when backing up. No backup
  or cloud publication is automated. Schema upgrades run through packaged Alembic
  migrations when the store opens; revision 0001 contains only ingestion metadata.

Use tests' tiny generated fixtures for offline development; they are explicitly
synthetic and never inserted into the real data store. No raw NFL files, models,
credentials, photos, or logos should be committed to Git.
