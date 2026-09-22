"""Generates the synthetic 5-minute two-speaker baseline clip via macOS `say`.

Ground truth: the LINES list below is the exact transcript. Each line is
synthesized individually (so speaker turns are unambiguous), stitched into
one WAV with ffmpeg, and the gold transcript files are written alongside it.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

OUT_DIR = Path(__file__).parent
VOICES = {"Alex": "Daniel", "Jordan": "Samantha"}

# (speaker, text) — a two-person project retro discussion, ~5 minutes at
# natural speaking pace including pauses between turns.
LINES = [
    ("Alex", "Okay, thanks everyone for joining. Let's do a quick retro on the September release."),
    ("Jordan", "Sounds good. I'll start with what went well, if that's okay."),
    ("Alex", "Please, go ahead."),
    ("Jordan", "So the migration to the new billing service went smoother than expected. We budgeted three days and it took two."),
    ("Alex", "That's great. Was that because of the staging environment we set up last month?"),
    ("Jordan", "Exactly. Having a realistic staging environment with production-like data caught two edge cases before they hit customers."),
    ("Alex", "Good, that validates the investment. What about the on call rotation? I heard there were some pages overnight."),
    ("Jordan", "Yeah, there were four pages between Tuesday and Thursday. Three were false alarms from a noisy health check."),
    ("Alex", "And the fourth?"),
    ("Jordan", "The fourth was real. The payment webhook retried too aggressively and briefly overloaded the database connection pool."),
    ("Alex", "Do we have a fix for that already, or is it still open?"),
    ("Jordan", "We shipped a fix on Friday. We added exponential backoff and capped retries at five attempts."),
    ("Alex", "Perfect. Let's make sure that's documented in the runbook so the next on call engineer isn't caught off guard."),
    ("Jordan", "Agreed, I'll update the runbook this afternoon."),
    ("Alex", "Let's talk about the frontend rollout next. How did the feature flag rollout go?"),
    ("Jordan", "We rolled out to five percent, then twenty five percent, then everyone, over about four days."),
    ("Alex", "Any issues at each stage?"),
    ("Jordan", "At the twenty five percent stage we saw a small increase in checkout abandonment, maybe half a percent."),
    ("Alex", "Did we figure out why?"),
    ("Jordan", "It turned out to be a rendering delay on older Android devices. The new checkout summary component was doing a synchronous layout calculation."),
    ("Alex", "Was that fixed before we went to a hundred percent?"),
    ("Jordan", "Yes, we moved the calculation off the main thread and abandonment went back to baseline within a day."),
    ("Alex", "Nice catch. What about the design team's feedback on the new checkout flow?"),
    ("Jordan", "Overall positive. They want to revisit the confirmation screen typography in the next design review."),
    ("Alex", "Let's put that on the agenda for next week rather than block this release on it."),
    ("Jordan", "Agreed, it's a small polish item, not a blocker."),
    ("Alex", "Okay, now for what didn't go well. I want to talk about the deployment pipeline delays."),
    ("Jordan", "Right, the pipeline took almost forty minutes on release day, compared to our usual fifteen."),
    ("Alex", "Do we know the root cause?"),
    ("Jordan", "The test suite for the reporting module isn't parallelized, and it grew significantly this quarter."),
    ("Alex", "How many tests are we talking about?"),
    ("Jordan", "About twelve hundred tests now, up from around four hundred at the start of the year."),
    ("Alex", "That's a big jump. Should we split that suite out, or invest in parallelization?"),
    ("Jordan", "I'd recommend parallelization first since it's lower effort. Splitting can come later if needed."),
    ("Alex", "Let's put together a small proposal by next Friday and estimate the effort."),
    ("Jordan", "I can own that. I'll have a short write up ready by Wednesday for early feedback."),
    ("Alex", "Great, thank you. Any other blockers or risks we should flag before we wrap up?"),
    ("Jordan", "One thing. The vendor for the fraud detection API mentioned a rate limit change starting next month."),
    ("Alex", "Do we know the new limit yet?"),
    ("Jordan", "Not the exact number, but they said it could be as much as forty percent lower than today."),
    ("Alex", "Let's get that confirmed this week so we have time to adjust our request batching if needed."),
    ("Jordan", "I'll email them today and loop in the team once I hear back."),
    ("Alex", "One more thing before we wrap. How's the team feeling about the on call load in general?"),
    ("Jordan", "Honestly, a bit better than last quarter. Splitting the rotation into two weeks instead of one helped a lot."),
    ("Alex", "Good, I was worried burnout might creep back in after the holidays."),
    ("Jordan", "It's manageable right now. The main ask from the team was better documentation for the newer services."),
    ("Alex", "That's fair. Let's fold that into the runbook update you're already doing."),
    ("Jordan", "I can do that. I'll flag which services are missing docs and prioritize those first."),
    ("Alex", "Great. Last item, budget for next quarter. Do we need to request more infrastructure spend?"),
    ("Jordan", "Slightly. The staging environment upgrade added about eight percent to our monthly cloud bill."),
    ("Alex", "Is that within the range we planned for?"),
    ("Jordan", "Yes, it's under the ten percent ceiling we agreed on back in July."),
    ("Alex", "Perfect. I think that covers everything. Thanks for a thorough retro, Jordan."),
    ("Jordan", "Thanks, Alex. Talk soon."),
]


def main() -> None:
    part_paths: list[Path] = []
    transcript_lines: list[str] = []

    for i, (speaker, text) in enumerate(LINES):
        voice = VOICES[speaker]
        aiff_path = OUT_DIR / f"_part_{i:03d}.aiff"
        subprocess.run(["say", "-v", voice, "-o", str(aiff_path), text], check=True)
        part_paths.append(aiff_path)
        transcript_lines.append(f"{speaker}: {text}")

    # Concat list for ffmpeg, with a short silence between turns for realism.
    silence_path = OUT_DIR / "_silence.aiff"
    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono",
         "-t", "0.6", str(silence_path)],
        check=True, capture_output=True,
    )

    concat_list = OUT_DIR / "_concat.txt"
    with concat_list.open("w") as f:
        for p in part_paths:
            f.write(f"file '{p.name}'\n")
            f.write(f"file '{silence_path.name}'\n")

    combined_aiff = OUT_DIR / "_combined.aiff"
    subprocess.run(
        ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat_list), "-c", "copy", str(combined_aiff)],
        check=True, capture_output=True, cwd=OUT_DIR,
    )

    final_wav = OUT_DIR / "audio.wav"
    subprocess.run(
        ["ffmpeg", "-y", "-i", str(combined_aiff), "-ar", "16000", "-ac", "1", str(final_wav)],
        check=True, capture_output=True,
    )

    # Duration
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(final_wav)],
        check=True, capture_output=True, text=True,
    )
    duration_sec = float(probe.stdout.strip())

    (OUT_DIR / "gold_transcript.txt").write_text("\n".join(transcript_lines) + "\n")
    (OUT_DIR / "gold_transcript.json").write_text(json.dumps(
        {
            "case": OUT_DIR.name,
            "source": "synthetic-tts",
            "notes": "Generated via macOS `say` from a fixed two-speaker script; "
                     "script text is exact ground truth by construction.",
            "audio_file": final_wav.name,
            "duration_sec": duration_sec,
            "segments": [{"speaker": s, "text": t} for s, t in LINES],
        },
        indent=2,
    ))

    # Clean up intermediates
    for p in part_paths:
        p.unlink()
    silence_path.unlink()
    combined_aiff.unlink()
    concat_list.unlink()

    print(f"Wrote {final_wav} ({duration_sec:.1f}s)")


if __name__ == "__main__":
    main()
