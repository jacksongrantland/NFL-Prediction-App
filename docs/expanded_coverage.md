# Additional statistics and coverage audit

October 21, 2026: this stage supports **team aggregates** for field-goal attempts/
makes, extra-point attempts/makes, defensive sacks and defensive interceptions.
It does not claim individual kicker/defender/returner roles or complete DST fantasy.

Definitions follow the [nflverse team stats dictionary](https://nflreadr.nflverse.com/articles/dictionary_team_stats.html)
and its [primary stats implementation](https://github.com/nflverse/nflfastR/blob/master/R/calculate_stats.R).
Field goals/PATs are kick counts; defensive sacks are credited defensive sacks,
separate from offensive sacks suffered. Interceptions are defensive takeaways,
separate from interceptions thrown. Raw fields are read from already downloaded,
checksummed team-stat sources, joined through exact normalized source-row numbers.
No new paid source, name matching or rewritten historical snapshots is involved.

Across 2020-2026 active snapshots: 3,572 team-games, zero nulls in the six selected
raw fields; all counts integral/nonnegative and makes no greater than attempts.
Sack-credit/opponent-sacks-suffered disagreements: 3/12/7/11/10/9/4 by year (56 total).
Those defensive sack targets are excluded from evaluation rather than silently
reconciled as actuals. Interceptions reconcile in every audited row. Source IDs,
coverage, null counts and exclusions are in team_component_verification_2026-10-21.json.

## Baselines and fixed evaluation

`nfl models extended-baselines FEATURES` compares earlier league means, lagged team
opportunity/rate baselines and opponent-aware defense. It uses the established
16-game history, five-game half-life and four-observation shrinkage. Kicking first
predicts attempts, then success probability, preserving makes <= attempts. Opponent
defense averages own prior production and prior opponent sacks/interceptions conceded.
First expanding fold uses league; later folds select only using earlier folds.
FG attempt/make and PAT attempt/make pairs choose together. Training-only residual
intervals report MAE/bias/count/80% coverage. No learned role/assignment coefficients
were invented.

Final earlier-validation choices: league field goals, own-team extra points,
opponent-aware sacks/interceptions. First fixed 2025 additional-target test:

| Target | Team-games | MAE | Bias | 80% coverage |
|---|---:|---:|---:|---:|
| FG attempts | 570 | 0.973 | -0.052 | 83.5% |
| FG made | 570 | 1.005 | -0.055 | 74.4% |
| PAT attempts | 570 | 1.145 | 0.009 | 79.5% |
| PAT made | 570 | 1.137 | -0.002 | 80.5% |
| Defensive sacks | 561 | 1.372 | 0.004 | 78.6% |
| Defensive interceptions | 570 | 0.690 | 0.014 | 83.5% |

This is the first test of these new targets, not a rescore/tune of the observed
2025 offensive experiment. The artifact is frozen. Historical timing remains
approximate corrected-source evaluation; no prospective accuracy is claimed.

## Joint integration

Set optional `team_model` in refresh config, or pass `--team-model` to
`models simulate-week`. Refresh reuses the selected baseline definitions with fresh
history, without reselection or holdout evaluation. Simulation/2 samples FG attempts
before makes, uses team PAT success rates, and uses the opposing defensive sack/INT
expectation for offensive sacks/interceptions. Interceptions still cannot exceed
incomplete attempts. Opposing defensive/offensive sack and interception counts match.
OT field goals add an attempt and a make. Scores still reconcile exactly.

Raw PAT volume is reconciled to the joint touchdown/two-point count; it is not an
independent score-changing draw. The offensive TD budget subtracts expected modeled
FG points from raw game expected score before allocation. Both raw component inputs
and simulated summaries are retained. Miscellaneous scores, safeties, fumbles and
full overtime remain the documented approximation, not newly evaluated targets.

Same real 2024 week-1 diagnostic, 16 games/100 draws: 13.829 seconds, Brier 0.469588,
log loss 0.659358, margin MAE 9.237, score coverage 90.625%. Its Brier is worse than
the earlier 100-draw simulation check; do not claim improved win calibration.
Additional team interval diagnostics are in team_simulation_verification_2026-10-21.json.
The small week is not evidence of season-long calibration. A floating-point bin-edge
bug was corrected so every calibration game belongs to exactly one bin; scoring/
sampling was unchanged. Legacy seeded samples were verified identical after loop
optimization. New accounting/property tests cover attempts/makes and defensive links.

Real current-source cached refresh with the optional team model produced 14 new
pregame versions and reconciled 93 games in 42.507 seconds. Prior forecasts and the
pending paper verification entry retain their original immutable samples. Browser
verified Cowboys/Eagles team summaries and new model metadata. The API/dashboard
show team aggregate intervals; individual fantasy eligibility remains QB/RB/WR/TE
supported offensive subtotals. Partial team targets do not imply full DST scoring.

## Remaining unsupported coverage

The audit also counted stat rows by position (including 3,568 K rows and defenders,
returner-capable positions and offensive linemen). Having a row/field does not prove
complete on-field participation, assignments, future role or historical availability.
Individual kicker, defender, returner and other-role projections remain unsupported;
their relevant scoring is still in explicitly aggregate buckets. No name-based role
assignment or fabricated inactive label closes these gaps.

There are zero preseason schedule rows in the active snapshots. A separate
preseason ingestion/model/evaluation path is required; the regular/postseason
simulator explicitly rejects PRE, rather than borrowing regular-season confidence.
No preseason accuracy or full on-field coverage is claimed.

Future coherent additions, only after source/role/evaluation evidence:
`feat(ml): add role-verified individual kicker projections`,
`feat(ml): evaluate defender and returner opportunity baselines`, and
`feat(ml): add separately evaluated preseason forecasts`. These are suggestions,
not implemented or promised supported features. Unsupported coverage does not block
the current offensive app or the evaluated team aggregate additions.
