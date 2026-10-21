# Forecast history and actual revisions

`nfl forecasts publish PAYLOAD.json` records local pregame history, not an external
publication. Generation time comes from the writer. Required payload fields:
game_id, cutoff, kickoff_at, source_snapshots, input_freshness, model_versions,
simulation_seed, simulation_config, supported_outputs and summary. The summary
uses joint sample results; input/model metadata is preserved verbatim for audit.
Do not import untrusted files or mislabel synthetic/retrospective data as live.

Input cutoff cannot exceed generation time or kickoff. Live publication at/after
kickoff, after locking, or after a prior kickoff crossed without a timely reschedule
is rejected. A caller-supplied generated_at is rejected. Retrospective imports use
`--retrospective`, receive the actual import generation time, never become eligible
for official pregame locks and do not mutate the live schedule observation history.

`nfl forecasts lock GAME_ID --minutes-before 5` uses the latest eligible version
created by the configured pregame deadline. A late-running job can select an actual
previously saved eligible forecast; it cannot substitute a late version. If none
exists, the immutable lock records `no_eligible_forecast`. Duplicate lock jobs return
the same lock. Versions, locks, schedule observations and results have SQLite
UPDATE/DELETE rejection triggers. Publication and lock selection serialize writes.

Each changed kickoff is an append-only schedule observation. A postponement observed
before the previous kickoff can use a new forecast with the revised kickoff. Old
kickoff forecasts do not silently transfer to that new schedule. A schedule change
observed after a previous kickoff cannot reopen that game. Already locked games
never unlock automatically; this deliberately favors auditability over reclaiming
an earlier locked forecast after a postponement. All times require explicit UTC or
an offset and are stored in UTC; America/Chicago is display only.

`nfl forecasts result GAME_ID ACTUAL.json SOURCE_REVISION --status provisional`
appends an actual revision; `settled` and `cancelled` are also supported. Duplicate
identical revisions are idempotent. Corrections append rather than overwrite.
`nfl forecasts reconcile 2026` imports completed canonical normalized game/player
actuals using source snapshot IDs as revisions; unknown/missing stats remain null.
This is source-based finality, not proof that no future official correction exists.

`nfl forecasts audit GAME_ID` shows every version, schedule observation, immutable
lock, result revision and exact forecast/result pairs used for game/player errors.
Missing player actuals are not zero-filled. Cancelled revisions are not scored.
Published-history errors remain separate from approximate historical backtests.
No official prediction is invented for any preexisting completed game.

Verification on October 21, 2026: fake-clock tests cover late/duplicate jobs,
postponement before/after kickoff, missing forecasts, offset/naive times, backdating,
immutable rows, retrospective exclusion and corrected results. Real local
reconciliation imported 79 completed 2026 games with snapshot
1134a20ea6995acbc3de659dffbd07e0deb1558b022dc478f320a939c1512b7d.
