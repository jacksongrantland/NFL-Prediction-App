# NFL Prediction App

Local Windows NFL prediction project, currently at Prompt 01 (bootstrap).
The dashboard displays API connection health. No sports data or predictions are
present yet. Follow the numbered roadmap one stage at a time.

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

The user reviews and commits each stage. Nothing is automatically committed,
pushed, published, or scheduled.
