# Offensive baseline experiment — Prompt 07 in progress

This checkpoint adds a participation coverage audit and an evaluated offensive
baseline experiment. It does **not** complete Prompt 07 or promote a production
player model. The opportunity allocation experiment underperforms its lag baseline;
unresolved depth/role context and incomplete identity/participation coverage remain
material. Do not use these previews for lineup or paper-betting recommendations.

```powershell
.\.venv\Scripts\nfl.exe audit-participation
.\.venv\Scripts\nfl.exe models offense-baselines artifacts/features-verified/FEATURE_ID data/participation/PARTICIPATION_ID
.\.venv\Scripts\nfl.exe models preview-players artifacts/players/PLAYER_MODEL_ID 2026_06_ARI_LA
```

Use emitted IDs. Defaults stay under ignored data/ and artifacts/. No source rows
are bundled in Git. Source rights/attribution review from data_sources.md remains
in force, including PFR/Sports Reference restrictions before any redistribution.

## Participation coverage

The direct audited nflverse snap Parquet adapter preserves immutable raw files,
source manifests and historical snapshot lineage. PFR IDs map only through exact
historical weekly-roster PFR/GSIS crosswalks, never names. Ambiguous IDs stay
unmapped. Normalized audit directories publish after complete writes; cache reuse
checks the normalized checksum.

For a team/game, an absent player may be labeled zero offensive participation only
when conservative checks pass: a reconciled final game/team, offensive snap sum
equal to 11 times the maximum player offensive snaps, consistent snap percentages,
mapped positive-snap QB/RB/WR/TE players and matching positive box-score participants.
These are conservative coverage checks, not authoritative proof of complete source
history. Exceptions/identity gaps yield unknown, not zero. A present zero-snap row
can establish zero offensive snaps without establishing game inactivity.

Known positive offensive snaps are distinct from a missing box-score row. Positive
snap rows without actual stats remain missing and are excluded for those target
metrics. Eight discovered snap/stat contradictions were marked unknown before
participation forecasting. These conservative rules leave 48,075 of 89,897 player
feature rows with unknown participation. Source years differ substantially; only
25 of 568 2022 team-games pass all checks, versus 512 of 570 in 2025.

## Experimental forecast definition

The baseline estimates offensive participation from a player's last 16 known
prior labels, shrunk with four observations toward prior position participation.
Only games eligible before the frozen weekly cutoff contribute. This is a
no-injury empirical baseline and does not estimate a questionable player's health
or an official active probability. No history at all yields unsupported output.

Team attempts/carries/targets are forecast from prior team production and league
shrinkage before allocating opportunities. Targets cannot exceed pass attempts.
Player lagged workload supplies share weights. Prior production per opportunity
supplies completion/reception, yardage and touchdown rates. Negative yardage is
permitted. An explicit other-player opportunity bucket retains omitted/unresolved
roles and nonparticipation remainder. Conditional and probability-weighted
unconditional expectations are separate; confirmed Out/inactive inputs set the
unconditional participation probability to zero and redistribute opportunities.
Questionable receives no arbitrary coefficient. Preview also exposes offensive
participation versus no-participation counterfactual scenarios, without asserting
an injury probability.

The source role/roster uncertainties remain explicit. Current role weights can
overallocate to backups and materially underpredict starters. Opponent context is
available in the Prompt 05 features but no validated opponent-conditioned player
adjustment has been implemented. Individual expected statistics do not yet form
joint valid football draws. Fumbles, kicking and defense remain unsupported.

## Evaluation and uncertainty

Earlier expanding folds report MAE, bias, sample count, lag-baseline comparison
and empirical 80% interval coverage by position/stat and low/medium/high prior
workload buckets. Prior workload buckets use pregame expected opportunities,
not actual future workload. Interval residuals fit earlier training rows only;
validation residuals are separately retained for future joint simulation work.
Intervals attached to projection rows are limited to cutoffs after the calibration
training cutoff. Unconditional residuals include known nonparticipation zeros;
unknown participation/actuals are excluded, never silently zero-filled.

The fixed experiment's 2025 result was recorded without parameter changes after
inspection. Example unconditional MAEs: QB passing yards 122.86 (lag baseline
73.17), RB rushing yards 21.10 (lag 20.12), WR receiving yards 22.05 (lag 21.68),
TE receiving yards 15.89 (lag 15.39). Eligible sample counts differ by stat/position.
The sample is incomplete and selected by coverage, so participation Brier 0.0432
on 7,342 eligible rows must not be advertised as full-roster participation quality.
See offense_baseline_verification_2026-10-15.json for dated counts and metrics.

The manifest remains baseline_candidate, and preview explicitly returns
recommended_for_decisions false. No learned player-production challenger was
added to conceal the bad result. The simpler lag comparator remains the reference.

## Remaining Prompt 07 work

Establish a defensible default player forecast from earlier-fold evidence, retain
the simpler baseline where it wins, and resolve/represent depth-role allocation
and sparse coverage before production promotion. Add and validate opponent context
where coverage supports it. Keep the existing 2025 experimental result frozen;
do not repeatedly tune against that final season. Any additional development must
use earlier validation folds and declare new prospective evaluation eligibility
honestly. Complete this stage before starting Prompt 08's joint simulation.
