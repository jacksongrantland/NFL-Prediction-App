# Local refresh and catch-up operations

Copy config/refresh.example.json to config/refresh.local.json once, then choose the
emitted local model/participation directories. The example references this machine's
verified checkpoints and uses 100 draws to bound runtime; 500 is supported. Config
includes Chicago daily hour, pregame windows, minimum refresh interval, source
request interval, input age limit, horizon, seed, draw count and kickoff lock offset.
Do not put credentials in this file. It is ignored by Git.

```powershell
.\.venv\Scripts\nfl.exe models promote-games GAME_MODEL
.\.venv\Scripts\nfl.exe refresh
.\.venv\Scripts\nfl.exe refresh --cached-sources
.\.venv\Scripts\nfl.exe refresh --scheduled
.\scripts\refresh.ps1 -Scheduled
```

Game promotion is explicit and requires the recorded evaluation. Player selection
is separate (`models select-offense`). Refresh never trains/reselects models or
re-evaluates the holdout. It reuses frozen baseline definitions with fresh lagged
history, and verifies model/feature schema and source checksums. Cached participation
labels remain coverage-limited; later unobserved games stay unknown. Refreshing snap
coverage is a separate explicit audit, not an invented inactive label.

Each run takes an OS-backed refresh lock, separate from individual ingestion locks.
Writers release locks on process exit; stale lock *files* are harmless. CLI source
fetches use per-host pacing (default at most two requests/second), conditional cache,
three bounded attempts with backoff, byte limits and immutable checksums. No sources
cost money. Existing validated snapshots survive failed/truncated downloads.

Steps: ingest current season; capture prospective schedule/roster/availability;
prepare as-of-now features for future games; infer frozen models; generate joint
samples; publish each eligible immutable game version; lock due games and append
actual revisions. Current observed season rosters may supply future-game candidates;
they are never backfilled into past evaluation games. Partially started weeks retain
past-game weekly cutoffs and use now only for remaining future-game features.
Unknown injuries remain unknown and visible. Fresh observed schedule and roster
are required for publication. At/after kickoff or already locked means skip,
never a fabricated pregame forecast. A changed kickoff requires recomputation.

Runs and failure boundaries are recorded atomically in data/refresh/runs/*.json.
last_success.json updates only after every step succeeds. Each artifact publishes
by an atomic directory rename; each game's forecast publishes in a single SQLite
transaction. A week is not one lock: if a later game fails, earlier immutable game
versions survive and the failed run is recorded. Retrying is safe; locks/results are
idempotent, while a newly generated forecast becomes a new auditable version.

## Optional Windows Task Scheduler (user action only)

No task is created by setup, tests, CLI refresh or this repository. If desired,
open Task Scheduler and create a task manually. Use the current Windows user,
run while logged on, and run every five minutes during the desired NFL period.
Program: powershell.exe. Arguments: `-NoProfile -ExecutionPolicy Bypass -File
"C:\Users\Jacks\OneDrive\NFL\nfl-prediction-app\scripts\refresh.ps1" -Scheduled`.
Start in the repository root. Configure "Do not start a new instance" and
"Run task as soon as possible after a scheduled start is missed". Do not grant
administrator privileges just to run the app. Start manually once and review logs.

`--scheduled` checks the daily Chicago hour and crossings of configured pregame
windows, subject to minimum refresh spacing. Missed/offline/sleeping jobs cannot
fetch sources. On wake-up, maintenance still locks/reconciles cached known games;
a due daily/pregame run fetches new data. Late wake-up never creates eligible
post-kickoff forecasts. DST uses America/Chicago IANA rules, never host-local time.

## Recovery

Inspect the failed step and error in the newest run JSON. Retry after network
recovery. Do not delete published snapshots, history, or blobs to hide integrity
errors; investigate the exact checksum/path. Partial staging artifacts are not
active and may be inspected/quarantined manually. If schema differs, rebuild
features with the supported version or explicitly train/select a compatible model;
refresh refuses publication rather than guessing. Retraining is always separate.
