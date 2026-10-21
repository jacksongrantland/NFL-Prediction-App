# Offensive player models - Prompt 07

Completed October 21, 2026 as an evaluated local baseline stage. Prospective
accuracy is unproven; previews remain `recommended_for_decisions=false`.

## Commands

```powershell
.\.venv\Scripts\nfl.exe audit-participation
.\.venv\Scripts\nfl.exe models select-offense FEATURES PARTICIPATION --output artifacts/player-defaults-verified
.\.venv\Scripts\nfl.exe models preview-players PLAYER_MODEL GAME_ID
```

Use emitted directories/IDs. Data and full model artifacts remain ignored. Source
attribution and PFR/Sports Reference redistribution review in data_sources.md apply.

## Coverage and labels

Exact historical PFR-to-GSIS roster crosswalks establish snap identity; names never
establish identity. Missing/ambiguous mappings remain unresolved. An absent player
gets zero offensive participation only if conservative team-game denominator,
percentage and positive-box-score checks pass. Otherwise participation is unknown.
A zero offensive-snap row does not establish game inactivity. Positive snaps with
missing actual statistics remain missing and are excluded from target evaluation.
Snap/stat contradictions are excluded rather than silently scored as zeros.

The initial audit has 41,822 known and 48,075 unknown participation labels among
89,897 feature rows. Only 25/568 2022 team-games passed the conservative checks,
versus 512/570 in 2025. These are selected-coverage results, not full-roster accuracy.

## Forecast definitions

Supported QB/RB/WR/TE targets: attempts, completions, passing yards/TD/interceptions,
carries, rushing yards/TD, targets, receptions, receiving yards/TD. Fumbles, kicking,
defense and other positions remain unsupported individual targets.

Participation uses only earlier known offensive-participation labels: last 16,
shrunk by four toward earlier position participation. It is not an injury-health
or official-active probability. No prior participation history means unsupported.
Sparse personal workload uses documented position shrinkage. Unknown availability
stays visible. Questionable has no invented coefficient. Confirmed Out/inactive
sets unconditional participation to zero and redistributes workload. Active versus
no-participation scenarios are explicit and carry no claimed injury probability.

Team historical volume is forecast before allocating player workload. Conditional
production per opportunity is separated from participation-weighted unconditional
production. Signed yardage remains valid. Other-player work preserves omitted roles.
The lag-reference candidate floors team volume at the pregame roster lag-workload
sum; mixed defaults share the same explicit budget. This preserves the stronger
simple forecast but can inflate team volume when competing depth roles are unknown.
This reconciliation is exposed in output, not interpreted as a verified depth chart.
Backups have no guaranteed starter promotion, including when a teammate is Out.

## Selection, intervals and residuals

Candidates: lag reference, capped lag workload, normalized opportunity allocation,
and capped lag with opponent context. The latter uses earlier opponent-conceded
team opportunities, requires four games, shrinks toward league volume and bounds
the adjustment to 0.75-1.25. It asserts no learned individual matchup/injury effect.

Selection minimizes absolute error divided by training-only per-stat mean absolute
actual (floor one), pooled within position. Each expanding validation fold selects
using earlier folds only; the first uses the lag reference. Final defaults use
2021-2024 validation. All four positions retained the simpler lag reference.
No learned player-production challenger was needed to replace a stronger baseline.

Training-only empirical residual intervals report nominal 80% coverage, MAE, bias
and sample count by position/stat and pregame workload bucket. Keyed nested OOF
predictions/residuals are saved for simulation. These marginal intervals do not form
joint valid football draws. The observed 2025 experiment remains frozen; new defaults
are not rescored on it. New model prospective evaluation eligibility is 2026 onward.

## Evidence

The initial normalized opportunity experiment underperformed its lag comparator:
2025 QB passing-yard MAE 122.864 versus 73.169, RB rushing 21.103 versus 20.116,
WR receiving 22.047 versus 21.677, TE receiving 15.886 versus 15.394. It was never
promoted. See offense_baseline_verification_2026-10-15.json.

The October 21 capped/opponent comparison also failed to replace the simpler
reference; see offense_allocation_comparison_2026-10-21.json. Final nested 2021-2024
reference MAEs: QB passing 70.553 (n=2,625), RB rushing 20.669 (n=6,390), WR receiving
23.251 (n=9,522), TE receiving 16.599 (n=4,572). These match the comparator and are
approximate historical results, not a claim of improved or prospective accuracy.
See offense_default_verification_2026-10-21.json. Full workload reports and residuals
remain in the checksummed local artifact. There are 4,765 2026 projection rows.
