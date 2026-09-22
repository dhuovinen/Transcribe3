# Transcribe3 — Setup

## Prerequisites

Install the following before setting up the project.

### Python 3.11+

Verify your Python version:

```bash
python3 --version
```

If you need to install or upgrade Python, use [pyenv](https://github.com/pyenv/pyenv) or the official installer from [python.org](https://www.python.org).

### uv (package manager)

```bash
pip install uv
```

Verify:

```bash
uv --version
```

### ffmpeg (audio processing)

```bash
brew install ffmpeg
```

Required for audio file decoding in the Phase 2+ audio pipeline.

### Ollama (local LLM backend)

```bash
brew install ollama
```

Ollama serves the LLM used for transcript cleaning and speaker attribution. Pull any model you want to use before starting — for example:

```bash
ollama pull <model-name>
```

Any Ollama-compatible model can be used. The active model is selected in the **Settings** page of the UI or via `--model` on the CLI. Available models are populated automatically from your local Ollama installation.

Start the Ollama server before running the pipeline:

```bash
ollama serve
```

---

## Model cache

Downloaded models are stored in the HuggingFace hub cache directory:

```
~/.cache/huggingface/hub/
```

Models are downloaded automatically on first use and reused on all subsequent runs. On this machine the following are already present:

| Directory | Model | Used by |
|---|---|---|
| `models--pyannote--speaker-diarization-3.1` | Speaker diarization pipeline | pyannote.audio |
| `models--pyannote--speaker-diarization-community-1` | Community diarization pipeline | pyannote.audio (dependency) |
| `models--pyannote--segmentation-3.0` | Audio segmentation | pyannote.audio (internal) |
| `models--pyannote--wespeaker-voxceleb-resnet34-LM` | Speaker embedding | pyannote.audio (internal) |
| `models--Systran--faster-whisper-base` | Whisper `base` transcription weights | WhisperX |

To use a larger Whisper model (e.g. `small`, `medium`, `large-v2`), select it in the Upload form or pass `--whisper-model` on the CLI — it downloads on first use.

To clear the cache and force a re-download:

```bash
rm -rf ~/.cache/huggingface/hub/models--pyannote--*
rm -rf ~/.cache/huggingface/hub/models--Systran--*
```

---

## Install

```bash
git clone <repository-url>
cd Transcribe3
uv sync --all-extras
```

`uv sync --all-extras` installs all dependencies including optional extras (e.g., the Claude API backend for benchmarking comparisons).

---

## Environment Configuration

Copy the example environment file if one is present:

```bash
cp .env.example .env
```

No secrets are required for the default local setup. The `.env` file is only needed if you opt into the optional Claude API backend for benchmarking.

Never commit `.env` to version control.

---

## Run the CLI

```bash
uv run transcribe3 --help
```

Key commands:

```bash
# Clean a raw transcript file
uv run transcribe3 clean <transcript_file> [options]

# Transcribe an audio file (Phase 2+)
uv run transcribe3 transcribe <audio_file> [options]

# Process audio + transcript together (Phase 3+)
uv run transcribe3 process <audio_file> <transcript_file> [options]

# Open the web review UI for a processed session
uv run transcribe3 review <session_id>

# Export a session to a specific format
uv run transcribe3 export <session_id> --format srt|vtt|txt|docx|json

# Run benchmarks against the gold standard test set (Phase 4+)
uv run transcribe3 benchmark tests/gold/
```

---

## Start the API Server

```bash
uv run uvicorn transcribe3.api.main:app --reload --host 127.0.0.1 --port 8010
```

The API will be available at `http://localhost:8010`. Interactive docs are at `http://localhost:8010/docs`.

> **Port conflict?** If port 8010 is already in use, start on another port (e.g. `--port 8050`) and create `src/ui/.env.local` so the UI knows where to find the API:
>
> ```
> VITE_API_URL=http://localhost:8050
> ```
>
> Restart the Vite dev server after creating or editing this file.

---

## UI Development

```bash
cd src/ui
npm install
npm run dev   # starts on http://localhost:3015
```

The UI connects to the API at `http://localhost:8010` by default. If your API is running on a different port, set `VITE_API_URL` in `src/ui/.env.local` before starting the dev server (see Port conflict note above). Start the API server first, then start the UI dev server.

## LAN mode (trusted networks only)

LAN mode is opt-in and requires an explicit browser-origin allowlist. Replace
`192.168.1.50` with the LAN IP address of the machine running Transcribe3.

```bash
# .env in the project root
TRANSCRIBE3_CORS_ORIGINS=http://192.168.1.50:3015

# src/ui/.env.local
VITE_API_URL=http://192.168.1.50:8010

# API terminal
uv run uvicorn transcribe3.api.main:app --reload --host 0.0.0.0 --port 8010

# UI terminal
cd src/ui
npm run dev -- --host 0.0.0.0
```

Browse to `http://192.168.1.50:3015` remotely. Permit ports 3015 and 8010 in the
host firewall if needed. Never use a wildcard CORS origin or expose these ports to
the internet: the API is unauthenticated and can modify and delete sessions.

To build for production:

```bash
cd src/ui
npm run build   # output in src/ui/dist/
```

---

## Run Tests

```bash
# All tests
uv run pytest

# Unit tests only
uv run pytest tests/unit/

# With coverage report
uv run pytest --cov=src
```
