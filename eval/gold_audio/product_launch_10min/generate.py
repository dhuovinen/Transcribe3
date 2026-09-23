"""Generates the synthetic ~10-minute three-speaker, semi-noisy gold case.

Ground truth: the LINES list below is the exact transcript. Each line is
synthesized individually (so speaker turns are unambiguous) via macOS `say`,
stitched into one WAV with ffmpeg, then mixed with a low-level brown-noise
bed to simulate a moderately noisy room (HVAC/office hum) without harming
intelligibility — the gold transcript stays exact by construction regardless
of the noise layer, since the noise is mixed in after transcription-grade
speech is already fixed.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

OUT_DIR = Path(__file__).parent
# Three distinct accents/genders for reliably separable diarization ground truth.
VOICES = {"Priya": "Samantha", "Marcus": "Daniel", "Elena": "Karen"}

# Noise bed level relative to speech — "semi-noisy": clearly audible
# throughout, but never obscures a word. Tuned by ear against the mix.
NOISE_VOLUME = 0.05

# (speaker, text) — a three-person cross-functional launch-readiness review,
# ~10 minutes at natural speaking pace including pauses between turns.
LINES = [
    ("Priya", "Okay, let's get started. This is our go, no-go review for the Meridian launch. Marcus, Elena, thanks for making time."),
    ("Marcus", "Happy to be here. I've got the engineering status ready whenever you want it."),
    ("Elena", "Same on the marketing side. I'll follow after Marcus."),
    ("Priya", "Perfect. Marcus, why don't you start with where the build stands."),
    ("Marcus", "Sure. As of this morning, the release candidate is code complete and it's been in staging for four days."),
    ("Priya", "And how's it holding up?"),
    ("Marcus", "Mostly well. We found two P2 bugs during regression, both already fixed and verified."),
    ("Priya", "Any P1s or P0s?"),
    ("Marcus", "One P1, still open. It's an intermittent crash on the checkout confirmation screen, only on older Android devices."),
    ("Priya", "Do we understand the cause yet?"),
    ("Marcus", "We think so. It looks like a race condition when the payment confirmation comes back before the animation finishes."),
    ("Elena", "How intermittent are we talking? Once in a hundred sessions, once in a thousand?"),
    ("Marcus", "Closer to one in three hundred, based on the crash reporting from the beta cohort."),
    ("Priya", "That's not nothing. What's the fix estimate?"),
    ("Marcus", "Our best guess is a day of work plus half a day of testing, so realistically ready by tomorrow evening."),
    ("Priya", "Okay. Let's treat that as a blocker for now and revisit at the end of this meeting."),
    ("Marcus", "Agreed, that's fair."),
    ("Priya", "What about performance? Last time we talked, cold start was still a concern."),
    ("Marcus", "Good news there. We shaved off about four hundred milliseconds by lazy loading the onboarding illustrations."),
    ("Priya", "What's cold start sitting at now?"),
    ("Marcus", "Around one point eight seconds on our reference device, down from two point three."),
    ("Elena", "That's a nice win. Does that apply evenly across low end devices too, or mostly flagship phones?"),
    ("Marcus", "Mostly flagship so far. We haven't finished profiling on the budget Android tier yet."),
    ("Priya", "Can we get that data before the launch decision?"),
    ("Marcus", "I can have preliminary numbers by tomorrow morning, full numbers by end of day tomorrow."),
    ("Priya", "Let's aim for the preliminary numbers, that should be enough to make the call."),
    ("Marcus", "Sounds good, I'll prioritize that first thing."),
    ("Priya", "Anything else on engineering before we move to marketing?"),
    ("Marcus", "Just one thing. The analytics team asked for two new events to be added before launch, and those are already merged."),
    ("Priya", "Great, thanks Marcus. Elena, over to you."),
    ("Elena", "Thanks. On the marketing side, the campaign assets are finished and approved by legal as of yesterday."),
    ("Priya", "That's ahead of schedule, nice."),
    ("Elena", "We got lucky, legal turned it around in two days instead of the usual week."),
    ("Marcus", "Did the messaging change at all during legal review?"),
    ("Elena", "Only minor wording. We had to soften one claim about battery savings to say, quote, up to thirty percent, unquote."),
    ("Priya", "Makes sense, that's safer language anyway. What's the plan for launch day itself?"),
    ("Elena", "We're doing a staggered rollout. Email to the waitlist at nine AM, social posts at ten, and a press embargo lifts at noon."),
    ("Priya", "How big is the waitlist at this point?"),
    ("Elena", "Just under forty thousand people, which is about twenty percent higher than we projected in August."),
    ("Marcus", "That's a good problem to have. Are we confident the backend can handle a spike from that many people at once?"),
    ("Priya", "Good question. Marcus, do we have load testing numbers for that scenario?"),
    ("Marcus", "We load tested up to sixty thousand concurrent sign ups last week and it held, but I'd want to rerun it since the checkout fix hasn't landed."),
    ("Priya", "Let's rerun load testing tomorrow once the checkout fix is in."),
    ("Marcus", "Will do."),
    ("Elena", "One more thing on my side. We have three press outlets confirmed for early access briefings this week."),
    ("Priya", "Which outlets?"),
    ("Elena", "TechDaily, the Morning Ledger, and a smaller newsletter called Signal Weekly that's popular with our target audience."),
    ("Priya", "Good spread. Any concerns from them so far?"),
    ("Elena", "TechDaily asked about pricing changes for existing customers, so we should make sure support has clean talking points."),
    ("Priya", "Let's make sure that's in the support brief. Speaking of which, where do we stand on support readiness?"),
    ("Elena", "I don't own that directly, but I know the support team finished their training session yesterday."),
    ("Marcus", "I can speak to the technical side. We gave them a runbook for the top ten expected issues, including the checkout bug once it's fixed."),
    ("Priya", "Good. Let's make sure that runbook gets updated the moment the fix ships, not after."),
    ("Marcus", "Understood, I'll own that update myself so it doesn't slip."),
    ("Priya", "Thank you. Let's talk about the launch date itself. Original target was this Thursday."),
    ("Elena", "From a marketing standpoint, Thursday still works. All the assets are locked and the press embargo is already scheduled."),
    ("Marcus", "From engineering, I'd feel more comfortable with Friday, just to give the checkout fix a full day of soak time after it ships."),
    ("Priya", "That's a reasonable ask. Elena, how disruptive would a one day slip be for marketing?"),
    ("Elena", "Not too bad. We'd need to reschedule the press embargo and resend one calendar invite, but nothing structural breaks."),
    ("Priya", "Okay, let's tentatively move to Friday, pending the checkout fix landing cleanly tomorrow."),
    ("Marcus", "That works for me."),
    ("Elena", "Agreed, I'll start adjusting the press calendar today so it's ready either way."),
    ("Priya", "Let's talk risk register quickly before we wrap. Marcus, top risk from your side?"),
    ("Marcus", "Still the checkout crash. Second would be the unknown performance on budget Android devices."),
    ("Priya", "And a mitigation for the Android question if the numbers come back bad?"),
    ("Marcus", "Worst case, we feature flag the new onboarding illustrations off for lower end devices and keep the old flow there."),
    ("Priya", "Good, that's a reasonable fallback. Elena, top risk from marketing?"),
    ("Elena", "Honestly, it's the waitlist size. If sign up traffic spikes harder than expected, a rocky first hour could hurt press sentiment."),
    ("Priya", "That lines up with wanting fresh load test numbers. Let's make sure those are done before Friday regardless of which day we launch."),
    ("Marcus", "Agreed, I'll treat that as non negotiable before go live."),
    ("Priya", "Good. Let's also touch on the rollback plan in case something goes wrong on launch day."),
    ("Marcus", "We can roll back the client release within about fifteen minutes since it's a staged rollout, not a hard cutover."),
    ("Priya", "And on the backend?"),
    ("Marcus", "Backend changes are backward compatible with the previous client version, so a rollback there is low risk."),
    ("Elena", "What would trigger a rollback decision, and who makes that call on launch day?"),
    ("Priya", "Good question. Let's say crash rate above two percent or checkout failure rate above five percent triggers an automatic page to me and Marcus."),
    ("Marcus", "That threshold matches what we used for the last major release, so it's a reasonable bar."),
    ("Priya", "Agreed. Let's put that in writing in the launch runbook today so there's no ambiguity on the day."),
    ("Elena", "I can help draft that section if it's useful, I've written similar runbooks before."),
    ("Priya", "That would be great, thank you."),
    ("Marcus", "One last engineering item. We should decide who's on call across the launch window, especially if we move to Friday."),
    ("Priya", "Let's plan for you and one other engineer during business hours, plus normal on call coverage overnight."),
    ("Marcus", "I'll pull in Renata for the daytime shift, she's been closest to the checkout code this sprint."),
    ("Priya", "Perfect, please loop her in today so she has context ahead of time."),
    ("Marcus", "Will do, I'll message her right after this call."),
    ("Priya", "Elena, anything else from marketing before we close out?"),
    ("Elena", "Just a reminder that the influencer partnerships go live the same day as press, so timing really does matter here."),
    ("Priya", "Understood, that's a strong argument for locking the date firmly by tomorrow afternoon."),
    ("Elena", "Agreed, tomorrow afternoon works well for us."),
    ("Priya", "Alright, let's summarize. Checkout fix ships and is verified tomorrow. Fresh load test and budget device numbers come in tomorrow too."),
    ("Marcus", "And the support runbook gets updated the moment the fix ships, not after."),
    ("Elena", "And I'll have the press calendar ready to shift to Friday, plus a draft of the rollback section for the runbook."),
    ("Priya", "Great. Let's reconvene tomorrow at the same time to make the final go, no-go call."),
    ("Marcus", "Works for me."),
    ("Elena", "Same here, talk tomorrow."),
    ("Priya", "Thanks both, this was a productive session."),
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

    speech_wav = OUT_DIR / "_speech.wav"
    subprocess.run(
        ["ffmpeg", "-y", "-i", str(combined_aiff), "-ar", "16000", "-ac", "1", str(speech_wav)],
        check=True, capture_output=True,
    )

    # Mix in a low-level brown-noise bed for the whole clip's duration —
    # brown noise reads as a room/HVAC hum rather than harsh static, so it
    # stresses the pipeline's noise robustness without masking any word.
    final_wav = OUT_DIR / "audio.wav"
    subprocess.run(
        [
            "ffmpeg", "-y",
            "-i", str(speech_wav),
            "-f", "lavfi", "-i", "anoisesrc=color=brown:amplitude=1:sample_rate=16000",
            "-filter_complex",
            f"[1:a]volume={NOISE_VOLUME}[noise];[0:a][noise]amix=inputs=2:duration=first:dropout_transition=0[out]",
            "-map", "[out]", "-ar", "16000", "-ac", "1", str(final_wav),
        ],
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
            "notes": "Generated via macOS `say` from a fixed three-speaker script (US/GB/AU "
                     "voices for separable diarization ground truth), mixed with a low-level "
                     f"brown-noise bed (relative volume {NOISE_VOLUME}) to simulate a "
                     "semi-noisy room. Script text is exact ground truth by construction — "
                     "the noise layer is mixed in after speech synthesis and never alters it.",
            "audio_file": final_wav.name,
            "duration_sec": duration_sec,
            "speaker_count": len(VOICES),
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
    speech_wav.unlink()

    print(f"Wrote {final_wav} ({duration_sec:.1f}s, {duration_sec / 60:.1f} min)")


if __name__ == "__main__":
    main()
