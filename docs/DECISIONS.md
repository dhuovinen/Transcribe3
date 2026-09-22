# Transcribe3 — Architecture Decision Records

This file is append-only. Records are never deleted or modified after acceptance.

---

## ADR-001: Fully Local Processing

**Date:** 2026-05-23
**Status:** Accepted

### Context
Transcribe3 processes interview recordings and transcripts that may contain sensitive personal, professional, or journalistic content. Sending audio or text to external cloud APIs creates privacy risk and dependency on third-party service availability.

### Decision
All processing runs on-device. No audio data, transcript data, or derived content is sent to external services in the default configuration. The system uses only local open-weight models.

### Consequences
- Users must have sufficient local compute to run Whisper, pyannote.audio, and an Ollama-hosted LLM.
- Model quality is bounded by what runs locally on the target hardware (Apple Silicon primarily).
- The optional Claude API backend (benchmarking comparisons only) is explicitly opt-in and never used in the default pipeline.
- No network calls in the default configuration — no telemetry, no analytics, no model update checks.

---

## ADR-002: Open-Weight Models Only

**Date:** 2026-05-23
**Status:** Accepted

### Context
Privacy and reproducibility require that models are inspectable, locally runnable, and not subject to remote API changes or deprecation without notice.

### Decision
The default stack uses open-weight models only:
- **Transcription:** `faster-whisper` (optimized for Apple Silicon; MLX variant available)
- **Diarization:** `pyannote.audio`
- **LLM cleaning and attribution:** Ollama-hosted model (default: Llama 3.x or Mistral; configurable)

The Claude API is available as an optional, explicit-opt-in backend for benchmarking comparisons only. It is never the default.

### Consequences
- The pipeline is reproducible across machines without API keys or internet access.
- Model swapping for benchmarking is built into the architecture from the start (see ADR-005).
- Users who want Claude API quality comparisons must set up and opt into the integration explicitly.

---

## ADR-003: JSON as Canonical Internal Format

**Date:** 2026-05-23
**Status:** Accepted

### Context
Transcript data has rich metadata: timestamps, confidence scores, speaker maps, cleaning annotations, conflict flags, and segment-level provenance. Formats like TXT and SRT discard most of this. Downstream AI pipelines need the full metadata to make reliable decisions.

### Decision
JSON is the source-of-truth format for all processed sessions. It preserves all metadata with no fidelity loss. All other output formats (TXT, SRT, VTT, DOCX) are derived exports from the canonical JSON representation.

### Consequences
- The canonical `TranscriptSegment` type (in `shared/`) defines the JSON schema.
- Exporters are stateless transformations from JSON to a target format — they cannot recover metadata that was not in the JSON.
- The recommended primary output pair is JSON + SRT: JSON for pipeline use, SRT for caption workflows.
- Session archival stores JSON; other formats can always be re-derived.

---

## ADR-004: Two-Party Interview Scope Only (v1)

**Date:** 2026-05-23
**Status:** Accepted

### Context
Speaker diarization accuracy degrades as speaker count increases. Multi-speaker panels introduce overlapping speech, cross-talk complexity, and attribution ambiguity that require substantially more sophisticated diarization and attribution logic than a two-party conversation.

### Decision
v1 supports two-party interviews only (one interviewer, one subject). Group meetings and panels with more than two speakers are explicitly out of scope. The system will not attempt to diarize more than two speakers.

### Consequences
- Diarization logic can be simplified to a binary Speaker A / Speaker B model.
- Confidence scoring for attribution is more reliable within this constrained scope.
- Use cases involving panel discussions, roundtables, or multi-person calls are unsupported until this decision is revisited in a later phase.
- This constraint should be enforced at input validation; the system should reject or warn on inputs detected to have more than two distinct speakers.

---

## ADR-005: LLM Backend as Injected Dependency

**Date:** 2026-05-23
**Status:** Accepted

### Context
The project's benchmarking requirements (Phase 4) require running the same cleaning and attribution pipeline against multiple LLM backends and comparing results. If the LLM model is hardcoded inside `core/`, swapping it requires code changes, making controlled comparison impossible.

### Decision
The LLM backend is always injected as a dependency into `core/` functions and classes. The model name and backend configuration are always runtime parameters — never hardcoded constants anywhere in `core/`. `core/` defines an interface (protocol or abstract base class) for the LLM backend; concrete implementations live outside `core/`.

### Consequences
- `core/` is independently testable with a mock LLM backend that returns deterministic responses.
- Benchmarking can swap backends without touching core logic.
- Adding a new LLM backend (e.g., a new Ollama model or the Claude API) requires only a new implementation of the backend interface, not changes to `core/`.
- All CLI commands and API endpoints that invoke the LLM accept a `--model` parameter or equivalent configuration.

---

## ADR-006: WhisperX as the Integrated Audio Pipeline (Phase 2)

**Date:** 2026-05-24
**Status:** Accepted

### Context
Phase 2 requires audio transcription and speaker diarization. Two approaches were considered:
1. `faster-whisper` (transcription) + `pyannote.audio` (diarization) wired together manually
2. `WhisperX` — a single library that wraps faster-whisper, adds word-level forced alignment, and integrates pyannote.audio diarization into one pipeline call

### Decision
Use `WhisperX` as the single integration point for the Phase 2 audio pipeline. It is added as an optional dependency group (`audio`) in `pyproject.toml` so it does not inflate the base install for Phase 1 users.

Install with: `uv sync --extra audio`

### Consequences
- A single `whisperx.load_model()` + `whisperx.transcribe()` + `whisperx.assign_word_speakers()` call replaces what would have been separate integration code for transcription and diarization.
- `pyannote.audio` is still a direct dependency (pulled in by WhisperX) and requires a free HuggingFace token (`HF_TOKEN` in `.env`) to download speaker diarization model weights.
- `torchcodec` (a WhisperX transitive dependency) currently does not support FFmpeg 8.x. This produces a non-fatal warning at import time but does not affect WhisperX operation — it routes audio loading through `faster-whisper`'s own backend.
- Phase 1 install remains lightweight; audio processing is strictly opt-in.

---

## ADR-007: qwen3.6:27b as Default LLM Model

**Date:** 2026-05-24
**Status:** Accepted

### Context
The initial default LLM model was set to `llama3` during scaffolding. After reviewing models already installed in Ollama on the target machine, significantly more capable models were found to be available: `qwen3.6:27b`, `qwen3:30b`, `gemma4:26b`, `nemotron-3-nano:30b`.

For the attribution task — structured JSON output, two-speaker conversational flow reasoning, instruction following — model quality has a direct impact on attribution accuracy.

### Decision
`qwen3.6:27b` is the new default, updated in `src/transcribe3/shared/constants.py`. The model remains a runtime parameter on all commands; this is only the default fallback.

Recommended benchmarking set (all locally installed):

| Model | Role |
|---|---|
| `qwen3.6:27b` | Default — strongest instruction following at this scale |
| `gemma4:26b` | Benchmark comparison — Google's latest generation |
| `qwen3:30b` | Benchmark comparison — larger Qwen variant |
| `nemotron-3-nano:30b` | Benchmark comparison — NVIDIA offering |
| `qwen3.5:9b` | Fast fallback for low-latency use cases |

### Consequences
- Attribution quality improves substantially over `llama3` or `qwen2.5:7b`.
- Default model requires ~17 GB of memory. On machines with less RAM, `qwen3.5:9b` (6.6 GB) is the recommended fallback.
- The benchmarking framework (Phase 4) exists precisely to measure this — running `transcribe3 benchmark tests/gold/` against each model will produce objective accuracy comparisons.

---

## ADR-008: Audio and LLM Layers are Architecturally Separate

**Date:** 2026-05-24
**Status:** Accepted

### Context
During setup, the question arose whether any Ollama-hosted LLM could perform audio processing (transcription or diarization) directly, which would simplify the stack.

Investigation confirmed: no current Ollama-served model accepts raw audio input. Models described as "multimodal" in the installed set (`llava:13b`, `gemma4:26b`) support image input only — not audio. Speaker diarization requires a specialized neural architecture (speaker embedding + clustering) that is fundamentally different from a language model.

### Decision
The audio processing layer (WhisperX / pyannote.audio) and the LLM layer (Ollama) are architecturally separate and handle different stages of the pipeline:

```
Audio file → WhisperX → anonymous speaker segments + text
                                    ↓
                          Ollama LLM → named speakers + confidence scores + cleaning
```

No LLM in this pipeline receives raw audio. LLMs receive only text segments with anonymous speaker labels.

### Consequences
- The two layers can be updated, swapped, or benchmarked independently.
- If a future Ollama-compatible model with genuine audio input capability becomes available, it would require a new pipeline stage, not a replacement of the existing LLM stage.
- This separation is already reflected in the codebase: `core/attributor.py` operates on `TranscriptSegment` objects (text), never on audio.

---

## ADR-009: LAN Access Uses Explicit CORS Origins

**Date:** 2026-07-19
**Status:** Accepted

### Context

The Transcribe3 UI needs to be reachable from another machine on a trusted local
network. The API performs unauthenticated file and session operations, including
deletion, so enabling a blanket cross-origin policy would broaden access too far.

### Decision

LAN access is opt-in. The API reads `TRANSCRIBE3_CORS_ORIGINS` as a
comma-separated list of explicit browser origins. It rejects a wildcard and retains
the localhost-only allowlist when the setting is absent. Operators must bind Uvicorn
and Vite to `0.0.0.0` deliberately when LAN access is desired.

### Consequences

- The default development setup remains local-only.
- A LAN setup must identify the host's LAN URL in both the API CORS setting and the
  UI's `VITE_API_URL` setting.
- This is a trusted-network convenience feature, not an authentication boundary;
  public or untrusted-network deployment requires authentication and a reverse proxy.

---

## ADR-010: Verified External Audio Archive

**Date:** 2026-09-06
**Status:** Accepted

### Context

Original recordings can consume substantial local storage, while completed session
metadata and transcripts remain small and should stay immediately available for
search, editing, and export. An external SSD is available for the source recordings.

### Decision

The application archives only the original audio, not the session directory. The
admin UI configures an absolute archive root and stores each audio file under
`recordings/<session-id>/`. Session metadata records the relative archive path.

Every archive and restore operation writes to a temporary file, verifies source and
copy using a SHA-256 digest, and only then makes the copy available. An offload removes
the local recording only after that verification. A separate local-delete operation
rechecks the local and archived hashes and refuses to delete if they differ.

### Consequences

- Transcripts remain available when the external drive is disconnected.
- The audio player requires a local copy; an archived recording must be restored from
  the admin screen before it can be played locally.
- Archive copies take time proportional to recording size and run through the local
  API process.
- The archive root must remain mounted at the configured path to restore or verify
  recordings.

## ADR-011: Provider Bearer Tokens Live in the Environment

**Date:** 2026-09-21
**Status:** Accepted

### Context

The provider registry made LLM backends configurable data (ADR-005), but some servers
— hosted APIs and locally proxied models alike — require an `Authorization: Bearer`
token. The registry itself is stored in `sessions/settings.json`, which the
unauthenticated `GET /settings` endpoint returns verbatim to any browser on the LAN
and which the UI rewrites wholesale on every save.

### Decision

A provider's token is read from the process environment, never stored in
`settings.json`. The registry entry holds only the *name* of the variable: the
convention `TRANSCRIBE3_LLM_API_KEY_<PROVIDER_ID>` (id uppercased, non-alphanumerics
replaced by `_`), or an explicit `api_key_env` when an existing variable name is
preferred. `data/secrets.resolve_provider_api_key` performs the lookup, and the
resolved token is injected into `build_llm_client` by the API and CLI layers so
`core/` never reads the environment. A blank value counts as unset.

### Consequences

- Tokens never reach the browser, the settings file, or session metadata.
- The token cannot be set from the Settings screen; it is an operator task in `.env`,
  and the API server must be restarted to pick up a change.
- Both the model-list and completion calls authenticate, so a provider that needs a
  token appears in the UI's model picker exactly like one that doesn't.

## ADR-012: Application Settings Live Outside sessions/

**Date:** 2026-09-22
**Status:** Accepted

### Context

`settings.json` (the app-level defaults edited via the gear-icon Settings screen —
LLM providers/model, transcription backend/Whisper model, thresholds) lived inside
`sessions/`, the same directory that holds every `session_id/` subfolder. That made
it look session-scoped when it is not: it is one file shared by the whole app, and
each session already keeps its own frozen record of what was actually used to
produce it (`session.processing_params`, see `shared/types.py`). The shared
directory was a layout coincidence, not a functional coupling, but it was a real
source of confusion about which file governs what.

### Decision

`settings.json` now lives in its own directory, `config/` by default, resolved
independently of `sessions/` (`get_config_dir` in `api/dependencies.py`, mirrored by
`_config_dir_default` in `cli.py`), overridable via `TRANSCRIBE3_CONFIG_DIR`.
`SettingsRepository.load` migrates an existing `sessions/settings.json` to the new
location automatically on first read (`_migrate_legacy_location`), so upgrading
needs no manual step.

### Consequences

- The gear-icon Settings screen and `config/settings.json` are now unambiguously
  the same thing; `sessions/` holds only per-session data.
- Existing installs migrate in place the first time the server (or CLI) loads
  settings after upgrading; the old file is moved, not copied, so there is exactly
  one file to edit afterward.
- Anything that read `sessions/settings.json` directly (scripts, backups) needs to
  point at `config/settings.json` instead.

---

---

## Session Log Reference

**Design session date:** 2026-05-23 – 2026-05-24
**Session transcript:** `~/.claude/projects/-Users-dhuovinen-Documents/30121fc1-1271-46ba-96dc-fcdc52583720.jsonl`

This file contains the full verbatim conversation in which the requirements were defined, the task decomposition was designed, and all four build waves were executed. It is the authoritative record of why decisions were made and what alternatives were considered.
