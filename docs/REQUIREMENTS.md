# Transcribe3 — Requirements

> Transcript validation and enrichment pipeline. A quality layer that sits on top of raw transcription: clean, speaker-attributed, validated output from multiple input types.

---

## 1. Purpose and Users

**What it does:** Accept raw audio, raw transcripts, or both — and produce clean, speaker-attributed, confidence-scored transcripts ready for human review or downstream AI pipelines.

**Primary users:**
- Owner (personal use, high-quality transcript production)
- AI agents (tool-calling via CLI in automated workflows)

**Non-users (v1):** External teams, public users, non-technical reviewers

---

## 2. Core Constraints

| Constraint | Decision |
|---|---|
| Processing location | **Fully local** — no cloud APIs, no data leaves the machine |
| Models | **Open-weight only** (Whisper, pyannote.audio, Ollama-hosted LLMs) |
| Speaker scope | **Two-party interviews only** — panels and group meetings are explicitly out of scope in v1 |
| Real-time processing | **Not required** — batch processing only; real-time audio playback in UI review is the sole exception |

---

## 3. Input Scenarios

### Scenario 1 — Transcript Only
**Input:** Raw text file (plain text, OCR output, or loosely formatted transcript)

**Processing:**
1. Clean OCR artifacts, formatting inconsistencies, encoding errors
2. Normalize speaker labels, punctuation, and timestamp format
3. Validate and correct speaker attribution using conversational flow inference (LLM-assisted)
4. Score confidence per segment; flag low-confidence attributions for human review

**Output:** Clean, normalized, attributed transcript with confidence scores

---

### Scenario 2 — Audio Only
**Input:** Audio file (WAV, MP3, M4A, or similar)

**Processing:**
1. Transcribe audio using Whisper (local, open-weight)
2. Perform speaker diarization (pyannote.audio) → Speaker A / Speaker B segments
3. Map speaker clusters to real names (see Section 5)
4. Apply Scenario 1 cleaning pipeline to the resulting transcript

**Output:** Speaker-labeled, cleaned transcript with timestamps and confidence scores

---

### Scenario 3 — Audio + Transcript
**Input:** Audio file + existing transcript document

**Processing:**
1. Align existing transcript against the audio timeline (forced alignment)
2. Use diarization output to confirm or correct speaker labels
3. Detect and resolve conflicts between transcript text and audio content
4. Apply Scenario 1 cleaning pipeline

**Output:** Highest-confidence attributed transcript; conflicts annotated for human review

---

## 4. Speaker Identity Resolution

Diarization produces anonymous speaker clusters (Speaker A, Speaker B). Name resolution follows this priority order:

1. **Manual confirmation via UI** — reviewer confirms the first attributed instance for each speaker (MVP approach)
2. **LLM context inference** — conversational flow analysis to infer speaker identity from content
3. **Known voice sample matching** — voice fingerprint comparison against reference samples (Phase 4)

**Rules:**
- Every attribution carries a confidence score (see Section 7)
- Low-confidence attributions are **never silently accepted** — they surface in the human review queue
- Speaker identity mapping is stored per-session and can be re-used across related files

---

## 5. Cleaning Layer

All behaviors are configurable per run via CLI flags or UI toggles.

| Behavior | Default | Options |
|---|---|---|
| Filler word removal (`um`, `uh`, `you know`, etc.) | Off | `off` / `flag` / `strip` |
| False starts and self-corrections | Preserve | `preserve` / `remove` |
| Crosstalk and interruptions | Flag + preserve | `flag` / `preserve` / `remove` |
| Verbatim mode | Off | When enabled, disables all cleaning — outputs exact speech (for legal, journalism) |

When **verbatim mode** is on, it overrides all other cleaning settings and produces an exact record of speech.

---

## 6. Output Formats

**Canonical internal format: JSON**

JSON is the source-of-truth format. It preserves all metadata (timestamps, speaker maps, confidence scores, cleaning annotations) and enables downstream LLM pipelines with no fidelity loss.

All other formats are derived exports from JSON.

| Format | Use case |
|---|---|
| `JSON` | Machine consumption, AI pipelines, archival, benchmarking |
| `SRT` | Video captions and subtitles |
| `VTT` | Web video captions (HTML5 `<video>`) |
| `TXT` | Plain human-readable attributed text |
| `DOCX` | Formatted document with review annotations and speaker labels |

**Recommended primary pair: JSON + SRT.** JSON for pipeline use; SRT for caption workflows.

---

## 7. Confidence Scoring

- Every transcript segment carries a confidence score: `0.0` (no confidence) to `1.0` (certain)
- **Low-confidence threshold:** configurable, default `0.6`
- Segments below threshold are:
  - Flagged in all output formats
  - Surfaced in the UI review queue with visual indicator
  - Never auto-accepted without human confirmation
- CLI output includes a summary confidence report (total segments, low-confidence count, mean score)

---

## 8. Human Review UX (Web UI)

The review interface is optimized for a single reviewer correcting a batch-processed transcript.

**Core interactions:**
- Side-by-side layout: audio waveform / playback on one side, transcript on the other
- Click any transcript segment to jump audio playback to that timestamp
- Inline edit of speaker attribution and text content
- Low-confidence segments highlighted with a distinct visual indicator
- Per-segment accept / override action (confirm or change the attribution decision)
- Session auto-save; export to any supported format on completion

**Audio playback** is the only real-time requirement in the system. All other processing is batch.

---

## 9. CLI Interface

The CLI is the primary interface for agent/tool-calling use. It must be composable and scriptable.

**Design principles:**
- Structured output (JSON) by default when stdout is not a TTY
- Human-readable output when running interactively
- Exit codes: `0` success, `1` validation error, `2` processing error
- `--dry-run` flag available on all write operations
- Verbosity control: `--quiet` / `--verbose`

**Key commands (illustrative, not final):**
```
transcribe3 clean <transcript_file> [options]
transcribe3 transcribe <audio_file> [options]
transcribe3 process <audio_file> <transcript_file> [options]
transcribe3 review <session_id>          # open UI for a processed session
transcribe3 export <session_id> --format srt|vtt|txt|docx|json
transcribe3 benchmark <gold_set_dir>     # run benchmarks against gold standard
```

---

## 10. Tech Stack

All components are local and open-weight.

| Component | Technology | Notes |
|---|---|---|
| Language | Python 3.11+ | |
| Package management | `uv` | Consistent with existing projects |
| Transcription | `faster-whisper` | Optimized for Apple Silicon; MLX variant available |
| Diarization | `pyannote.audio` | Leading open-source speaker diarization |
| LLM (cleaning / attribution) | Ollama + configurable model | Default: Llama 3.x or Mistral; swappable for benchmarking |
| LLM (optional) | Claude API | Optional backend; used for benchmarking comparisons only |
| Web UI backend | FastAPI | Consistent with existing projects |
| Web UI frontend | TBD | Deferred to Phase 2; requires DOM control for audio/media UX |
| CLI | Typer | Agent/tool-calling compatible; structured output support |
| Audio processing | ffmpeg | Consistent with existing projects |

---

## 11. Benchmarking Framework

Benchmarking is a first-class requirement — accuracy must be measurable, not assumed.

**Gold standard test set:**
- Manually corrected transcripts used as ground truth
- Minimum viable test set: one fully corrected two-party interview
- Stored in `tests/gold/` with paired audio files where available

**Metrics:**
| Metric | What it measures |
|---|---|
| WER (Word Error Rate) | Transcription accuracy vs. ground truth |
| Attribution accuracy | % of segments with correct speaker label |
| Confidence calibration | Correlation between confidence scores and actual accuracy |
| Cleaning precision/recall | Correct vs. over/under-cleaning decisions |

**Multi-model comparison:**
- LLM backend is a configurable parameter, not a hardcoded dependency
- `transcribe3 benchmark` runs the full pipeline against the gold set for a given model
- Results stored as JSON for comparison across runs and models

---

## 12. Phased Delivery Plan

### Phase 1 — MVP
**Goal:** End-to-end Scenario 1 with manual speaker assignment and a working CLI + minimal UI

- Scenario 1 only: transcript-only cleaning and attribution validation
- Manual speaker ID via UI (no automated diarization)
- CLI: `clean`, `review`, `export` commands
- Output: JSON + TXT
- Basic confidence scoring on LLM attributions
- Web UI: load transcript → manual speaker assignment → export
- No audio processing in this phase

### Phase 2 — Audio Pipeline
**Goal:** Add audio transcription and diarization; complete the review UX

- Scenario 2: audio-only path (Whisper transcription + pyannote.audio diarization)
- Speaker-to-name mapping with manual confirmation in UI
- Human review UX with audio playback and click-to-jump
- SRT / VTT export
- CLI: `transcribe` command

### Phase 3 — Alignment and Conflict Resolution
**Goal:** Scenario 3 — the highest-confidence output path

- Audio + transcript forced alignment
- Conflict detection and resolution between transcript and audio
- DOCX export with review annotations
- Verbatim mode
- CLI: `process` command

### Phase 4 — Benchmarking and Advanced Speaker ID
**Goal:** Measurable quality; automated speaker fingerprinting

- Full benchmarking framework and `benchmark` CLI command
- Multi-LLM comparison tooling
- Known voice sample matching for speaker ID
- Gold standard test set tooling

---

## 13. Out of Scope (v1)

| Item | Reason |
|---|---|
| Real-time transcription | Not a stated requirement |
| Cloud API processing | Privacy constraint: fully local |
| Multi-speaker panels / group meetings (>2 speakers) | Deferred; increases diarization complexity significantly |
| Mobile interface | Not a stated requirement |
| Automated diarization in MVP | Deferred to Phase 2; MVP uses manual speaker ID via UI |
| Speaker diarization in MVP | Deferred to Phase 2 |

---

## 14. Privacy and Data Handling

- All processing is local — no audio or transcript data is sent to external services
- The optional Claude API backend (benchmarking only) must be explicitly opted into; it is not used by default
- No persistent storage of session data beyond the project working directory
- No telemetry, analytics, or network calls in the default configuration
