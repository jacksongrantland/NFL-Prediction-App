# Resume evidence and suggested wording

Use only claims supported by the local repository and dated verification files.
The application is a local research checkpoint, not a deployed production service,
profitable betting system or proven prospective player model. CI is defined and
its checks ran locally. The new workflow was not pushed or run remotely; existing
origin configuration was preserved, and no remote or deployment was created.

Possible bullets (adapt to the role and space available):

- Built a Python/FastAPI and React/TypeScript NFL research app with versioned
  2020-2026 snapshots, full-league filters and local forecast/actual audit history.
- Implemented chronological validation and CPU model comparisons; the selected
  game model recorded 61.4% three-way accuracy on 285 approximate historical 2025 games.
- Enforced joint football accounting, immutable pregame locks and corrected-result
  audit trails; tested delayed jobs, postponements, missing data and cutoff boundaries.
- Added exact fantasy slot/FLEX assignment from joint samples and a paper-only
  integer-credit ledger with duplicate prevention and compensating corrections.
- Added 100+ generated-fixture tests, a synthetic end-to-end smoke and a pinned
  Windows/Linux CI definition; verified clean locked dependency installs locally.

Optional measured detail: cold dependency setup with existing runtimes took 11.28s
(Python) and 3.17s (frontend); a recorded 14-game/100-draw cached-source refresh took
42.51-62.22s. Training/selection was 0.835s excluding interpreter imports. See
release_measurements_2026-10-21.json for scope, peak memory, environment and variability.

The game result is an approximate corrected-source backtest, not genuinely published
pregame performance. Player defaults retained the simpler baseline after worse
alternatives. Participation/role coverage is incomplete, expanded simulation did
not improve the small-week win calibration check, and individual defenders/kickers,
full DST fantasy and preseason remain unsupported. Do not replace these limitations
with claims of full player coverage, production readiness or a betting advantage.
