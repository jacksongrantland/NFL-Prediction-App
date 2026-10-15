# Chronological evaluation

`build-features` produces games.parquet, players.parquet, splits.json and
eligibility.json under a content-derived directory in artifacts/features.

```powershell
.\.venv\Scripts\nfl.exe build-features --smoke --output artifacts/features-smoke
.\.venv\Scripts\nfl.exe build-features --output artifacts/features-full
.\.venv\Scripts\nfl.exe check-backtest artifacts/features-full/FEATURE_ID
```

The smoke run uses the latest four published seasons; the full run uses all
published seasons. Exact timings and row counts belong in the progress log.
`check-backtest` verifies folds and fits imputation/scaling only on training rows;
it does not evaluate a prediction model or inspect final-test metrics.

The latest eligible completed season is reserved for final evaluation (2025 in
the initial 2020–2026 data). Current-season games are excluded from tuning/test.
Earlier seasons supply expanding training windows and complete-season validation
folds, which keep complete season/week groups together. Both teams share a game
row. All player rows inherit their game's partition; no random player-row split
exists. Training labels must be eligible before the first validation cutoff.
Later validation features may use earlier games already completed in that season,
matching weekly operation with a model fitted before the season. They never use
future results. Preprocessing fits within each training fold. Final-test data must
not guide model choice or calibration.

Model accuracy is not established by feature tests. Corrected historical inputs,
unverified original availability and the game-end delay approximation must remain
visible in every model report. No strict historical injury-aware claim is valid
without trusted preserved availability evidence.

Reference: [scikit-learn leakage and preprocessing guidance](https://scikit-learn.org/stable/common_pitfalls.html).
