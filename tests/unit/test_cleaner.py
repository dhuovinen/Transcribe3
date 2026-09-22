"""Unit tests for transcribe3.core.cleaner — self-contained, no conftest needed."""
from __future__ import annotations

import pytest

from transcribe3.shared.types import (
    CleaningConfig,
    CleaningMode,
    FillerWordBehavior,
    SegmentFlag,
    SpeakerLabel,
    TranscriptSegment,
)
from transcribe3.core.cleaner import (
    clean_transcript,
    flag_crosstalk,
    handle_false_starts,
    normalize_speaker_labels,
    normalize_text,
    normalize_timestamps,
    remove_filler_words,
)


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def make_segment(
    text: str = "Hello world.",
    start: float = 0.0,
    end: float = 2.0,
    speaker_id: str = "Speaker_1",
    flags: list[SegmentFlag] | None = None,
) -> TranscriptSegment:
    return TranscriptSegment(
        start_time=start,
        end_time=end,
        speaker=SpeakerLabel(anonymous_id=speaker_id),
        text=text,
        flags=flags or [],
    )


# ---------------------------------------------------------------------------
# normalize_text
# ---------------------------------------------------------------------------


def test_normalize_text_strips_whitespace():
    assert normalize_text("  hello  ") == "hello"
    assert normalize_text("\tsome text\n") == "some text"


def test_normalize_text_collapses_spaces():
    assert normalize_text("too   many    spaces") == "too many spaces"
    assert normalize_text("a  b  c") == "a b c"


def test_normalize_text_straightens_quotes():
    assert normalize_text("“hello”") == '"hello"'  # curly double quotes
    assert normalize_text("‘it’s") == "'it's"      # curly single quotes


def test_normalize_text_normalizes_emdash():
    # em-dash without spaces should get spaces
    assert normalize_text("word—word") == "word — word"
    # already-spaced em-dash should stay as-is (no double space)
    assert normalize_text("word — word") == "word — word"
    # double-hyphen should become spaced em-dash
    assert normalize_text("word--word") == "word — word"


def test_normalize_text_normalizes_ellipsis():
    assert normalize_text("wait....") == "wait..."
    assert normalize_text("wait. . .") == "wait..."
    assert normalize_text("wait.....end") == "wait...end"


# ---------------------------------------------------------------------------
# remove_filler_words
# ---------------------------------------------------------------------------


def test_remove_filler_words_off_leaves_text_unchanged():
    seg = make_segment(text="Um, I think so.")
    result = remove_filler_words(seg, behavior=FillerWordBehavior.OFF)
    assert result.text == "Um, I think so."
    assert SegmentFlag.FILLER_WORD not in result.flags


def test_remove_filler_words_flag_adds_flag_preserves_text():
    seg = make_segment(text="Um, I think so.")
    result = remove_filler_words(seg, behavior=FillerWordBehavior.FLAG)
    assert result.text == "Um, I think so."
    assert SegmentFlag.FILLER_WORD in result.flags


def test_remove_filler_words_strip_removes_and_flags():
    seg = make_segment(text="Um, I think so.")
    result = remove_filler_words(seg, behavior=FillerWordBehavior.STRIP)
    assert "um" not in result.text.lower()
    assert SegmentFlag.FILLER_WORD in result.flags
    # Core meaning should survive
    assert "I think so" in result.text


def test_remove_filler_words_no_filler_no_change():
    seg = make_segment(text="The report is ready.")
    result = remove_filler_words(seg, behavior=FillerWordBehavior.STRIP)
    assert result.text == "The report is ready."
    assert SegmentFlag.FILLER_WORD not in result.flags


def test_remove_filler_words_case_insensitive():
    seg = make_segment(text="UH, let me check.")
    result = remove_filler_words(seg, behavior=FillerWordBehavior.STRIP)
    assert "uh" not in result.text.lower()
    assert SegmentFlag.FILLER_WORD in result.flags


# ---------------------------------------------------------------------------
# handle_false_starts
# ---------------------------------------------------------------------------


def test_handle_false_starts_flag_mode():
    seg = make_segment(text="I think — I think this is right.")
    result = handle_false_starts(seg, remove=False)
    assert result.text == "I think — I think this is right."
    assert SegmentFlag.FALSE_START in result.flags


def test_handle_false_starts_remove_mode():
    seg = make_segment(text="I think — I think this is right.")
    result = handle_false_starts(seg, remove=True)
    assert SegmentFlag.FALSE_START in result.flags
    # The false-start fragment before the dash should be gone
    assert result.text.count("—") == 0 or not result.text.startswith("I think —")
    # Core continuation must remain
    assert "this is right" in result.text


def test_handle_false_starts_ellipsis_variant():
    seg = make_segment(text="The report... the report shows growth.")
    result = handle_false_starts(seg, remove=False)
    assert SegmentFlag.FALSE_START in result.flags


def test_handle_false_starts_no_false_start():
    seg = make_segment(text="This is a clean sentence.")
    result = handle_false_starts(seg, remove=True)
    assert result.text == "This is a clean sentence."
    assert SegmentFlag.FALSE_START not in result.flags


# ---------------------------------------------------------------------------
# normalize_timestamps
# ---------------------------------------------------------------------------


def test_normalize_timestamps_flags_short_segment():
    # 0.05 s is below MIN_SEGMENT_DURATION_SECONDS (0.1)
    seg = make_segment(start=0.0, end=0.05)
    result = normalize_timestamps([seg])
    assert SegmentFlag.SUSPICIOUS_DURATION in result[0].flags


def test_normalize_timestamps_flags_long_segment():
    # 61 s is above MAX_SEGMENT_DURATION_SECONDS (60.0)
    seg = make_segment(start=0.0, end=61.0)
    result = normalize_timestamps([seg])
    assert SegmentFlag.SUSPICIOUS_DURATION in result[0].flags


def test_normalize_timestamps_normal_segment_not_flagged():
    seg = make_segment(start=0.0, end=5.0)
    result = normalize_timestamps([seg])
    assert SegmentFlag.SUSPICIOUS_DURATION not in result[0].flags


def test_normalize_timestamps_does_not_modify_times():
    seg = make_segment(start=1.0, end=0.05 + 1.0)
    result = normalize_timestamps([seg])
    assert result[0].start_time == 1.0
    assert result[0].end_time == pytest.approx(1.05)


# ---------------------------------------------------------------------------
# flag_crosstalk
# ---------------------------------------------------------------------------


def test_flag_crosstalk_detects_overlap():
    seg1 = make_segment(start=0.0, end=3.0)
    seg2 = make_segment(start=2.5, end=5.0)  # starts before seg1 ends
    result = flag_crosstalk([seg1, seg2])
    assert SegmentFlag.CROSSTALK in result[0].flags
    assert SegmentFlag.CROSSTALK in result[1].flags


def test_flag_crosstalk_no_overlap():
    seg1 = make_segment(start=0.0, end=2.0)
    seg2 = make_segment(start=2.0, end=4.0)  # starts exactly when seg1 ends
    result = flag_crosstalk([seg1, seg2])
    assert SegmentFlag.CROSSTALK not in result[0].flags
    assert SegmentFlag.CROSSTALK not in result[1].flags


def test_flag_crosstalk_three_segments_only_overlapping_pair_flagged():
    seg1 = make_segment(start=0.0, end=2.0)
    seg2 = make_segment(start=1.5, end=3.5)  # overlaps seg1
    seg3 = make_segment(start=4.0, end=6.0)  # no overlap
    result = flag_crosstalk([seg1, seg2, seg3])
    assert SegmentFlag.CROSSTALK in result[0].flags
    assert SegmentFlag.CROSSTALK in result[1].flags
    assert SegmentFlag.CROSSTALK not in result[2].flags


# ---------------------------------------------------------------------------
# clean_transcript (integration of pipeline)
# ---------------------------------------------------------------------------


def test_clean_transcript_verbatim_returns_unchanged():
    segments = [
        make_segment(text="Um, so I was like, you know, going there."),
        make_segment(text="  extra   spaces  ", start=3.0, end=5.0),
    ]
    config = CleaningConfig(
        mode=CleaningMode.VERBATIM,
        filler_words=FillerWordBehavior.STRIP,
    )
    result = clean_transcript(segments, config)
    # Should be identical objects / equal values — no mutation
    assert result[0].text == segments[0].text
    assert result[1].text == segments[1].text
    assert SegmentFlag.FILLER_WORD not in result[0].flags


def test_clean_transcript_standard_applies_pipeline():
    segments = [
        make_segment(
            text="  Um, I—I think so.  ",  # has filler + em-dash + whitespace
            start=0.0,
            end=2.0,
        ),
    ]
    config = CleaningConfig(
        mode=CleaningMode.STANDARD,
        filler_words=FillerWordBehavior.STRIP,
        remove_false_starts=False,
        handle_crosstalk=True,
    )
    result = clean_transcript(segments, config)
    seg = result[0]
    # Text was stripped of leading/trailing whitespace
    assert not seg.text.startswith(" ")
    assert not seg.text.endswith(" ")
    # "Um" was removed (filler strip) and flagged
    assert "um" not in seg.text.lower()
    assert SegmentFlag.FILLER_WORD in seg.flags
    # em-dash normalised to spaced form
    assert "—" not in seg.text  # raw em-dash gone


def test_clean_transcript_crosstalk_flagged():
    segments = [
        make_segment(start=0.0, end=3.0, text="First speaker."),
        make_segment(start=2.0, end=5.0, text="Second speaker."),
    ]
    config = CleaningConfig(mode=CleaningMode.STANDARD, handle_crosstalk=True)
    result = clean_transcript(segments, config)
    assert SegmentFlag.CROSSTALK in result[0].flags
    assert SegmentFlag.CROSSTALK in result[1].flags


def test_clean_transcript_crosstalk_disabled():
    segments = [
        make_segment(start=0.0, end=3.0, text="First."),
        make_segment(start=2.0, end=5.0, text="Second."),
    ]
    config = CleaningConfig(mode=CleaningMode.STANDARD, handle_crosstalk=False)
    result = clean_transcript(segments, config)
    assert SegmentFlag.CROSSTALK not in result[0].flags
    assert SegmentFlag.CROSSTALK not in result[1].flags


# ---------------------------------------------------------------------------
# normalize_speaker_labels
# ---------------------------------------------------------------------------


def test_normalize_speaker_labels_normalizes_variants():
    """SPEAKER 1, speaker1, S1, SPEAKER_1 all become Speaker_1."""
    variants = ["SPEAKER 1", "speaker1", "S1", "SPEAKER_1"]
    for variant in variants:
        seg = make_segment(speaker_id=variant)
        result = normalize_speaker_labels([seg])
        assert result[0].speaker.anonymous_id == "Speaker_1", (
            f"Expected 'Speaker_1' for variant {variant!r}, "
            f"got {result[0].speaker.anonymous_id!r}"
        )


def test_normalize_speaker_labels_normalizes_speaker2_variants():
    """SPEAKER 2, speaker2, S2, SPEAKER_2 all become Speaker_2."""
    variants = ["SPEAKER 2", "speaker2", "S2", "SPEAKER_2"]
    for variant in variants:
        seg = make_segment(speaker_id=variant)
        result = normalize_speaker_labels([seg])
        assert result[0].speaker.anonymous_id == "Speaker_2", (
            f"Expected 'Speaker_2' for variant {variant!r}, "
            f"got {result[0].speaker.anonymous_id!r}"
        )


def test_normalize_speaker_labels_unknown_variant_unchanged():
    """A label not in the map is returned as-is."""
    seg = make_segment(speaker_id="UNKNOWN_PERSON")
    result = normalize_speaker_labels([seg])
    assert result[0].speaker.anonymous_id == "UNKNOWN_PERSON"


def test_normalize_speaker_labels_already_canonical_unchanged():
    """A label that is already canonical is not modified."""
    seg = make_segment(speaker_id="Speaker_1")
    result = normalize_speaker_labels([seg])
    assert result[0].speaker.anonymous_id == "Speaker_1"


def test_normalize_speaker_labels_interviewer():
    seg = make_segment(speaker_id="INTERVIEWER")
    result = normalize_speaker_labels([seg])
    assert result[0].speaker.anonymous_id == "Interviewer"


# ---------------------------------------------------------------------------
# clean_transcript — full pipeline on shared fixtures
# ---------------------------------------------------------------------------


def test_clean_transcript_full_pipeline(sample_segments, default_config):
    """Run the full pipeline on the shared sample_segments fixture.

    Verifies:
    - Output count matches input count (no segments lost).
    - No exceptions raised.
    - Pipeline produces at least some non-trivial output.
    """
    result = clean_transcript(sample_segments, default_config)
    assert len(result) == len(sample_segments)
    # All items are still TranscriptSegment instances
    for seg in result:
        assert isinstance(seg, TranscriptSegment)
    # Pipeline ran: text was at minimum normalized (no leading/trailing spaces)
    for seg in result:
        assert seg.text == seg.text.strip()
