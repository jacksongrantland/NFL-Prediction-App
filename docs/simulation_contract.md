# Joint simulation consistency contract (simulation/1)

Each seeded draw has one shared multiplicative game environment. Team volumes
are sampled before player allocations. Offensive participation is sampled once
per player per draw from the explicitly empirical baseline; confirmed Out is zero.
Unknown probabilities and unallocated roles go to `other`. Allocations use
conditional workload, never an independent draw of every marginal statistic.

Every team draw enforces integer nonnegative attempts, targets <= attempts,
completions = receptions <= targets, passing yards = receiving yards, passing TDs
= receiving TDs <= receptions, and rushing TDs <= carries. A quarterback bucket
owns passing outcomes; receiving outcomes are allocated to eligible receivers.
Other QB/receiver/rusher buckets retain omitted contributions. Yardage can be
negative. Net passing = gross passing minus sack yards; sacks allowed by one
team equal defensive sacks by its opponent. Interceptions cannot exceed incomplete
attempts. Fumbles/lost fumbles are aggregate approximations, not player targets.

Scores equal 6*(passing+rushing+defense/ST TD) + extra points + 2*successful two
point tries + 3*field goals + 2*safeties. Miscellaneous scoring lives in aggregate
buckets. Defensive/ST TDs, safeties and two point plays use documented fixed
scenario rates, not learned player estimates. Field goals and extra points are
aggregate scoring components, not evaluated kicker projections. Overtime is a
single additional scoring opportunity when regulation ties; postseason ties are
resolved by a field goal. This is a bounded box-score approximation with no
possessions, clock, field position or full overtime rules.

Game-model expected scores set the offensive touchdown environment after an
explicit allowance for aggregate kicking and miscellaneous scores. The resulting
sample means can differ from the raw model. Report both; derive win/tie
probabilities and all player summaries from these same draws. Never add marginal
medians to reconcile totals. Quantiles are empirical draw quantiles. Their observed
coverage and win probability calibration must be evaluated on earlier validation
samples separately from the untouched/frozen 2025 test. Simulation output remains
experimental and unsupported for decisions while prospective calibration is absent.

Seed/config, inputs/model identifiers and accounting version accompany outputs.
Simulation count is bounded 100–5000. Individual draws are retained locally for
scoring and invariant checks. No independent fantasy samples are permitted.


## Implementation and measured verification - October 21, 2026

`nfl models simulate-week GAME_MODEL PLAYER_MODEL FEATURES SEASON WEEK --count 500`
creates ignored checksummed samples and summaries; `--validation` uses earlier OOF
rows only and rejects seasons outside those rows. It never publishes live history.
Input hashes and feature definitions are verified. A validator rejects accounting
violations before atomic artifact-directory publication.

The shared environment is mean-one lognormal (log standard deviation 0.15).
Opportunities are Poisson, receptions use the projected aggregate catch rate,
receiver/rusher counts are multinomial, and one passer is sampled per team/draw.
Signed aggregate yards use player rates with fixed scenario standard deviations
8*sqrt(receptions) and 4*sqrt(carries). These variances are assumptions, not trained
residual parameters. Passing outcomes are the exact receiving sums.

Scoring uses an offensive TD budget max(0.05, (raw expected score-6-0.7)/7), divided
by a reference catch/rush TD opportunity count. TD probabilities are bounded at
0.5. Fixed scenario rates: defensive/ST TD Poisson mean 0.1, field goals Poisson
mean 2, safety probability 0.015, two-point attempt probability 0.03 per TD,
two-point success 0.48, extra-point success 0.95, sack mean 0.065*attempts, mean
sack yards 7/sack, interception probability 0.06 per incomplete attempt, fumbles
0.015 per carry/reception/sack and half lost. The environment also affects
opportunities and miscellaneous scoring. These constants describe an approximation;
none is advertised as a learned/evaluated individual kicking/defensive forecast.

At a regulation tie, a single field goal resolves 90% of regular-season samples
and every postseason sample. This is an explicit overtime approximation. Lost
fumbles do not independently create a second defensive TD; defensive/ST scoring
is the separate aggregate bucket. Two-point statistics remain aggregate and are
unsupported for individual fantasy bonuses. Sacks allowed and defensive sacks are
separate fields with cross-team equality.

Real 2024 week 1: all 16 games, 500 draws/game, 99.915 seconds including IO and
summaries. All 8,000 draws passed accounting validation. Three-outcome Brier 0.421717,
log loss 0.608410, margin MAE 8.4085, nominal 80% score coverage 90.625% across
32 team outcomes. Per-position/stat player MAE/bias/coverage and reliability bins
are in simulation_verification_2026-10-21.json. This small selected validation week
cannot establish calibrated season-long probabilities. QB yardage intervals were
especially broad (100% coverage on 39 eligible rows). Do not advertise these as
calibrated or decision-ready. No 2025 holdout evaluation or parameter fitting used
these results. Historical timing/participation limitations still apply.

Known limitation: uncertain lag-reference depth roles can inflate team opportunities.
The shared scoring environment reconciles touchdowns toward game expected scores;
yardage/attempt means may differ substantially from raw individual estimates.
Both raw and simulated score means are reported. Future work should evaluate
richer role information and learned joint dispersion on prospective eligible data.
