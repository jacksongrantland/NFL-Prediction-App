# Free source audit

Audited October 14, 2026 (America/Chicago). Machine evidence is in
[`source_audit_2026-10-14.json`](source_audit_2026-10-14.json). Its UTC retrieval
times fall on October 15. This is a source audit, not ingestion or model validation.

## Decision

Use direct nflverse CSV/Parquet adapters, not an unverified wrapper. The six
completed NFL seasons are **2020–2025**, plus available 2026 data. All 49 target
annual CSV assets were listed and downloaded as bounded probes. Seven dataset
families were checked, including weekly rosters in addition to season rosters.
The audit also read one 2,184,486-byte schedule file. No complete annual PBP,
player, roster, injury, or snap dataset was downloaded. The small 2026 team-stats
CSV fit inside the 64 KiB probe and was read completely (158 rows).

All files have the required base columns except the 2025/2026 injury timestamp
column. **48/50 probes verified; two known optional-source schema gaps**. Existence
and prefix samples do not prove full-season row counts, all teams/weeks, duplicate
absence, non-null IDs, or accuracy. Full coverage validation belongs to Prompt 03.

## Availability matrix

`S` = asset exists and sample base schema verified, not season completeness.
`T` = injury status sample exists, but `date_modified` is absent.

| Dataset | Required for initial pipeline? | 2020 | 2021 | 2022 | 2023 | 2024 | 2025 | 2026 |
|---|---|---|---|---|---|---|---|---|
| Schedules/results | Yes | S | S | S | S | S | S | S |
| Play-by-play | Yes, selected fields | S | S | S | S | S | S | S |
| Weekly player stats | Yes | S | S | S | S | S | S | S |
| Weekly team stats | Yes | S | S | S | S | S | S | S |
| Season rosters | Yes, identity context | S | S | S | S | S | S | S |
| Weekly rosters | Optional enrichment; prefer for historical membership | S | S | S | S | S | S | S |
| Snap counts | Optional workload enrichment | S | S | S | S | S | S | S |
| Injuries | Optional; no-injury model must work | S | S | S | S | S | T | T |

Weekly roster absence must disable unsupported historical roster-based features,
not replace them with today's team. Historical stat rows still provide game team.

The schedule artifact contains the following target-season rows:

| Season | Schedule rows | Rows with both scores | Types observed |
|---|---:|---:|---|
| 2020 | 269 | 269 | REG, WC, DIV, CON, SB |
| 2021 | 285 | 285 | REG, WC, DIV, CON, SB |
| 2022 | 284 | 284 | REG, WC, DIV, CON, SB |
| 2023 | 285 | 285 | REG, WC, DIV, CON, SB |
| 2024 | 285 | 285 | REG, WC, DIV, CON, SB |
| 2025 | 285 | 285 | REG, WC, DIV, CON, SB |
| 2026 | 272 | 79 | REG |

Scores are evidence of recorded results, **not a final-status contract**. Reconcile
finalization/cancellations explicitly during ingestion. The 2022 count differs
from adjacent seasons; do not fill a missing game with a fabricated result.
No preseason rows or future 2026 playoff rows were present. No verified preseason
schedule adapter was selected; retain PRE in the canonical contract for later work.

## URLs, access, and cadence

All chosen URLs are public HTTPS downloads without paid credentials. Use one
source adapter per family and check HTTP status/schema before accepting a snapshot.
For release assets, use
`https://github.com/nflverse/nflverse-data/releases/download/{tag}/{filename}`.

| Dataset | Tag / filename pattern | Documentation and identifiers |
|---|---|---|
| Schedule | `https://raw.githubusercontent.com/nflverse/nfldata/master/data/games.csv` | [Schedule loader](https://github.com/nflverse/nflreadr/blob/main/R/load_schedules.R), [dictionary](https://nflreadr.nflverse.com/articles/dictionary_schedules.html); `game_id`, season, week, home/away team |
| PBP | `pbp/play_by_play_{season}.csv` or `.parquet` | [Loader](https://nflreadr.nflverse.com/reference/load_pbp.html); `game_id`, `play_id`, GSIS participant IDs |
| Player stats | `stats_player/stats_player_week_{season}.csv` or `.parquet` | [Loader](https://nflreadr.nflverse.com/reference/load_player_stats.html); `player_id` (GSIS), `game_id`, team |
| Team stats | `stats_team/stats_team_week_{season}.csv` or `.parquet` | [Loader](https://nflreadr.nflverse.com/reference/load_team_stats.html); `game_id`, team |
| Season roster | `rosters/roster_{season}.csv` or `.parquet` | [Loader](https://nflreadr.nflverse.com/reference/load_rosters.html); `gsis_id`, `pfr_id`, team, season |
| Weekly roster | `weekly_rosters/roster_weekly_{season}.csv` or `.parquet` | [Loader](https://nflreadr.nflverse.com/reference/load_rosters_weekly.html); `gsis_id`, season, week, game_type, team |
| Snaps | `snap_counts/snap_counts_{season}.csv` or `.parquet` | [Loader](https://nflreadr.nflverse.com/reference/load_snap_counts.html); canonical `game_id`, `pfr_game_id`, `pfr_player_id` |
| Injuries | `injuries/injuries_{season}.csv` or `.parquet` | [Loader](https://nflreadr.nflverse.com/reference/load_injuries.html); `gsis_id`, season, week, team; no `game_id` in inspected schemas |

The schedule R loader uses an RDS sibling; this app selects the CSV artifact from
the same maintained repository. Release metadata lists CSV and Parquet for every
target annual source. Only CSV contents were inspected; Parquet contents remain
unverified until ingestion. Weekly `stats_*_week` preserves game detail; `reg`,
`post`, and `regpost` are season summaries and must not substitute for lagged rows.

The [official update schedule](https://nflreadr.nflverse.com/articles/nflverse_data_schedule.html)
documents schedules every five minutes, rosters and injuries daily at 07:00 UTC,
snaps at 00/06/12/18 UTC, and PBP/player/team stats nightly after game days with
additional game-day runs. It recommends a Wednesday-night/Thursday stats refresh
for corrections. These are upstream intentions, not freshness guarantees. The
current PBP/stats/roster/injury assets had October 14 updates; snap assets had an
October 13 update. Always inspect the actual manifest rather than a stale release
description (the snaps release description still says 2022).

Daily app refresh is sufficient initially. Later pregame checks must respect the
actual source cadence and use caching/backoff. Unauthenticated GitHub API rate
limits can prevent metadata probes; a 403 is unknown availability, not absent data.

## Injury and historical timestamp limitations

The 2020–2024 samples expose `date_modified`; 2025/2026 instead add `season_type`
and omit that timestamp. Neither layout proves a preserved history of each report
revision. Do not treat a historical row's game week, file update, retrieval time,
or even `date_modified` alone as verified pregame publication evidence.

Current injuries are available as downloadable status data at this audit date,
contrary to the older planning concern that a feed might be absent. Completeness,
all player statuses, practice-day history, and update continuity remain unproven.
Keep practice participation, injury designation, roster status, and game inactivity
separate. Do not infer active probability from a designation.

Prompt 04 should save prospective timestamped snapshots and implement a validated
manual CSV fallback: source URL, published_at (nullable), observed_at, player_id,
game_id, team, injury_designation, practice_participation, roster_status, and
game_inactive. Resolve game mapping against schedules; ambiguous mappings fail.
Only trustworthy source publication evidence establishes published_at; otherwise
observed_at is the earliest proven availability for a locally observed snapshot.
Show missing/stale/unknown. Exclude undated injury histories from strict as-of
evaluation; allow a clearly labeled no-injury baseline. No paid feed or broad news
scraper was selected.

## Attribution and redistribution review

This section records evidence, not a blanket license determination.

| Dataset | Evidence / credit | Redistribution status |
|---|---|---|
| Schedule | Lee Sharpe and nflverse; [nfldata repository](https://github.com/nflverse/nfldata) | No dataset-specific license confirmed in inspected documentation. Review required before bundling or public redistribution. |
| PBP | nflverse / nflfastR contributors and underlying NFL data | nflverse-data publishes a CC BY 4.0 repository license; retain attribution/source and mark transformations. Underlying-source rights remain a separate review. |
| Player/team stats | nflverse / nflfastR calculated statistics | Same repository CC BY evidence; preserve computation lineage and review any upstream restrictions before redistribution. |
| Season/weekly rosters | nflverse and credited upstream roster providers | Same repository CC BY evidence; provider-specific grant not independently established. Review required before redistribution. |
| Snaps | Pro Football Reference / Sports Reference, distributed by nflverse | Third-party source. PFR pipeline software GPL is not a data permission. Provider data-use page returned HTTP 403 during review; no redistribution permission verified. |
| Injuries | nflverse; upstream injury-report API as described by loader | Same repository CC BY evidence; specific upstream API/data rights not independently established. Review required before redistribution. |

References: [nflverse-data license](https://github.com/nflverse/nflverse-data/blob/main/LICENSE.md),
[PFR pipeline](https://github.com/nflverse/nflverse-pfr),
[Sports Reference data-use page](https://www.sports-reference.com/data_use.html).
Do not conflate nflreadr/nflfastR/pipeline software licenses with every dataset's
terms. Raw data and models stay ignored in Git. Do not bundle third-party data
fixtures, player photos, or logos as part of this stage. A future shared deployment
needs a dataset-by-dataset review; this stage creates no public data service.

## Reproduce this audit

From the app root:

```powershell
.\.venv\Scripts\nfl.exe audit-sources --current-season 2026
```

Default output: ignored `data/audits/source_audit.json`. Use `--output` for another
path and `--completed-seasons 6` to select the history window. An explicit season
avoids calendar ambiguity. It uses seven public release metadata calls, up to
64 KiB per annual CSV, four concurrent probes, and a schedule capped at 8 MiB.
Servers may ignore HTTP Range; the client still limits bytes read. Request timeout
is 30 seconds. No credentials are read, no synthetic rows are substituted, and no
normalization/ingestion occurs. Reports contain headers and counts, not raw player
records. Output paths are overwritten on rerun; use a new name to preserve history.

The dated evidence was generated with:

```powershell
.\.venv\Scripts\nfl.exe audit-sources --current-season 2026 --output docs/source_audit_2026-10-14.json
```

Exit code **1 is expected for this dated audit**: it reports missing
`date_modified` in injuries 2025/2026. Inspect each gap instead of treating all
nonzero exits as source outages. Network/rate-limit errors are reported distinctly.
The known optional injury gap does not prevent Prompt 03's core ingestion.
