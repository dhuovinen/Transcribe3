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
- Run API dev server: `uv run uvicorn transcribe3.api.main:app --reload --host 127.0.0.1 --port 8010`
- Run UI dev server: `cd src/ui && npm run dev`
- Run LAN mode: `TRANSCRIBE3_CORS_ORIGINS=http://<host-ip>:3015 uv run uvicorn transcribe3.api.main:app --reload --host 0.0.0.0 --port 8010`, then `cd src/ui && VITE_API_URL=http://<host-ip>:8010 npm run dev -- --host 0.0.0.0`
- Open UI: `http://localhost:3015`
- Registered ports: frontend `3015`, backend `8010`

## How to run
- Start Ollama: `ollama serve`
- Start API: `uv run uvicorn transcribe3.api.main:app --reload --host 127.0.0.1 --port 8010`
- Start UI: `cd src/ui && npm run dev`
- Open: `http://localhost:3015`
- UI API URL: `src/ui/.env.local` should contain `VITE_API_URL=http://localhost:8010` when overriding the default.
- LAN mode: set `TRANSCRIBE3_CORS_ORIGINS=http://<host-ip>:3015` in `.env`, set `VITE_API_URL=http://<host-ip>:8010` in `src/ui/.env.local`, then use the LAN commands above. This API is unauthenticated; trusted LAN only.
- Build UI: `cd src/ui && npm run build`
- Run tests: `uv run pytest`

## Current Phase
MVP (Phase 1) — Scenario 1 only: transcript cleaning + manual speaker ID via UI

## Key Constraints
- Fully local — no cloud API calls in the default pipeline
- Open-weight models only (Whisper, pyannote.audio, Ollama)
- Layer boundaries are strict: core/ has zero framework or I/O imports
- LLM backend is a parameter, never hardcoded — required for benchmarking
