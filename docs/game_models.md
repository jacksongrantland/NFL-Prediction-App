# Game baselines and local registry

Use an existing content-addressed feature directory from Prompt 05:

```powershell
.\.venv\Scripts\nfl.exe models train-games artifacts/features-optimized/FEATURE_ID
.\.venv\Scripts\nfl.exe models evaluate-games artifacts/models/MODEL_ID
.\.venv\Scripts\nfl.exe models promote-games artifacts/models/MODEL_ID
.\.venv\Scripts\nfl.exe models preview-games artifacts/models/MODEL_ID artifacts/features-optimized/FEATURE_ID
```

Training and evaluation are explicit CPU operations, never HTTP request work.
Preview creates no published pregame forecast and does not retrain. Only trusted
locally generated model.joblib files should be loaded; model persistence is not
an exchange format for untrusted downloads.

Candidates are league/home-field and recency/shrinkage rolling baselines, logistic
win plus multioutput ridge score models, and a bounded scikit-learn histogram
boosting challenger (60 iterations, seven leaf nodes, L2 10, fixed seed 2026).
There is no hyperparameter search. Every preprocessing pipeline fits on its
training fold. Models are evaluated on complete earlier-season validation folds;
the simplest model within 0.005 log loss of the best wins. Log loss is the primary
predeclared selection measure; score/margin error is also reported. Selection
does not use final-test results. Baseline candidates are retained even if learned
models fail to improve probability quality.

Regular-season ties form a distinct third outcome, never a binary loss or win.
The model estimates a home-win probability conditional on a decisive result,
then allocates a smoothed training regular-season tie rate ((ties + 0.5) /
(regular games + 100)). Playoff tie probability is zero. This rare-event prior
is explicit and not a learned overtime simulator. Score estimates are nonnegative
fractional expectations, not valid simulated football scores. They need not imply
the same winner as the win classifier; joint reconciliation arrives in Prompt 08.

Reports contain multiclass log loss, multiclass Brier (sum across three classes),
three-way accuracy, score/margin MAE and RMSE, counts/ties and home-win reliability
bins. No calibration is fitted against test data; reliability is measured on
earlier held-out folds. The final season is evaluated only after selection. Its
saved result is reused by repeat evaluation commands. Do not retune the model
after reading this final test; a new tuning exercise requires a new holdout.
Margin-MAE uncertainty uses 500 seeded whole-week bootstrap draws. These bounds
measure sampling variability, not future score prediction intervals.

The registry manifest links model/validation/residual checksums, data snapshot
IDs, feature definitions/hashes, dependency versions, training eligibility cutoff,
seed, hyperparameters, validation metrics and explicit promotion status. Initial
status is candidate. Local promotion requires recording the selected model's final
evaluation and does not itself publish predictions. Test results are immutable
per model artifact; a new data/config model must not become an excuse to repeatedly
tune against the same final season.

All evaluation is approximate corrected-source historical analysis. Source timing,
kickoff-plus-12-hour completion approximation, home designation at neutral venues,
rare ties and limited model scope remain limitations. No claim of market advantage
or injury-adjusted accuracy is supported. Real measured results are in progress.md.

## Current local registry note - October 21, 2026

The evaluated selected game artifact was explicitly promoted locally for refresh
inference. Its original dated verification JSON intentionally retains its original
candidate status; that historical evidence is not rewritten. Refresh uses the
promoted registry manifest, never retrains per request, and later reproduction
training writes a separate unevaluated candidate without rescoring the holdout.
