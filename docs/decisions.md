# Architecture decisions

Recorded October 21, 2026 for the local checkpoint.

1. **Local CPU and free sources.** Python/FastAPI plus React/TypeScript/Vite keep
   setup approachable. No GPU, cloud deployment, paid feed, league login or payment
   integration is introduced. Feature expansion is gated by source/role evidence.
2. **Separate immutable analytics from operational state.** Raw/Parquet artifacts
   preserve hashes and revisions; SQLite/WAL owns pointers, observations, locks and
   ledger state. DuckDB reads analytical files without a competing writable store.
3. **Knowledge times are not invented.** Retrieval/observation/recording times stay
   separate from original publication. Corrected historical training is approximate;
   prospective snapshots prove local knowledge only from their actual recording.
4. **Baseline evidence beats model novelty.** Earlier validation retained the
   regularized game model, lagged player reference and simple team baselines where
   challengers failed. The observed holdout is frozen. No injury/depth coefficient
   is invented to hide incomplete coverage or poor results.
5. **Joint box-score consistency before realism.** Team environment/opportunities
   precede player allocations. Per-draw football identities are enforced; unknown
   roles retain an aggregate bucket. This is not full play-by-play/overtime realism.
   Expanded team targets have independent evidence and do not imply full DST fantasy.
6. **Immutable pregame identity.** Generation comes from the writer, cutoffs are UTC,
   late jobs cannot create pregame history, and reschedules never silently unlock.
   A rescheduled locked version remains auditable but is excluded from scoring/new
   lineup comparison. Missing eligible forecasts stay missing.
7. **Visible numerical fantasy scope.** Joint unrounded offensive subtotals and exact
   assignment under kickoff locks are useful without pretending unsupported fumble,
   two-point, individual kicker/defense or role inputs exist. Risk objectives are
   explicit arithmetic, never LLM-generated persuasion.
8. **Virtual credit conservation.** Decimal odds and integer minor units prevent
   float balance drift. Stakes debit once; corrections append compensating events.
   Correction debt is visible and blocks spending. No real-money path exists.
9. **Single-user loopback access.** Trusted Host checks, local-client/origin/header
   rules, bounded JSON and no remote CORS grant are the current boundary. They are
   not a substitute for authentication, HTTPS and access control in a hosted app.
10. **Measured, reproducible checks.** Locks, generated legal fixtures, end-to-end
    tests, pinned formatter/action versions and clean dependency environments support
    reproduction. CI is defined but has not run remotely. Raw data/models/secrets stay
    out of Git. Source attribution/redistribution review remains necessary before
    any future publication, along with backups, job service and concurrency review.
