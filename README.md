# Transcribe3

Transcript validation and enrichment pipeline. Cleans, normalises, and speaker-attributes raw transcripts using a local LLM. Fully local — nothing leaves your machine.

## Requirements

- Python 3.11+
- [uv](https://github.com/astral-sh/uv) — `pip install uv`
- [Ollama](https://ollama.com) — `brew install ollama`
- [ffmpeg](https://ffmpeg.org) — `brew install ffmpeg` (Phase 2+ audio only)
- Node.js 18+ — for the web UI

## Install

```bash
git clone <repository-url>
cd Transcribe3
uv sync --all-extras
cd src/ui && npm install && cd ../..
```

## Running

Three processes, each in its own terminal:

**Terminal 1 — Ollama (LLM backend)**
```bash
ollama serve
```

**Terminal 2 — API server**
```bash
cd /path/to/Transcribe3
uv run uvicorn transcribe3.api.main:app --reload --host 127.0.0.1 --port 8010
```

**Terminal 3 — Web UI**
```bash
cd /path/to/Transcribe3/src/ui
npm run dev
```

Open **http://localhost:3015** in your browser.

> **Registered ports:** Transcribe3 is registered in `~/Projects/app-registry` on
> frontend port `3015` and backend port `8010`. If you temporarily start the API on
> another port, create `src/ui/.env.local` to match:
> ```
> VITE_API_URL=http://localhost:<api-port>
> ```

### LAN mode (trusted local networks only)

The default setup is local-only. To use the UI from another machine on your LAN,
replace `192.168.1.50` below with the LAN address of the machine running
Transcribe3. On macOS, `ipconfig getifaddr en0` usually prints the Wi-Fi address.

```bash
# .env (project root): allow only the browser origin that will access the API
TRANSCRIBE3_CORS_ORIGINS=http://192.168.1.50:3015

# src/ui/.env.local: point browser requests at the LAN-reachable API
VITE_API_URL=http://192.168.1.50:8010
```

Start the API and UI with LAN bindings:

```bash
uv run uvicorn transcribe3.api.main:app --reload --host 0.0.0.0 --port 8010
cd src/ui && npm run dev -- --host 0.0.0.0
```

Open `http://192.168.1.50:3015` from the other machine. Allow inbound TCP ports
3015 and 8010 in the host firewall if prompted. The API has no authentication and
can read, create, modify, export, and delete sessions; do not expose these ports to
the internet or use this mode on an untrusted network.

## CLI

```bash
# Clean a raw transcript
uv run transcribe3 clean transcript.txt

# Specify model and output format
uv run transcribe3 clean transcript.txt --model qwen3.6:27b --format srt

# List sessions
uv run transcribe3 sessions list

# Export a session
uv run transcribe3 export <session-id> --format srt

# Run benchmarks against gold standard
uv run transcribe3 benchmark tests/gold/
```

Run `uv run transcribe3 --help` for all commands and options.

## Configuration

Settings (LLM timeout, default model, confidence threshold, Ollama URL) are managed via the **⚙ Settings** page in the UI, or directly in `sessions/settings.json`. Defaults:

| Setting | Default |
|---|---|
| LLM timeout | 60 s (configurable up to 1800 s) |
| Low-confidence threshold | 0.6 |
| Ollama URL | http://localhost:11434 |

## Audio processing (Phase 2)

The full transcription pipeline — ingestion, transcription/diarization, cleaning,
attribution, review, and export — is documented phase-by-phase in
[ARCHITECTURE.md](docs/ARCHITECTURE.md#data-flow--phases-of-the-transcription-process).

Audio transcription and diarization require a HuggingFace token for pyannote model weights:

```bash
cp .env.example .env
# Add: HF_TOKEN=hf_...
```

See [HuggingFace settings](https://huggingface.co/settings/tokens) for a free token.

## Tests

```bash
uv run pytest                   # all tests
uv run pytest tests/unit/       # unit tests only
uv run pytest --cov=src         # with coverage
```

## Docs

Full documentation in [`docs/`](docs/):

| File | Contents |
|---|---|
| [REQUIREMENTS.md](docs/REQUIREMENTS.md) | Full feature requirements and scope |
| [ARCHITECTURE.md](docs/ARCHITECTURE.md) | Layer boundaries and the full transcription pipeline, phase by phase |
| [ROADMAP.md](docs/ROADMAP.md) | Phased delivery plan and backlog |
| [DECISIONS.md](docs/DECISIONS.md) | Architecture decision records |
| [SETUP.md](docs/SETUP.md) | Detailed setup and configuration |
| [TESTING.md](docs/TESTING.md) | Testing strategy and gold standard |
