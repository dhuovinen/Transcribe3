# Evaluation: WhisperX (CPU) vs mlx-whisper (Apple GPU) — Transcription Backend

**Date:** 2026-09-01
**Author:** Claude Code, with dhuovinen
**Status:** Complete
**Related change:** Added a `backend` option (`whisperx` | `mlx`) to `transcribe_audio()` — see [`src/transcribe3/core/audio/transcriber.py`](../../src/transcribe3/core/audio/transcriber.py)

## Motivation

Transcription on the existing `whisperx` backend runs on CPU only — the underlying
CTranslate2/faster-whisper engine has no Apple GPU (Metal/MPS) support, so moving
from the `base` Whisper model to `medium` for better quality made transcription
noticeably slower. `mlx-whisper` runs Whisper on Apple's GPU/Neural Engine via MLX
and was added as an alternative backend. This evaluation measures whether it's
actually faster and how transcription quality compares, before recommending it as
a default.

## Test setup

| | |
|---|---|
| Hardware | Mac mini, Apple M4 Pro, 64 GB RAM |
| Whisper model sizes | `medium` and `large-v2`, both backends |
| Audio | Synthetic, 5.1 minutes (306.1s), 16kHz mono WAV |
| whisperx config | `device="cpu"`, `compute_type="int8"`, `batch_size=4` (unchanged production defaults) |
| mlx config | `mlx-community/whisper-{medium,large-v2}-mlx`, default settings |
| Diarization | Excluded from timing — this evaluates the transcription step only, which is what the backend choice affects |

### Why a synthetic baseline

No existing recording in the project had a manually-verified ground-truth transcript
to benchmark against — files under `sessions/` are raw pipeline output (uniform
`confidence: 0.8`, no review flag), not corrected transcripts. Rather than hand-correct
a real recording, the baseline clip was synthesized from a known script via macOS
`say` (two voices — `Daniel` and `Samantha` — for two speakers), so the **script text
is exact ground truth by construction**. This isolates ASR (speech-to-text) accuracy
from the audio content itself, at the cost of not testing real acoustic conditions
(background noise, overlapping speech, accents, mic quality).

Content: a 45-turn two-person "project retro" dialogue including numbers, percentages,
technical terms, and natural speech patterns — chosen to exercise transcription on
content similar to real usage (meetings/interviews) without using anyone's real audio.

Generation script and gold transcript: [`eval/gold_audio/retro_5min/`](../../eval/gold_audio/retro_5min/)
(`generate.py` produces `audio.wav` + `gold_transcript.json`; the shared
[`eval/run_eval.py`](../../eval/run_eval.py) runs any backend against any gold
case and computes WER — see [`eval/README.md`](../../eval/README.md) for how to
add more cases).

### Metrics

- **Duration**: wall-clock time for `transcribe_audio()` to return segments.
- **Quality**: Word Error Rate (WER) against the gold transcript, using the same
  Levenshtein-based WER function already in `transcribe3.cli._word_error_rate`
  (kept consistent with the project's existing benchmark command).

## Results

| Backend | Model | Time | Segments | WER |
|---|---|---|---|---|
| whisperx (CPU) | medium | 89.0s | 98 | 0.0658 |
| mlx-whisper (Apple GPU) | medium | 19.2s | 62 | 0.1015 |
| whisperx (CPU) | large-v2 | **133.9s** | 99 | **0.0645** |
| mlx-whisper (Apple GPU) | large-v2 | **27.2s*** | 54 | **0.0796** |

\* Every model's *first* run on a given machine also pays a one-time download
cost (medium: ~205s, large-v2: ~461s), cached under `~/.cache/huggingface`
afterward. All timings above are steady-state, model-cached numbers — the fair,
repeatable comparison, and what it will actually run at after first use.

**Speed:** mlx-whisper is **~4.6x faster** at medium (19.2s vs 89.0s) and
**~4.9x faster** at large-v2 (27.2s vs 133.9s). The speed multiplier holds
steady as model size goes up — mlx isn't just winning because medium is cheap.

**Quality:** whisperx is more accurate at both sizes, but the gap **shrinks
sharply** going from medium to large-v2:

| | medium | large-v2 |
|---|---|---|
| WER gap (mlx − whisperx) | +3.6 points (10.15% vs 6.58%) | **+1.5 points (7.96% vs 6.45%)** |

mlx-whisper/large-v2 is within 1.5 WER points of whisperx/medium while still
running **~3.3x faster** than whisperx/medium (27.2s vs 89.0s) — the strongest
speed/accuracy combination measured here.

### What actually went wrong

**mlx / medium** (10.15% WER) — a handful of concrete errors, not a uniform
quality gap:
- One duplicated sentence ("That's a big jump. Should we split that suite out or
  invest in parallelization?" appears twice consecutively).
- A dropped clause ("...on release day, **compared to our usual 15**" was cut).
- Two word-level mishearings: "retried **two** aggressively" (should be "too"),
  and "creep back **enough to** the holidays" (should be "in after").
- More aggressive sentence-splitting than whisperx (62 vs 98 segments) — doesn't
  hurt WER directly but affects downstream segment-level timestamp granularity.

**mlx / large-v2** (7.96% WER) — the duplicated sentence from medium is gone,
and segment count (54) moved further from whisperx's granularity, not closer.
Remaining errors:
- "cap retries" instead of "capped retries".
- "before we go" instead of "before we wrap up".
- The same "creep back **enough to** the holidays" mishearing as medium —
  this looks like a systematic weak spot for mlx-whisper on this phrase, not
  model-size-dependent.
- One more substantial slip: "**Is that a good idea?**" in place of "Is that
  within the range we planned for?" — a bigger semantic miss than the other
  errors, though still an isolated one, not a pattern.

whisperx's residual WER at both sizes is almost entirely **numeral
formatting**, not real errors — e.g. "5%" vs the gold's "five percent", "1,200"
vs "twelve hundred". These are correct transcriptions, just normalized
differently than the literal gold script. A text-normalization pass before WER
(expanding numerals, stripping punctuation) would lower both backends' WER and
likely narrow the gap further in whisperx's favor, since it has fewer of these
mismatches to begin with.

## Recommendation

- **Keep `whisperx` as the default backend for now.** It's the more accurate
  option at every size tested, and whisperx/medium at ~1.7x real-time isn't
  painfully slow for occasional use — the original "medium is slow" complaint
  was mostly about `medium` vs `base`, not whisperx vs an alternative.
- **mlx/large-v2 is the best fast-path option**, not mlx/medium as originally
  suggested — it's within 1.5 WER points of whisperx/medium while running
  ~4.9x faster than whisperx/large-v2 (or ~3.3x faster than whisperx/medium).
  If a "fast" preset is ever added to the UI/CLI defaults, point it at
  mlx/large-v2 rather than mlx/medium.
- `mlx` stays an explicit opt-in (`--backend mlx` / the UI dropdown) rather
  than a new default, given whisperx's accuracy edge still holds at both sizes
  tested and only one audio sample has been evaluated so far.
- Worth testing `large-v3` on both backends next — the gap-narrowing trend
  from medium→large-v2 suggests it could close further, or even flip, at the
  top model size. Not tested here.

## Caveats

- Single synthetic sample, one language (English), clean audio, no background
  noise or overlapping speech, no diarization — real recordings (phone/laptop
  mic, cross-talk, accents) will shift both backends' absolute WER and may
  change the ranking.
- WER here is unnormalized (no numeral/punctuation normalization), which
  penalizes both backends but especially whisperx's numeral-formatting
  "errors" that are arguably not errors at all.
- Single run per backend/model — no variance estimate.
- `mlx-whisper` model-download time (~205s, one-time per model size) is worth
  accounting for if evaluating a model size for the first time on a fresh machine.

## Reproducing

```bash
uv sync --extra mlx
uv run python eval/run_eval.py --model medium --case retro_5min     # or omit --case to run every gold case
uv run python eval/run_eval.py --model large-v2 --case retro_5min
```

Results accumulate per model file (`eval/results/results_<model>.json`) —
running a subset of backends/cases merges into the existing file rather than
overwriting it, so re-running one backend later doesn't lose prior entries.
