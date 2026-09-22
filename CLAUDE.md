# Transcribe3

## Stack
- Python 3.11+ managed with uv
- Package layout: `src/transcribe3/` (src-layout)
- CLI: Typer — entry point `transcribe3`
- API: FastAPI + uvicorn
- Tests: pytest + pytest-cov

## Commands
- Install: `uv sync --all-extras`
- Run tests: `uv run pytest`
- Run CLI: `uv run transcribe3 --help`
- Run API dev server: `uv run uvicorn transcribe3.api.main:app --reload --host 0.0.0.0 --port 8010`
- Run UI dev server: `cd src/ui && npm run dev -- --host 0.0.0.0`
- Open UI: `http://localhost:3015` (local) or `http://<host-ip>:3015` (LAN) — both work simultaneously, no config switch needed
- Registered ports: frontend `3015`, backend `8010`

## How to run
- Start Ollama: `ollama serve`
- Start API: `uv run uvicorn transcribe3.api.main:app --reload --host 0.0.0.0 --port 8010`
- Start UI: `cd src/ui && npm run dev -- --host 0.0.0.0`
- Open: `http://localhost:3015` or `http://<host-ip>:3015`
- Both servers bind to `0.0.0.0`, so local and LAN access work at the same time without switching modes or restarting:
  - The API's CORS allowlist (`TRANSCRIBE3_CORS_ORIGINS` in `.env`) must explicitly list every origin you want to allow — setting it replaces the built-in localhost defaults rather than adding to them, so include `http://localhost:3015,http://127.0.0.1:3015` plus your LAN origin(s) together, comma-separated.
  - The UI (`src/ui/src/api.ts`) auto-detects the API host from `window.location.hostname`, so `src/ui/.env.local`'s `VITE_API_URL` should normally stay unset/commented. Only set it to point the UI at an API host that differs from the page's own host.
  - If the machine's LAN IP changes (DHCP), update it in `.env`'s `TRANSCRIBE3_CORS_ORIGINS`.
  - This API is unauthenticated; trusted LAN only.
- LLM providers that require a bearer token read it from the environment, never from
  `sessions/settings.json` (that file is served verbatim by the unauthenticated
  `/settings` endpoint). Variable name: `TRANSCRIBE3_LLM_API_KEY_<PROVIDER_ID>` — the
  provider id from Settings, uppercased, non-alphanumerics replaced by `_`. Set it in
  `.env` and restart the API server. A provider entry can name a different variable via
  its `api_key_env` field.
- Build UI: `cd src/ui && npm run build`
- Run tests: `uv run pytest`

## Troubleshooting
- "Failed to fetch" in the UI: the app tries to diagnose this automatically (see `src/ui/src/api.ts`) and surfaces whether it looks like a CORS rejection vs. the API being unreachable. Checklist:
  1. Is the API process running and listening? `lsof -iTCP:8010 -sTCP:LISTEN`
  2. Does `TRANSCRIBE3_CORS_ORIGINS` in `.env` include the exact origin shown in the browser's address bar (scheme + host + port)? Remember it replaces the defaults, not adds to them.
  3. Is `VITE_API_URL` in `src/ui/.env.local` stale/pointing at the wrong host? It should normally be unset.
  4. After editing `.env` or `.env.local`, restart the affected dev server — neither hot-reloads env files.

## Optional pipeline stages
- Both are switched in Settings and apply to transcript and audio runs alike:
  `run_cleaning` (rule-based text cleanup, ~1s) and `run_attribution` (one LLM call per
  10-segment window — normally the dominant cost of a long recording).
- With attribution off, segments keep the labels diarization gave them and confidence is
  *unscored*, not 100%: the UI shows "not scored" instead of a percentage.
- Each run records per-stage durations in `session.stage_timings`; the Admin screen shows
  them per run and averaged across recent runs. Sessions from before this shipped show "—".

## Current Phase
MVP (Phase 1) — Scenario 1 only: transcript cleaning + manual speaker ID via UI

## Key Constraints
- Fully local — no cloud API calls in the default pipeline
- Open-weight models only (Whisper, pyannote.audio, Ollama)
- Layer boundaries are strict: core/ has zero framework or I/O imports
- LLM backend is a parameter, never hardcoded — required for benchmarking
