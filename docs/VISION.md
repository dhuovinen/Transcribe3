# Transcribe3 — Vision

## What the System Does

Transcribe3 is a quality layer that sits on top of raw transcription. It accepts raw audio, raw transcripts, or both, and produces clean, speaker-attributed, confidence-scored transcripts that are ready for human review or downstream AI pipelines.

It does not compete with transcription engines — it improves their output. The pipeline cleans artifacts, normalizes formatting, validates speaker attribution using LLM-assisted conversational flow inference, and scores confidence per segment so that uncertain decisions are never silently accepted.

---

## Primary Users

**Owner (personal use)**
High-quality transcript production for interviews, recorded conversations, and archival purposes. Operates via CLI or the web review interface.

**AI agents in automated workflows**
Tool-calling via the CLI. Structured JSON output by default when stdout is not a TTY. Composable with other pipeline steps. Exit codes follow standard UNIX conventions for scripting.

**Non-users (v1):** External teams, public users, non-technical reviewers.

---

## Success Criteria

1. **End-to-end pipeline completeness.** A clean, speaker-attributed transcript can be produced from any of the three supported input types: transcript only, audio only, or audio + transcript combined.

2. **Fully local.** Zero data leaves the machine. No cloud API calls in the default configuration. The optional Claude API backend (benchmarking comparisons only) must be explicitly opted into by the user.

3. **Measurable accuracy.** Transcript quality is measurable against a manually corrected gold standard test set stored in `tests/gold/`. The `transcribe3 benchmark` command reports Word Error Rate (WER) and attribution accuracy against that ground truth.

4. **CLI composable for agent tool-calling.** Every command produces structured output, respects `--dry-run`, and exits with standard codes (`0` success, `1` validation error, `2` processing error). The CLI is the primary interface for AI agents.

---

## Non-Goals (v1)

| Item | Reason |
|---|---|
| Real-time transcription | Not a stated requirement; audio playback in the UI review interface is the only real-time component |
| Cloud processing | Privacy constraint: all models run on-device |
| Group meetings / panels (>2 speakers) | Deferred; increases diarization complexity significantly; two-party interviews only in v1 |
| Mobile interface | Not a stated requirement |
