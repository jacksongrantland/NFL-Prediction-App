# Read API and local dashboard

Start `nfl serve` and `npm.cmd --prefix frontend run dev`, then open
http://127.0.0.1:5173. NFL_DATA_DIR optionally selects a local data root. The API
opens SQLite in read-only URI mode and reads immutable Parquet snapshots. Request
handlers never migrate databases, train models or download sources. No mutation
routes exist in this stage. Missing data returns an empty page; missing forecast
IDs return 404. Query validation bounds page sizes and filters.

Endpoints: GET /api/games (season/week/team/offset/limit), /api/games/{id},
/api/games/{id}/versions (paginated), /api/forecasts/{id},
/api/forecasts/{id}/players (team/position/offset/limit),
/api/forecasts/{id}/teams, /api/freshness and /api/evaluation. OpenAPI exposes
response contracts. Forecast details retain input cutoff, generation time, kickoff,
model versions, simulation config, sources, freshness, uncertainty and support.
The game audit pairs each scored official forecast with exact actual revision IDs.

The responsive dashboard includes the league schedule, Cowboys/team and week
filters, game details, player intervals, conditional/unconditional toggle, saved
versions/model audit, score comparison chart and revision error table. Names use
exact GSIS roster identity; missing identity displays its ID, never a guessed name.
Unknown availability and unresolved depth roles remain visible. Source observation
does not prove healthy availability. Last-refresh/cutoff age is shown and gets a
stale label after 36 hours. Other-player totals remain aggregate, not fictitious
named players. Individual fumbles, kicking, defense, unsupported roles/preseason
are not presented as supported projections.

Score intervals are empirical 10th-90th percentiles (nominal 80%), not guarantees.
Active-on-offense conditional statistics use only participating simulation draws;
unconditional statistics include nonparticipation zeros. The participation baseline
is not a learned injury probability. Mean and marginal median interpretations differ.

Measured historical accuracy/log loss/error, selected participation coverage and the
small simulation validation/calibration check are displayed separately from official
published pregame history. No synthetic demo is displayed as real history. Until an
eligible locked forecast has an actual, its performance view is explicitly empty.

October 21 verification used real week 7 (14 games), Cowboys at Eagles (55 player/
other rows), two saved versions, a completed Cowboys game with actuals and missing
forecast, conditional/QB filters and a 390px mobile viewport (then reset). No browser
console errors occurred. API tests cover filters, pagination, version identity,
missing data/404/422 and refusal of HTTP writes; an absent database is not created
by reads. 84 tests and frontend strict type checking/build passed. See
 dashboard_verification_2026-10-21.json for dated evidence.
