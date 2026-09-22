# Audio transcription evals (`eval/gold_audio/`)

This directory holds gold-standard audio + transcript pairs used to benchmark
the transcription backends (`whisperx`, `mlx`) for speed and accuracy (Word
Error Rate). See [`docs/evaluations/`](../docs/evaluations/) for write-ups
from past runs, and the Help panel in the web UI (gear icon → Help →
"Benchmarking & gold evals") for a shorter in-app summary.

## Running an eval

```bash
uv sync --extra mlx                       # only needed once, to enable the mlx backend
uv run python eval/run_eval.py                          # all cases, both backends, medium model
uv run python eval/run_eval.py --model small              # all cases, both backends, small model
uv run python eval/run_eval.py --backend mlx               # all cases, mlx only
uv run python eval/run_eval.py --case retro_5min            # one case, both backends
```

Results are written to `eval/results/results_<model>.json`, keyed by case name
then backend, with `elapsed_sec`, `num_segments`, `wer`, and the full
`hypothesis_text` for manual inspection.

## Directory layout

Each case is a subdirectory of `eval/gold_audio/`:

```
eval/gold_audio/<case_name>/
  audio.<ext>            # .wav/.mp3/.m4a/.flac/.ogg/.mp4
  gold_transcript.json   # required — see schema below
  gold_transcript.txt    # optional — human-readable copy
  generate.py            # optional — only for synthetic cases (see below)
```

`run_eval.py` discovers every directory under `eval/gold_audio/` that contains
a `gold_transcript.json` and runs each requested backend against it — no
registration step needed, just add the directory.

### `gold_transcript.json` schema

```json
{
  "case": "retro_5min",
  "source": "synthetic-tts",
  "notes": "Free-text: how this gold transcript was produced/verified.",
  "audio_file": "audio.wav",
  "duration_sec": 306.1,
  "segments": [
    { "speaker": "Alex", "text": "Okay, thanks everyone for joining." },
    { "speaker": "Jordan", "text": "Sounds good." }
  ]
}
```

- `segments[].text` is concatenated (in order) to form the reference text for
  WER — speaker labels aren't currently used in scoring, but keep them anyway
  since diarization accuracy is a natural future addition to these evals.
- `audio_file` should name the file in the same directory. If omitted or
  missing, `run_eval.py` falls back to the first supported audio file it
  finds in the case directory.
- `source` should be one of `"synthetic-tts"` or `"manual-verification"` (or
  another short free-text value) — it's not read by the runner, but keeps
  cases self-documenting for anyone auditing them later.

## Adding a new gold case

You have two options:

### Option A — synthetic (fast, exact ground truth, no privacy concerns)

Best when you just want more coverage (different lengths, topics, number of
speakers) without needing real acoustic conditions.

1. Copy `eval/gold_audio/retro_5min/generate.py` into a new case directory as
   a starting point.
2. Edit the `LINES` list — each entry is `(speaker_name, text)`. Map speaker
   names to macOS voices in the `VOICES` dict (run `say -v '?'` to list
   available voices; pick two clearly distinct ones).
3. Run it: `python3 eval/gold_audio/<new_case>/generate.py` — this uses `say`
   and `ffmpeg` (both must be on your PATH) to synthesize each line, stitch
   them into one WAV with short pauses between turns, and write
   `audio.wav` + `gold_transcript.json` + `gold_transcript.txt` next to it.
4. Confirm the printed duration is what you expected, then run an eval
   against just that case: `uv run python eval/run_eval.py --case <new_case>`.

### Option B — real recording with a manually verified transcript

Best for testing real acoustic conditions (background noise, accents,
overlapping speech, mic quality) that synthetic audio can't exercise.

1. Create `eval/gold_audio/<new_case>/` and put the audio file in it.
2. Transcribe it once with whichever backend/model to get a draft, then
   **manually correct every line against the actual audio** — listen to the
   whole thing and fix it word-for-word. A gold transcript that wasn't
   actually verified against the audio isn't a gold transcript; it just
   silently caps your WER measurements at whatever the model you used to
   draft it got right.
3. Write `gold_transcript.json` by hand (or script it from your corrected
   transcript) following the schema above. Split into `segments` however is
   convenient — sentence-per-segment is fine, since scoring joins them back
   into one reference string.
4. Consider privacy before adding a real recording here — this directory is
   part of the repo. Prefer synthetic cases for anything containing real
   names, business details, or other information you wouldn't want checked
   into version control.

## Why WER, and its limits

WER (Word Error Rate) is `(substitutions + deletions + insertions) / reference_word_count`,
computed via Levenshtein alignment — the same function already used by
`transcribe3 benchmark` for the text-cleaning pipeline
(`transcribe3.cli._word_error_rate`), reused here for consistency.

It's unnormalized: `"5%"` vs `"five percent"`, or `"1200"` vs `"twelve hundred"`,
count as full errors even though the transcription is arguably correct. This
matters most for whisperx, which tends to use numerals — its real-world WER is
likely a bit better than the raw number suggests. If you extend `run_eval.py`,
adding a text-normalization step (numeral expansion, punctuation stripping)
before scoring both hypothesis and reference is the highest-value next
improvement.
