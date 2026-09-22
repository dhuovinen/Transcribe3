from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

from transcribe3.core.attributor import (
    _attribute_window,
    attribute_speakers,
    build_attribution_prompt,
    parse_attribution_response,
    score_attribution_confidence,
)
from transcribe3.core.llm.client import LLMUnavailableError
from transcribe3.shared.types import CleaningConfig, SegmentFlag, SpeakerLabel, TranscriptSegment


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_segment(
    seg_id: str,
    anonymous_id: str = "SPEAKER_00",
    text: str = "Hello world",
    confidence: float = 1.0,
    flags: list[SegmentFlag] | None = None,
) -> TranscriptSegment:
    return TranscriptSegment(
        id=seg_id,
        start_time=0.0,
        end_time=1.0,
        speaker=SpeakerLabel(anonymous_id=anonymous_id),
        text=text,
        confidence=confidence,
        flags=flags or [],
    )


def make_config(threshold: float = 0.6) -> CleaningConfig:
    return CleaningConfig(low_confidence_threshold=threshold)


# ---------------------------------------------------------------------------
# build_attribution_prompt
# ---------------------------------------------------------------------------


def test_build_attribution_prompt_is_deterministic():
    segs = [
        make_segment("id-1", anonymous_id="SPEAKER_00", text="Hi there"),
        make_segment("id-2", anonymous_id="SPEAKER_01", text="How are you?"),
    ]
    prompt_a = build_attribution_prompt(segs)
    prompt_b = build_attribution_prompt(segs)
    assert prompt_a == prompt_b


def test_build_attribution_prompt_includes_all_segment_ids():
    seg_ids = ["seg-aaa", "seg-bbb", "seg-ccc"]
    segs = [make_segment(sid) for sid in seg_ids]
    prompt = build_attribution_prompt(segs)
    for sid in seg_ids:
        assert sid in prompt


# ---------------------------------------------------------------------------
# parse_attribution_response
# ---------------------------------------------------------------------------


def test_parse_attribution_response_valid_json_updates_segments():
    segs = [
        make_segment("id-1", anonymous_id="SPEAKER_00"),
        make_segment("id-2", anonymous_id="SPEAKER_00"),
    ]
    llm_output = json.dumps([
        {"id": "id-1", "speaker": "SPEAKER_01", "confidence": 0.9},
        {"id": "id-2", "speaker": "SPEAKER_00", "confidence": 0.8},
    ])
    result = parse_attribution_response(llm_output, segs)

    assert result[0].speaker.anonymous_id == "SPEAKER_01"
    assert result[0].confidence == pytest.approx(0.9)
    assert result[1].speaker.anonymous_id == "SPEAKER_00"
    assert result[1].confidence == pytest.approx(0.8)


def test_parse_attribution_response_malformed_json_returns_original_with_error_flag():
    segs = [make_segment("id-1"), make_segment("id-2")]
    result = parse_attribution_response("this is not json {{", segs)

    assert len(result) == 2
    for seg in result:
        assert SegmentFlag.ATTRIBUTION_PARSE_ERROR in seg.flags
        assert seg.confidence == pytest.approx(0.0)
    # Original text and ids preserved
    assert result[0].id == "id-1"
    assert result[1].id == "id-2"


def test_parse_attribution_response_unknown_segment_id_ignored():
    segs = [make_segment("id-real")]
    llm_output = json.dumps([
        {"id": "id-real", "speaker": "SPEAKER_01", "confidence": 0.85},
        {"id": "id-ghost", "speaker": "SPEAKER_99", "confidence": 0.5},
    ])
    result = parse_attribution_response(llm_output, segs)

    assert len(result) == 1
    assert result[0].id == "id-real"
    assert result[0].speaker.anonymous_id == "SPEAKER_01"


def test_parse_attribution_response_missing_segment_gets_zero_confidence():
    segs = [
        make_segment("id-present"),
        make_segment("id-missing"),
    ]
    llm_output = json.dumps([
        {"id": "id-present", "speaker": "SPEAKER_00", "confidence": 0.95},
        # id-missing not in response
    ])
    result = parse_attribution_response(llm_output, segs)

    present = next(s for s in result if s.id == "id-present")
    missing = next(s for s in result if s.id == "id-missing")

    assert present.confidence == pytest.approx(0.95)
    assert missing.confidence == pytest.approx(0.0)
    # Missing segment should not have error flag — it just has no entry
    assert SegmentFlag.ATTRIBUTION_PARSE_ERROR not in missing.flags


# ---------------------------------------------------------------------------
# score_attribution_confidence
# ---------------------------------------------------------------------------


def test_score_attribution_confidence_adds_low_confidence_flag():
    seg = make_segment("id-1", confidence=0.4)
    result = score_attribution_confidence(seg, threshold=0.6)
    assert SegmentFlag.LOW_CONFIDENCE in result.flags


def test_score_attribution_confidence_above_threshold_no_flag():
    seg = make_segment("id-1", confidence=0.9)
    result = score_attribution_confidence(seg, threshold=0.6)
    assert SegmentFlag.LOW_CONFIDENCE not in result.flags


def test_score_attribution_confidence_does_not_duplicate_flag():
    seg = make_segment("id-1", confidence=0.2, flags=[SegmentFlag.LOW_CONFIDENCE])
    result = score_attribution_confidence(seg, threshold=0.6)
    assert result.flags.count(SegmentFlag.LOW_CONFIDENCE) == 1


# ---------------------------------------------------------------------------
# _attribute_window
# ---------------------------------------------------------------------------


def test_attribute_window_calls_llm_and_updates_segments():
    segs = [
        make_segment("id-1", anonymous_id="SPEAKER_00"),
        make_segment("id-2", anonymous_id="SPEAKER_01"),
    ]
    llm_response = json.dumps([
        {"id": "id-1", "speaker": "SPEAKER_01", "confidence": 0.88},
        {"id": "id-2", "speaker": "SPEAKER_00", "confidence": 0.75},
    ])

    mock_client = MagicMock()
    mock_client.complete.return_value = llm_response

    config = make_config()
    result, unavailable = _attribute_window(segs, config, mock_client, model="llama3")

    mock_client.complete.assert_called_once()
    assert unavailable is False
    assert result[0].speaker.anonymous_id == "SPEAKER_01"
    assert result[0].confidence == pytest.approx(0.88)
    assert result[1].speaker.anonymous_id == "SPEAKER_00"
    assert result[1].confidence == pytest.approx(0.75)


def test_attribute_window_llm_unavailable_degrades_gracefully():
    segs = [make_segment("id-1"), make_segment("id-2")]

    mock_client = MagicMock()
    mock_client.complete.side_effect = LLMUnavailableError("Ollama is not running")

    config = make_config()
    result, unavailable = _attribute_window(segs, config, mock_client, model="llama3")

    # Must not raise — returns original segments with error flags and zero confidence
    assert unavailable is True
    assert len(result) == 2
    for seg in result:
        assert seg.confidence == pytest.approx(0.0)
        assert SegmentFlag.ATTRIBUTION_PARSE_ERROR in seg.flags


# ---------------------------------------------------------------------------
# attribute_speakers — full pipeline with mock LLM
# ---------------------------------------------------------------------------


def test_attribute_speakers_full_pipeline(mock_llm_client):
    """attribute_speakers runs on 5 segments using mock_llm_client.

    Verifies:
    - All segments are returned (no segments lost).
    - Each segment has a confidence score assigned.
    - No exception is raised.
    """
    segs = [
        make_segment(f"id-{i}", anonymous_id="SPEAKER_00", text=f"Utterance {i}.")
        for i in range(5)
    ]
    config = make_config(threshold=0.6)
    result = attribute_speakers(segs, config, mock_llm_client, model="llama3")

    assert len(result) == len(segs)
    for seg in result:
        assert isinstance(seg, TranscriptSegment)
        # mock returns 0.9 confidence for every segment
        assert seg.confidence == pytest.approx(0.9)
        # High confidence — should NOT have LOW_CONFIDENCE flag
        assert SegmentFlag.LOW_CONFIDENCE not in seg.flags


def test_attribute_speakers_empty_list(mock_llm_client):
    """attribute_speakers returns immediately on empty input."""
    config = make_config()
    result = attribute_speakers([], config, mock_llm_client, model="llama3")
    assert result == []
    mock_llm_client.complete.assert_not_called()


def test_attribute_speakers_flags_low_confidence():
    """Segments returned with confidence below threshold get LOW_CONFIDENCE flag."""
    segs = [make_segment("id-1", anonymous_id="SPEAKER_00")]

    # LLM returns confidence 0.3, which is below default threshold 0.6
    low_conf_response = json.dumps([{"id": "id-1", "speaker": "SPEAKER_00", "confidence": 0.3}])
    mock_client = MagicMock()
    mock_client.complete.return_value = low_conf_response

    config = make_config(threshold=0.6)
    result = attribute_speakers(segs, config, mock_client, model="llama3")

    assert len(result) == 1
    assert result[0].confidence == pytest.approx(0.3)
    assert SegmentFlag.LOW_CONFIDENCE in result[0].flags


def test_attribute_speakers_multi_window_no_segments_lost(mock_llm_client):
    """attribute_speakers handles >10 segments (multi-window path) without losing any."""
    # _WINDOW_SIZE is 10, _OVERLAP is 2 — 12 segments forces a second window
    segs = [
        make_segment(f"id-{i:02d}", anonymous_id="SPEAKER_00", text=f"Utterance {i}.")
        for i in range(12)
    ]
    config = make_config(threshold=0.6)
    result = attribute_speakers(segs, config, mock_llm_client, model="llama3")

    assert len(result) == 12
    # All IDs present
    result_ids = {s.id for s in result}
    input_ids = {s.id for s in segs}
    assert result_ids == input_ids


def test_attribute_speakers_raises_when_backend_unreachable_for_every_window():
    """If the LLM never answers a single window, don't silently return all-zero
    confidence — raise so callers can surface a real warning instead of a mean
    confidence that quietly drops to 0% with no explanation."""
    segs = [make_segment("id-1"), make_segment("id-2")]
    mock_client = MagicMock()
    mock_client.complete.side_effect = LLMUnavailableError("olmx is not running")

    config = make_config()
    with pytest.raises(LLMUnavailableError):
        attribute_speakers(segs, config, mock_client, model="llama3")


def test_attribute_speakers_does_not_raise_on_partial_outage(mock_llm_client):
    """If only some windows fail (e.g. the backend restarts mid-run), keep going —
    only a *complete* outage should abort the run."""
    segs = [
        make_segment(f"id-{i:02d}", anonymous_id="SPEAKER_00", text=f"Utterance {i}.")
        for i in range(12)  # 12 segments -> 2 windows (see multi-window test above)
    ]
    good_complete = mock_llm_client.complete.side_effect
    mock_llm_client.complete.side_effect = [
        LLMUnavailableError("temporarily down"),
        good_complete(build_attribution_prompt(segs[8:12]), "llama3"),
    ]

    config = make_config(threshold=0.6)
    result = attribute_speakers(segs, config, mock_llm_client, model="llama3")

    assert len(result) == 12
    # First window's segments degraded gracefully rather than aborting the run
    degraded_ids = {seg.id for seg in result[:8] if SegmentFlag.ATTRIBUTION_PARSE_ERROR in seg.flags}
    assert degraded_ids == {s.id for s in segs[:8]}


# ---------------------------------------------------------------------------
# parse_attribution_response — edge cases
# ---------------------------------------------------------------------------


def test_parse_attribution_response_non_dict_item_in_list_is_skipped():
    """Non-dict items inside the JSON array are silently skipped; segments get zero confidence."""
    segs = [make_segment("id-1")]
    # The list contains a non-dict item — id-1 will have no matching entry
    llm_output = json.dumps(["not_a_dict", 42, None])
    result = parse_attribution_response(llm_output, segs)
    # Only one segment, not found in response → zero confidence, no error flag
    assert len(result) == 1
    assert result[0].confidence == pytest.approx(0.0)
    assert SegmentFlag.ATTRIBUTION_PARSE_ERROR not in result[0].flags


def test_parse_attribution_response_item_without_id_is_skipped():
    """Items missing the 'id' key are silently skipped."""
    segs = [make_segment("id-real")]
    # Item has no "id" key
    llm_output = json.dumps([{"speaker": "SPEAKER_00", "confidence": 0.9}])
    result = parse_attribution_response(llm_output, segs)
    assert len(result) == 1
    assert result[0].confidence == pytest.approx(0.0)


def test_parse_attribution_response_non_list_json_returns_error_flag():
    """If the LLM returns a JSON object (not array), all segments get error flag."""
    segs = [make_segment("id-1"), make_segment("id-2")]
    llm_output = json.dumps({"unexpected": "object"})
    result = parse_attribution_response(llm_output, segs)
    assert len(result) == 2
    for seg in result:
        assert SegmentFlag.ATTRIBUTION_PARSE_ERROR in seg.flags
        assert seg.confidence == pytest.approx(0.0)
