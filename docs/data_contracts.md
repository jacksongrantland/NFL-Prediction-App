# Initial contracts

These conventions are binding defaults, not a claim that source mappings have
been audited. Prompt 02 will define actual raw and normalized schemas.

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
