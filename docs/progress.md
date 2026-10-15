# Progress

## Prompt 01 — Bootstrap and architecture

Completed October 14, 2026. Awaiting user review and commit. Do not start Prompt 02
until the user resumes work.

Created a new local Git repository in `nfl-prediction-app`, separate from the parent
planning file. No commit, remote, push, publication, or scheduled task was created.

Implemented an editable Python package, `nfl` CLI, environment settings with loopback
validation, and a typed FastAPI health endpoint. Created a React/TypeScript/Vite
connection dashboard with loading, failure, retry, and success states. Added Python
lint/format configuration, strict frontend type checks, backend smoke tests,
PowerShell helpers, ignore rules, architecture, contracts, and setup instructions.

### Versions verified

| Tool / primary dependency | Version |
|---|---|
| Git | 2.55.0.windows.3 |
| Python | 3.13.2 |
| uv | 0.13.1 |
| Node.js | 24.14.1 |
| npm | 11.11.0 |
| FastAPI | 0.143.1 |
| Uvicorn | 0.54.0 |
| Pydantic | 2.14.1 |
| pydantic-settings | 2.16.0 |
| Typer | 0.27.3 |
| pytest | 9.1.1 |
| HTTPX | 0.28.1 |
| Ruff | 0.17.0 |
| React / React DOM | 19.3.1 |
| TypeScript | 7.0.2 |
| Vite | 8.3.4 |
| Vite React plugin | 6.1.2 |

Installed stable package-manager releases, not prereleases. Node meets Vite's
reported engine requirement (`^20.19.0 || >=22.12.0`). Python dependencies resolved
and execute on Python 3.13.2. Full transitive versions are recorded in `uv.lock`
and `frontend/package-lock.json`; npm direct versions are exact. Python is currently
restricted to 3.13 to match the verified environment.

### Verification results

Commands run from repository root unless indicated:

- `py -3.13 -m uv sync`: resolved/installed 32 packages and created `uv.lock`.
- Frontend `npm.cmd install --save-exact react react-dom`, then
  `npm.cmd install --save-dev --save-exact typescript vite @vitejs/plugin-react @types/react @types/react-dom @types/node`:
  installed successfully; npm reported zero vulnerabilities.
- `.\.venv\Scripts\ruff.exe check .`: passed.
- `.\.venv\Scripts\ruff.exe format --check .`: all 10 Python files formatted.
- `.\.venv\Scripts\python.exe -m pytest`: 2 passed, no warnings. Tests cover the
  health response contract and rejection of public network binding.
- `.\.venv\Scripts\nfl.exe version`: `0.1.0`.
- `npm.cmd --prefix frontend run build`: strict TypeScript checks and Vite production
  build passed. Added Vite client types after the initial CSS-import type check failed.
- Live process smoke check: launched `nfl serve` and Vite with Node, requested
  `http://127.0.0.1:8000/api/health`, `http://127.0.0.1:5173/`, and
  `http://127.0.0.1:5173/api/health`. All returned HTTP 200; direct and proxied health
  bodies reported `status: ok`. Processes were stopped afterward.

### Limitations and local observations

- PowerShell execution policy blocks `.ps1` helpers. System policy was not changed;
  the README provides equivalent direct commands that were verified.
- Standalone `uv` is not on PATH; use `py -3.13 -m uv`.
- Browser rendering was not visually inspected. The build and real HTTP/proxy path
  were verified; manual UI review remains useful.
- No data coverage, source licensing, prediction quality, or model performance has
  been verified. No data/model/storage dependencies have been installed prematurely.
- No chart library is needed for the connection-only screen. Add one at dashboard stage.

### Next unfinished stage

Prompt 02: audit free NFL data and define actual source contracts and availability
matrix. Probe small real artifacts and document attribution, timestamps, and gaps.

Suggested commit: `chore: bootstrap local NFL prediction app and architecture`
