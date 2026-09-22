from __future__ import annotations

import re

from transcribe3.shared.types import (
    TranscriptSegment,
    CleaningConfig,
    CleaningMode,
    FillerWordBehavior,
    SegmentFlag,
)
from transcribe3.shared.constants import (
    FILLER_WORDS,
    MIN_SEGMENT_DURATION_SECONDS,
    MAX_SEGMENT_DURATION_SECONDS,
)


# ---------------------------------------------------------------------------
# Public pipeline entry-point
# ---------------------------------------------------------------------------


def clean_transcript(
    segments: list[TranscriptSegment],
    config: CleaningConfig,
) -> list[TranscriptSegment]:
    """Run the full cleaning pipeline according to *config*.

    If mode is VERBATIM the segments are returned unchanged.
    Otherwise the pipeline runs in order:
      normalize_timestamps → normalize_text → handle_false_starts
      → remove_filler_words → flag_crosstalk (when enabled)
    """
    if config.mode == CleaningMode.VERBATIM:
        return segments

    # 1. Timestamp validation (list-level)
    result = normalize_timestamps(segments)

    # 2. Per-segment text transforms
    cleaned: list[TranscriptSegment] = []
    for seg in result:
        seg = seg.model_copy(update={"text": normalize_text(seg.text)})
        seg = handle_false_starts(seg, remove=config.remove_false_starts)
        seg = remove_filler_words(seg, behavior=config.filler_words)
        cleaned.append(seg)

    # 3. List-level crosstalk detection
    if config.handle_crosstalk:
        cleaned = flag_crosstalk(cleaned)

    return cleaned


# ---------------------------------------------------------------------------
# normalize_text
# ---------------------------------------------------------------------------


def normalize_text(text: str) -> str:
    """Clean up raw transcript text with conservative, rule-based transforms."""
    # Strip leading/trailing whitespace
    text = text.strip()

    # Normalize smart/curly double quotes → straight double quotes
    text = text.replace("“", '"').replace("”", '"')

    # Normalize smart/curly single quotes → straight single quotes
    text = text.replace("‘", "'").replace("’", "'")

    # Normalize em-dash variants to spaced em-dash
    # Handle " — " (already spaced) first so we don't double-space later
    text = re.sub(r"\s*—\s*", " — ", text)  # U+2014 em-dash
    text = re.sub(r"\s*--\s*", " — ", text)       # double-hyphen → em-dash

    # Fix OCR substitution: pipe surrounded by word chars → "I"
    text = re.sub(r"(?<=\w)\|(?=\w)", "I", text)
    text = re.sub(r"(?<=\s)\|(?=\w)", "I", text)
    text = re.sub(r"(?<=\w)\|(?=\s)", "I", text)

    # Fix OCR substitution: "0" → "O" in apparent all-caps names/words only
    # Pattern: a run of uppercase letters with an embedded zero
    text = re.sub(
        r"\b([A-Z]+)0([A-Z]*)\b",
        lambda m: m.group(1) + "O" + m.group(2),
        text,
    )

    # Normalize ellipsis variants: four-or-more dots, or spaced dots → "..."
    text = re.sub(r"\.{4,}", "...", text)
    text = re.sub(r"\.\s\.\s\.", "...", text)

    # Collapse multiple spaces into one (do this last)
    text = re.sub(r" {2,}", " ", text)

    return text


# ---------------------------------------------------------------------------
# remove_filler_words
# ---------------------------------------------------------------------------


def remove_filler_words(
    segment: TranscriptSegment,
    behavior: FillerWordBehavior,
) -> TranscriptSegment:
    """Detect and optionally strip filler words from *segment*."""
    if behavior == FillerWordBehavior.OFF:
        return segment

    # Build a regex that matches any filler word as a whole word/phrase.
    # Sort longest first so multi-word fillers match before their sub-words.
    # Negative lookahead: do NOT strip a filler that is immediately followed by
    # end-of-sentence punctuation (.!?) — in that position it carries meaning
    # (e.g. "I think so." — "so" is not a filler here).
    sorted_fillers = sorted(FILLER_WORDS, key=len, reverse=True)
    pattern = re.compile(
        r"(?<!['\w])("
        + "|".join(re.escape(f) for f in sorted_fillers)
        + r")(?!['\w])(?!\s*[.!?])",
        re.IGNORECASE,
    )

    has_filler = bool(pattern.search(segment.text))

    if not has_filler:
        return segment

    # Always add the flag when a filler is detected
    new_flags = list(segment.flags)
    if SegmentFlag.FILLER_WORD not in new_flags:
        new_flags.append(SegmentFlag.FILLER_WORD)

    if behavior == FillerWordBehavior.FLAG:
        return segment.model_copy(update={"flags": new_flags})

    # STRIP: remove filler words and clean up resulting whitespace
    cleaned = pattern.sub("", segment.text)
    cleaned = re.sub(r" {2,}", " ", cleaned).strip()
    # Remove orphaned punctuation that may appear after stripping (e.g. leading comma)
    cleaned = re.sub(r"^\s*[,;]\s*", "", cleaned)
    cleaned = re.sub(r"\s*[,;]\s*$", "", cleaned)
    # Remove orphaned leading false-start fragments exposed by filler removal.
    # Pattern: 1–4 words at the start of the text followed by ' — ' or '...'
    # (the filler removal may have uncovered a fragment with nothing before it).
    cleaned = re.sub(
        r"^(?:\b\w[\w',-]*\b\s+){0,3}\b\w[\w',-]*\b\s+(?:—|\.\.\.)\s+",
        "",
        cleaned,
    )
    cleaned = cleaned.strip()

    return segment.model_copy(update={"text": cleaned, "flags": new_flags})


# ---------------------------------------------------------------------------
# handle_false_starts
# ---------------------------------------------------------------------------


def handle_false_starts(
    segment: TranscriptSegment,
    remove: bool,
) -> TranscriptSegment:
    """Detect false starts (short fragment + em-dash or ellipsis then resumed).

    A false-start is a 1–4 word phrase immediately followed by ` — ` or `...`
    whose first word matches the first word of the continuation, or which is
    followed by any continuation (conservative: just detect the pattern).
    """
    # Pattern: 1–4 words (no punctuation boundaries), then ` — ` or `...`,
    # optionally followed by more text.
    # We match greedily at the start or after sentence punctuation.
    false_start_pattern = re.compile(
        r"((?:\b\w[\w',-]*\b\s+){0,3}\b\w[\w',-]*\b)\s*(?:—|\.\.\.)\s+"
        r"(\S)",  # continuation must have at least one more char
        re.IGNORECASE,
    )

    match = false_start_pattern.search(segment.text)
    if not match:
        return segment

    new_flags = list(segment.flags)
    if SegmentFlag.FALSE_START not in new_flags:
        new_flags.append(SegmentFlag.FALSE_START)

    if not remove:
        return segment.model_copy(update={"flags": new_flags})

    # Remove the false-start fragment (everything up to and including the
    # em-dash / ellipsis), leaving the continuation.
    # Replace the first match only.
    cleaned = false_start_pattern.sub(r"\2", segment.text, count=1)
    cleaned = cleaned.strip()

    return segment.model_copy(update={"text": cleaned, "flags": new_flags})


# ---------------------------------------------------------------------------
# normalize_timestamps
# ---------------------------------------------------------------------------


def normalize_timestamps(
    segments: list[TranscriptSegment],
) -> list[TranscriptSegment]:
    """Flag segments whose duration is outside expected bounds."""
    result: list[TranscriptSegment] = []
    for seg in segments:
        duration = seg.end_time - seg.start_time
        if duration < MIN_SEGMENT_DURATION_SECONDS or duration > MAX_SEGMENT_DURATION_SECONDS:
            new_flags = list(seg.flags)
            if SegmentFlag.SUSPICIOUS_DURATION not in new_flags:
                new_flags.append(SegmentFlag.SUSPICIOUS_DURATION)
            result.append(seg.model_copy(update={"flags": new_flags}))
        else:
            result.append(seg)
    return result


# ---------------------------------------------------------------------------
# flag_crosstalk
# ---------------------------------------------------------------------------


def flag_crosstalk(
    segments: list[TranscriptSegment],
) -> list[TranscriptSegment]:
    """Flag pairs of segments that temporally overlap."""
    if len(segments) < 2:
        return list(segments)

    # Build a mutable copy of flags per segment
    flags: list[list[SegmentFlag]] = [list(seg.flags) for seg in segments]

    for i in range(1, len(segments)):
        if segments[i].start_time < segments[i - 1].end_time:
            # Overlap detected — flag both
            if SegmentFlag.CROSSTALK not in flags[i - 1]:
                flags[i - 1].append(SegmentFlag.CROSSTALK)
            if SegmentFlag.CROSSTALK not in flags[i]:
                flags[i].append(SegmentFlag.CROSSTALK)

    return [
        seg.model_copy(update={"flags": f})
        for seg, f in zip(segments, flags)
    ]


# ---------------------------------------------------------------------------
# normalize_speaker_labels
# ---------------------------------------------------------------------------

# Maps normalised lowercase variants → canonical form
_SPEAKER_LABEL_MAP: dict[str, str] = {
    # Speaker 1 variants
    "speaker 1": "Speaker_1",
    "speaker1": "Speaker_1",
    "s1": "Speaker_1",
    "speaker_1": "Speaker_1",
    # Speaker 2 variants
    "speaker 2": "Speaker_2",
    "speaker2": "Speaker_2",
    "s2": "Speaker_2",
    "speaker_2": "Speaker_2",
    # Interviewer
    "interviewer": "Interviewer",
    # Interviewee
    "interviewee": "Interviewee",
}


def normalize_speaker_labels(
    segments: list[TranscriptSegment],
) -> list[TranscriptSegment]:
    """Normalise speaker label variants to a consistent anonymous form."""
    result: list[TranscriptSegment] = []
    for seg in segments:
        key = seg.speaker.anonymous_id.strip().lower()
        canonical = _SPEAKER_LABEL_MAP.get(key)
        if canonical is not None and canonical != seg.speaker.anonymous_id:
            new_speaker = seg.speaker.model_copy(update={"anonymous_id": canonical})
            result.append(seg.model_copy(update={"speaker": new_speaker}))
        else:
            result.append(seg)
    return result
