# Initial contracts

These conventions and the schemas below govern Prompt 03 ingestion. Source headers
were sampled in Prompt 02; full data types, nullability, uniqueness, and season
completeness must still be validated over actual ingestion runs.

Prompt 03 implements games, selected plays, offensive player/team stat fields,
and season/weekly roster observations. It does not yet ingest snaps or injuries.
The contracts for those later entities remain targets, not implemented tables.
See `operations.md` for publication and completion-evidence rules.

- Game IDs: preserve verified nflverse game IDs as strings. Player IDs: use GSIS
  strings where verified. Team IDs: a versioned canonical abbreviation mapping.
  Preserve source IDs alongside canonical IDs and explicitly map aliases. No names
  as primary keys; no invented IDs for unresolved source entities.
- Times: timezone-aware UTC, serialized as ISO 8601 with `Z`. Display in
  `America/Chicago`, including daylight saving transitions. Never infer a timezone
  from the computer's local settings.
- Separate scheduled kickoff, observed kickoff, retrieved_at, available_at,
  generated_at, and prediction cutoff. Retrieval today does not prove historical
  availability. Unknown source publication times are null, not guessed.
- Units: yards for yardage, seconds for durations, integer counts for attempts,
  receptions, touchdowns, and realized scores. Probabilities lie in [0, 1]. Yardage
  may be negative. Distributions and expected values may be fractional.
- Missing: use null with explicit missing/stale/unsupported context. Zero represents
  a known zero. No participation differs from missing actual statistics.
- Precision: retain float64 analytical values; do not round before aggregation,
  scoring, evaluation, or simulation. Round only for display. Future credit ledgers
  use integer minor credit units or decimal arithmetic, never binary float balances.
- Preserve season, week, game type, historical team membership, source lineage,
  schema version, and result revision. Training includes the full league.
- Health: GET `/api/health` returns HTTP 200 with
  `{"status":"ok","service":"nfl-prediction","version":"0.1.0"}`.
  Health confirms the API process responds; it does not assert data/model readiness.

No forecast endpoint exists yet. Later stages must define consistency and versioning
contracts before implementing simulation and pregame locking.

## Raw source schemas (audited headers)

Keep immutable source bytes, original columns, and a manifest. Raw CSV values are
strings until explicitly parsed. Full per-season column lists are recorded in
`source_audit_2026-10-14.json`; unexpected columns must not silently alter features.

| Family | Identity/context columns | Selected value fields and observed differences |
|---|---|---|
| Schedule | game_id, season, week, game_type, home_team, away_team | gameday, gametime, home_score, away_score; no explicit final-status field among required columns |
| PBP | game_id, play_id, season, week, season_type, posteam, defteam | 372 columns observed; select necessary participant/opportunity/yardage/scoring fields during ingestion rather than loading every field into features |
| Player weekly stats | player_id, game_id, season, week, season_type, team, opponent_team | 150 columns observed; attempts, completions, passing_yards, carries, rushing_yards, targets, receptions, receiving_yards, touchdown fields |
| Team weekly stats | game_id, team, season, week, season_type, opponent_team | 138 columns observed; team opportunity and production totals |
| Season/weekly roster | gsis_id, pfr_id, season, team, week, game_type | 36 columns observed; position, status and source identity crosswalks. Season rosters are latest-per-season, not historical pregame snapshots. |
| Snaps | game_id, pfr_game_id, pfr_player_id, season, week, game_type, team | 16 columns observed; offense/defense/ST snaps and percentages; player ID requires a verified PFR-to-GSIS crosswalk |
| Injuries 2020–2024 | gsis_id, season, week, game_type, team | 16 columns; report/practice primary/secondary injury, report_status, practice_status, date_modified |
| Injuries 2025–2026 | gsis_id, season, week, game_type, season_type, team | 16 columns; same status/injury fields but no date_modified. Preserve this layout difference; do not invent its missing timestamp. |

Actual sample identifiers confirm player_stats.player_id and rosters/injuries.gsis_id
use GSIS strings, e.g. `00-0023459`. Snap game_id uses the canonical format, e.g.
`2026_01_ARI_LAC`, while pfr_game_id is a separate namespace. A name match never
establishes an identity mapping. Unmapped PFR IDs remain unresolved and cannot be
joined into player features until reconciled with roster crosswalks.

## Normalized schemas (implementation contract)

All normalized rows carry `source_manifest_id` (SHA-256 of canonical manifest JSON),
`source_row_number` (1-based record number excluding header), and `schema_version`.
Versioned Parquet snapshot partitions add season and retrieval/snapshot identity.
Validate candidate keys before publishing; quarantine contradictory duplicate rows.
Exact raw-row duplicates may be collapsed only with counts and provenance retained.

| Entity | Candidate key within a snapshot | Typed normalized fields |
|---|---|---|
| Games | game_id:string | season:int16, week:int16, game_type:enum, home_team_id:string, away_team_id:string, kickoff_at:UTC timestamp nullable, source_gameday:date, source_gametime:string nullable, home_score:int16 nullable, away_score:int16 nullable, result_status:enum(unknown/provisional/final/cancelled) |
| Plays | game_id:string + play_id:int64 | season:int16, week:int16, game_type:enum, possession_team_id:string nullable, defense_team_id:string nullable; selected participant IDs nullable strings, counts int32, yardage int32/float64 as source definitions require |
| Player game stats | game_id + player_id + team_id | player_id:string, team_id:string, opponent_team_id:string, season:int16, week:int16, game_type:enum; attempts/completions/carries/targets/receptions/TD counts:int32 nullable; yardage:int32 nullable |
| Team game stats | game_id + team_id | team_id:string, opponent_team_id:string, season:int16, week:int16, game_type:enum; opportunity counts:int32 nullable and production yardage:int32 nullable |
| Roster observations | season + week(nullable) + game_type(nullable) + player_id + team_id | GSIS player_id:string nullable, source_pfr_id:string nullable, position:string nullable, roster_status:string nullable; preserve original team and source season/week |
| Snaps | game_id + source_pfr_player_id + team_id | player_id:string nullable until crosswalk resolved, source_pfr_player_id:string, team_id:string, offense_snaps/defense_snaps/st_snaps:int32 nullable, respective shares:float64 nullable in [0,1] after verifying source percent convention |
| Availability observations | player_id + game_id(nullable) + observed_at + source_row_number | team_id:string, season:int16, week:int16, game_type:enum, injury_designation:string nullable, practice_participation:string nullable, injury fields:string nullable, roster_status:string nullable, game_inactive:bool nullable, published_at:UTC timestamp nullable, observed_at:UTC timestamp, source_modified_at:UTC timestamp nullable |

These are snapshot keys; multiple historical snapshots intentionally preserve
revisions. A source row with missing required identity is not assigned a fake ID.
Keep it in a rejection/coverage report. Injuries have no direct game_id: join on
historical season/week/type/team only when the schedule yields exactly one match.
Preserve unresolved rows and their context rather than picking an arbitrary game.

Map REG to REG; map WC/DIV/CON/SB to POST at the broad game-class level while
retaining `playoff_round`. Preserve raw codes alongside normalized type. PRE is
reserved but unsupported by the selected schedule artifact. Unknown codes fail
validation. Schedule dates and times are Eastern per the source dictionary; combine
using `America/New_York`, then convert to UTC. Missing/TBD kickoff stays null; do not
assume midnight. Windows environments must include an IANA timezone data provider
when timestamp normalization is implemented.

Use canonical team codes ARI, ATL, BAL, BUF, CAR, CHI, CIN, CLE, DAL, DEN, DET, GB,
HOU, IND, JAX, KC, LAC, LAR, LV, MIA, MIN, NE, NO, NYG, NYJ, PHI, PIT, SEA, SF,
TB, TEN, WAS. Version aliases such as LA→LAR, JAC→JAX, WSH→WAS in configuration;
preserve original labels and historical membership. Do not rewrite old player
games with today's team. Audit unrecognized aliases before mapping them.

## Manifest contract

`data/manifests.py:SourceManifest` validates the contract; the exported
[`source_manifest.schema.json`](source_manifest.schema.json) is its JSON Schema.
Use this full manifest for future raw ingestion. The audit report is a separate,
lighter evidence format, not a claim that ingestion manifests already exist.

| Field | Meaning |
|---|---|
| schema_version | `source-manifest/1`, the manifest structure version |
| dataset, season | Source family and NFL season |
| source_url | Exact HTTPS download URL; release tags are mutable, so also preserve hashes |
| retrieved_at | Time this app completed retrieval, aware UTC |
| source_published_at | Source publication time only when specifically known; otherwise null |
| source_updated_at | File/asset update time if supplied; not historical publication evidence |
| available_at, availability_evidence | Earliest supported availability for this artifact version and why; default null; requires evidence and must not exceed retrieval time |
| sha256, checksum_scope, byte_count | Digest and count of exact downloaded bytes; explicitly distinguish full artifact from sampled prefix |
| source_schema_version | Versioned field mapping or fingerprint of ordered source columns |
| coverage | sample_only, partial_season, or season_validated; prefix hashes only allow sample_only |
| attribution_url, redistribution_status | Source credit reference and attribution_required/review_required decision; absence of a license never means unrestricted |

GitHub release `published_at` may be years older than a replaced annual asset.
Audit reports keep `release_published_at` and `asset_updated_at` separately and
leave source_published_at/available_at null. Never populate them by copying retrieval.
Full ingestion must compute its own complete checksum; a prefix digest is not one.

## Evaluation eligibility

- Strict as-of: only inputs whose availability and revisions are supported before
  cutoff. Prospective local snapshots prove observation from the observation time
  forward, never before it.
- Approximate historical: corrected historical box scores/PBP and latest season or
  weekly rosters lack preserved original release histories. Lag by completed games,
  but label results approximate where source version timing cannot be established.
- Historical injury rows without trustworthy pregame publication evidence are
  excluded from strict injury-aware evaluation, including rows with date_modified
  unless that field's semantics and complete revision history are verified.
- No-injury baseline remains valid scope when injury context is unknown, with
  input missingness made visible. Unavailable data is never silently synthesized.
