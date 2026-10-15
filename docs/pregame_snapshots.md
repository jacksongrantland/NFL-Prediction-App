# Pregame observations (Prompt 04)

These commands preserve local observations; no prediction or injury probability
model exists yet. Run from the application root:

```powershell
.\.venv\Scripts\nfl.exe capture-pregame --season 2026
.\.venv\Scripts\nfl.exe pregame-as-of 2026_06_ARI_LA --season 2026 --cutoff "2026-10-15T17:00:00Z"
```

Choose a cutoff after your own capture. Earlier cutoffs correctly return missing
data. Source game IDs can contain LA even though normalized team IDs use LAR.
`--data-dir PATH` selects another store. Timestamps require a timezone; offsets
are converted to UTC.

Capture revalidates the audited schedule, season roster and injury Parquet URLs
with the existing bounded downloader. It needs no completed games or historical
PBP/stat ingestion. The season roster is a current observation, not a verified
depth chart, active list or historical pregame membership. Repeated captures
append observations even when bytes have not changed, recording source checks.

Schedule and roster are required and publish together with the injury result in
one transaction. Missing/invalid injuries become `unavailable`; `--no-injuries`
records `disabled`. Neither prevents useful schedule/roster observations. Rejected
roster IDs and unresolved injury mappings remain in immutable batch payloads.
Injury mappings require exactly one schedule match on season/week/type/team;
ambiguous duplicate player/game injury records disable that injury capture.

## Manual fallback

Copy `config/manual_availability_template.csv` to an ignored path such as
`data/manual_availability.csv` and add sourced records. The template contains
only a header, no real or synthetic player observations.

```powershell
.\.venv\Scripts\nfl.exe import-availability data/manual_availability.csv --season 2026
```

Capture a schedule first. The exact CSV columns are:

| Column | Validation / meaning |
|---|---|
| player_id | GSIS syntax: two digits, hyphen, seven digits; never a name |
| game_id | Must exist in the latest locally captured season schedule |
| team_id | Must participate in that game; known aliases normalized |
| source_url | Required HTTP(S) reference; importer does not scrape it |
| published_at | Nullable, timezone-aware; enter only if supported by the source |
| observed_at | Required, timezone-aware; when you observed the report |
| injury_designation | Nullable source designation; no fixed playing probability |
| practice_participation | Nullable, independent practice status |
| roster_status | Nullable, independent roster status |
| game_inactive | Blank (unknown), `true`, or `false`; never inferred from designation |

At least one status is required. Status text is preserved as supplied; validation
checks ID syntax and schedule/team references, not the truth of the cited report
or independently verified player membership. Never supply an invented player ID.
Unknown publication time stays blank. Require
`published_at <= observed_at <= local import time`. Invalid rows, duplicate keys,
malformed CSV or naive/future timestamps reject the whole import. Original valid
CSV bytes are retained under `data/raw/manual/{checksum}.csv`. Downloads retain
raw blobs and source manifests.

Each manual row is a complete availability observation. Blank fields mean unknown,
not carry-forward instructions. Roster observations are returned separately so
roster status never silently becomes an injury designation or inactivity flag.

## Cutoff and freshness policy

SQLite migration 0002 adds append-only `observation_batches`, owning prospective
schedule, roster and availability observations. Triggers reject updates/deletes.
Historical analytical Parquet is not rewritten; observations are distinct
operational history with source hashes/manifests.

Each batch has observed_at and app-generated recorded_at. Strict queries require
both at or before cutoff. Importing an old report today cannot make it appear in
yesterday's strict snapshot. Historical injury date_modified is source metadata
only; it never establishes publication or availability.

Queries select the latest eligible complete nflverse batch per dataset and
eligible manual observations. For a player/game the latest observed_at wins,
then recorded_at, then batch ID. Later free-feed observations can supersede manual
entries. Manual imports update only their listed players; a player absent from
the latest free injury file is unknown, not healthy. Old free-feed rows do not
carry forward across complete captures.

Missing, unavailable, disabled, unknown and stale remain explicit. Staleness defaults
to 36 hours (`--stale-hours`) and measures time since **local observation**.
`observed` means recently checked, not recently published. Source file retrieval,
ETag and Last-Modified metadata remain in batch payloads; report age, completeness
and update continuity are unproven. Output explicitly says injury_coverage unknown.

No recently observed eligible availability produces mode no_injury_data. This is
a data-readiness label for a future no-injury baseline, not a model. Stale values
remain visible. Queries expose schedule/roster batch IDs and availability sources
and timestamps. There is no dashboard, automatic schedule, scraping or modeling.

Today's corrected historical stats, rosters and injury files cannot establish
their original pregame versions. Strict earlier queries return missing without
local observations recorded by cutoff. Historical evaluations using corrected
files must remain labeled approximate.
