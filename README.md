# NFL Prediction App

Local Windows NFL prediction project, currently through Prompt 06 (evaluated game models).
The dashboard displays API connection health. Real 2020–2026 data can be downloaded
and validated with the CLI; the dashboard does not display it yet. Evaluated game
models and unpublished scheduled-game previews exist. Player projections and
official locked prediction history are not implemented yet.

Pregame schedule/roster/injury observations:

```powershell
.\.venv\Scripts\nfl.exe capture-pregame --season 2026
.\.venv\Scripts\nfl.exe pregame-as-of 2026_06_ARI_LA --season 2026 --cutoff "2026-10-15T17:00:00Z"
```

Choose a cutoff after your own capture; earlier queries correctly show missing
data. See [snapshot commands, manual CSV and timestamp policy](docs/pregame_snapshots.md).
No injury probability model exists yet. Feature preparation:

```powershell
.\.venv\Scripts\nfl.exe build-features --smoke --output artifacts/features-smoke
.\.venv\Scripts\nfl.exe build-features --output artifacts/features-full
.\.venv\Scripts\nfl.exe check-backtest artifacts/features-full/FEATURE_ID
```

Use the emitted FEATURE_ID directory. See [feature policies](docs/modeling.md) and
[chronological evaluation](docs/evaluation.md). Historical inputs are explicitly
approximate; the latest completed season is reserved for final model evaluation.

See [game model commands and limitations](docs/game_models.md) and
[measured validation/test results](docs/game_model_verification_2026-10-15.json).
The selected regularized model's 2025 holdout: 285 games, 61.4% three-way accuracy,
0.663 log loss, 10.17-point margin MAE. These are approximate historical results,
not published pregame performance or evidence of a betting advantage.

Source discovery is available through:

```powershell
.\.venv\Scripts\nfl.exe audit-sources --current-season 2026
```

It checks 2020–2026 release metadata and bounded samples, writing ignored
`data/audits/source_audit.json`. See [source coverage and known gaps](docs/data_sources.md).
The dated audit detects two injury timestamp schema gaps and exits 1; these are
documented source limitations. This command does not ingest datasets or train models.

Historical ingestion and local analytical checks:

```powershell
.\.venv\Scripts\nfl.exe ingest --season 2025 --current-season 2026
.\.venv\Scripts\nfl.exe ingest --current-season 2026
.\.venv\Scripts\nfl.exe data-counts 2026
```

The first command is a one-season smoke run; the second selects 2020–2026. Data
stays under ignored `data/`. Repeat runs reuse unchanged snapshots; use
`--force-refresh` to re-fetch historical sources without discarding prior versions.
See [operations and recovery](docs/operations.md) and the progress log for real
counts, measured runtimes, storage use, and known missing-ID rows. Injuries and
snap counts are not part of this ingestion stage.

## Setup

Requirements: Git, Python 3.13, uv, Node.js 24, and npm. Exact resolved package
versions are in `uv.lock` and `frontend/package-lock.json`. Commands below run
from this repository's root in PowerShell. The current machine runs uv through
Python because the standalone uv command is not on PATH.

```powershell
py -3.13 -m uv sync --locked
npm.cmd --prefix frontend ci
Copy-Item .env.example .env
```

Copy `.env.example` only if you do not already have `.env`. Settings are optional;
defaults work without this file. Do not commit `.env` or credentials.

## Run

In one terminal:

```powershell
.\.venv\Scripts\nfl.exe serve
```

In a second terminal:

```powershell
npm.cmd --prefix frontend run dev
```

Open http://127.0.0.1:5173. The connection card should show Connected. Health is
available at http://127.0.0.1:8000/api/health and API docs at
http://127.0.0.1:8000/docs. Stop each process with Ctrl+C.

Optional PowerShell helpers: `./scripts/backend.ps1` and `./scripts/frontend.ps1`.
Direct commands above also work when local script execution policy blocks helpers.
Never bind the API to a public network interface. Vite proxies to port 8000; update
its configuration if you deliberately change NFL_PORT.

## Verify

```powershell
.\.venv\Scripts\ruff.exe check .
.\.venv\Scripts\ruff.exe format --check .
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\nfl.exe version
npm.cmd --prefix frontend run build
```

`./scripts/check.ps1` runs lint, formatting, tests, and frontend type checks/build.
TypeScript strict checking supplies the initial frontend static check; a separate
JavaScript lint configuration is deferred until component complexity needs it.
To preview the built frontend, keep the backend running and use
`npm.cmd --prefix frontend run preview`.

See [architecture](docs/architecture.md), [contracts](docs/data_contracts.md),
and [progress](docs/progress.md). Dependencies for data/model stages will be added
when needed. No Docker, CUDA, database server, paid feeds, or hosting are required.

The user authorized local commits after verified prompt checkpoints. Changes are
never pushed, published, or scheduled automatically.
