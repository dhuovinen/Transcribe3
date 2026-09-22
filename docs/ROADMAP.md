# Transcribe3 — Roadmap

## Phase Overview

| Phase | Goal | Status |
|---|---|---|
| Phase 1 | MVP — transcript cleaning, manual speaker assignment, CLI + minimal UI | **[COMPLETE]** |
| Phase 2 | Audio pipeline — Whisper transcription, diarization, review UX | **[CURRENT]** |
| Phase 3 | Alignment and conflict resolution — highest-confidence output path | Planned |
| Phase 4 | Benchmarking framework and advanced speaker ID | Planned |

---

## Phase 1 — MVP [CURRENT]

**Key deliverable:** End-to-end Scenario 1 with a working CLI and minimal web UI.

- [ ] Scenario 1: transcript-only cleaning and attribution validation
- [ ] LLM-assisted speaker attribution using conversational flow inference
- [ ] Manual speaker ID via web UI (no automated diarization)
- [ ] Basic confidence scoring on LLM attributions
- [ ] Low-confidence flagging — segments below threshold surfaced for human review
- [ ] CLI commands: `clean`, `review`, `export`
- [ ] Output formats: JSON + TXT
- [ ] Web UI: load transcript → manual speaker assignment → export
- [ ] No audio processing in this phase

---

## Phase 2 — Audio Pipeline [CURRENT]

**Key deliverable:** Audio-only transcription path with speaker diarization and full review UX.

- [x] Scenario 2: audio-only path (WhisperX transcription + pyannote.audio diarization)
- [x] Speaker-to-name mapping with manual confirmation in UI (uses existing speaker map editor)
- [x] Human review UX with audio player and click-to-jump playback
- [x] SRT and VTT export (carried from Phase 1)
- [x] CLI: `transcribe` command
- [x] `POST /sessions/upload-audio` API endpoint
- [x] `GET /sessions/{id}/audio` endpoint to serve audio for browser playback

---

## Phase 3 — Alignment and Conflict Resolution

**Key deliverable:** Scenario 3 — the highest-confidence output path combining audio + existing transcript.

- [ ] Audio + transcript forced alignment
- [ ] Conflict detection and resolution between transcript text and audio content
- [ ] Conflicts annotated for human review
- [ ] DOCX export with review annotations
- [ ] Verbatim mode (disables all cleaning; exact speech record for legal/journalism use)
- [ ] CLI: `process` command

---

## Phase 4 — Benchmarking and Advanced Speaker ID

**Key deliverable:** Measurable quality; automated speaker fingerprinting.

- [ ] Full benchmarking framework (`benchmark` CLI command)
- [ ] WER, attribution accuracy, confidence calibration, and cleaning precision/recall metrics
- [ ] Multi-LLM comparison tooling — run same pipeline against multiple model backends
- [ ] Benchmark results stored as JSON for cross-run comparison
- [ ] Known voice sample matching for speaker ID (voice fingerprint vs. reference samples)
- [ ] Gold standard test set tooling (`tests/gold/` management)

---

## Backlog

Features captured for future prioritisation. Not yet assigned to a phase.

### Custom dictionary / glossary correction

Apply a user-defined dictionary of corrections before or after the LLM cleaning pass.
Primary use case: proper nouns, technical terms, brand names, and domain-specific vocabulary that speech-to-text models consistently transcribe incorrectly (e.g. a person's name, a product name, an acronym).

**Intended behaviour:**
- Dictionary is a simple key→value map: `{"incorect spelling": "Correct Spelling"}`
- Applied as a pre-processing pass so the LLM sees already-corrected text
- Supports whole-word and phrase matching (case-insensitive by default, configurable)
- Dictionary scoped per-session (uploaded alongside transcript) or as a persistent global dictionary
- UI to manage the global dictionary (add, edit, delete entries)
- CLI flag: `--dictionary path/to/dict.json`
- Corrections logged as a `dictionary_correction` segment flag so they are auditable

### Topic-aware speaker-turn sectioning

Improve audio-transcript readability by grouping diarized segments into coherent
speaker turns and topic-based sections, while preserving the source segments and
their timestamp-level interaction in the UI.

**Intended behaviour:**
- Begin a new section whenever the confirmed speaker changes.
- Combine contiguous segments from the same speaker into one displayed section.
- Keep brief backchannels or interjections (for example, “right” or “okay”) from
  creating a new section when the surrounding speaker continues the same thought.
- Within uninterrupted same-speaker speech, begin a new section at a meaningful
  topic transition.
- When no topic transition occurs, split a continuous turn at a natural sentence
  boundary after approximately 35–40 seconds; never split a sentence mid-way.
- Preserve every underlying segment's timestamps, speaker, editable text, and
  original text so timestamp-to-audio seeking remains precise.

**Implementation direction:**
- Use deterministic post-processing for speaker changes, contiguous merging,
  short-interjection thresholds, and the maximum continuous-turn duration.
- Use a separate LLM boundary-classification pass only to identify substantive
  topic transitions; it must return structured boundary decisions and never
  rewrite text, timestamps, or speaker labels.
- Make the maximum turn duration configurable (default: 40 seconds), with
  topic-aware sectioning enabled by default.

### Auto-expanding transcript text fields

Ensure long transcript text is readable directly in the review list without
requiring the reviewer to enter a text field or scroll inside it.

**Intended behaviour:**
- Automatically size each editable transcript text field to its complete content
  when loaded and as it is edited.
- Do not show an internal vertical scrollbar or require focus merely to read text.
- Preserve inline editing and the existing save-on-blur behavior.
- Keep timestamps, speaker labels, and confidence indicators aligned with the
  top of the expanded row.
- Retain an accessible responsive layout on smaller screens.
