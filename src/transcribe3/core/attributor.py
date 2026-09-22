from __future__ import annotations

import json
import logging
import time
from typing import Callable

from transcribe3.core.llm.client import LLMClient, LLMUnavailableError
from transcribe3.core.llm.prompts import (
    ATTRIBUTION_SYSTEM_PROMPT,
    ATTRIBUTION_USER_PROMPT_TEMPLATE,
)
from transcribe3.shared.types import CleaningConfig, SegmentFlag, TranscriptSegment

logger = logging.getLogger(__name__)

_WINDOW_SIZE = 10
_OVERLAP = 2


def attribute_speakers(
    segments: list[TranscriptSegment],
    config: CleaningConfig,
    llm_client: LLMClient,
    model: str,
    on_progress: Callable[[int, int], None] | None = None,
) -> list[TranscriptSegment]:
    """Process all segments through windowed LLM attribution and apply confidence flags.

    This makes one sequential LLM call per 10-segment window (8-segment step,
    due to a 2-segment overlap for attribution continuity), so total time
    scales with transcript length — for a long recording this can be the
    slowest stage of the whole pipeline. on_progress, if given, is called
    after each window with (windows_done, total_windows) so callers can
    surface progress instead of one flat "processing" state.
    """
    if not segments:
        return segments

    # Build a mutable dict keyed by segment id for final assembly
    result: dict[str, TranscriptSegment] = {seg.id: seg for seg in segments}

    # Track which segment ids have already been written by a "fresh" (non-overlap) pass.
    # A segment is "fresh" in the window where it is not one of the carry-over overlap items.
    committed: set[str] = set()

    total = len(segments)
    step = _WINDOW_SIZE - _OVERLAP  # advance by 8 each time
    starts = list(range(0, total, step))
    total_windows = len(starts)
    unavailable_windows = 0

    for window_num, i in enumerate(starts, start=1):
        window = segments[i : i + _WINDOW_SIZE]

        # Determine which segment ids are "fresh" in this window.
        # The first two items of every window (except the very first window) are
        # overlap carry-overs; all others are fresh.
        if i == 0:
            fresh_ids = {seg.id for seg in window}
        else:
            overlap_ids = {seg.id for seg in window[:_OVERLAP]}
            fresh_ids = {seg.id for seg in window[_OVERLAP:]}

            # Also include overlap ids that haven't been committed yet
            # (shouldn't happen in normal flow, but be safe)
            fresh_ids |= overlap_ids - committed

        window_start = time.monotonic()
        updated_window, unavailable = _attribute_window(window, config, llm_client, model)
        if unavailable:
            unavailable_windows += 1
        window_elapsed = time.monotonic() - window_start
        logger.info(
            "LLM attribution window %d/%d (%d segments) took %.1fs",
            window_num, total_windows, len(window), window_elapsed,
        )

        for seg in updated_window:
            if seg.id in fresh_ids and seg.id not in committed:
                result[seg.id] = seg
                committed.add(seg.id)
            elif seg.id not in committed:
                # Overlap segment not yet committed — write tentatively but don't mark committed
                result[seg.id] = seg

        if on_progress:
            on_progress(window_num, total_windows)

    # If the backend was unreachable for every single window, the whole run is a
    # wash — raise instead of silently handing back all-zero confidence with no
    # explanation (previously this only degraded per-window and never surfaced,
    # so callers' "LLM unavailable" handling — which sets a session warning —
    # never triggered and mean confidence just silently dropped to 0%).
    if unavailable_windows == total_windows:
        raise LLMUnavailableError(
            f"LLM backend unreachable for all {total_windows} attribution window(s)"
        )

    # Apply confidence scoring to all segments
    threshold = config.low_confidence_threshold
    final_segments = [
        score_attribution_confidence(result[seg.id], threshold) for seg in segments
    ]
    return final_segments


def _attribute_window(
    segments: list[TranscriptSegment],
    config: CleaningConfig,
    llm_client: LLMClient,
    model: str,
) -> tuple[list[TranscriptSegment], bool]:
    """Run LLM attribution on a single window of segments. Degrades gracefully on failure.

    Returns (segments, unavailable). unavailable is True only when the backend itself
    could not be reached — as opposed to responding with unparseable output — so callers
    can distinguish "server down" from "model gave a bad answer".
    """
    prompt = build_attribution_prompt(segments)
    full_prompt = f"{ATTRIBUTION_SYSTEM_PROMPT}\n\n{prompt}"

    try:
        response = llm_client.complete(full_prompt, model)
    except LLMUnavailableError as exc:
        logger.warning("LLM unavailable during attribution: %s", exc)
        # Degrade gracefully: return originals with zero confidence
        degraded = []
        for seg in segments:
            flags = list(seg.flags)
            if SegmentFlag.ATTRIBUTION_PARSE_ERROR not in flags:
                flags.append(SegmentFlag.ATTRIBUTION_PARSE_ERROR)
            degraded.append(seg.model_copy(update={"confidence": 0.0, "flags": flags}))
        return degraded, True

    return parse_attribution_response(response, segments), False


def build_attribution_prompt(segments: list[TranscriptSegment]) -> str:
    """Build the user portion of the attribution prompt from a list of segments."""
    segments_data = [
        {"id": seg.id, "speaker": seg.speaker.anonymous_id, "text": seg.text}
        for seg in segments
    ]
    segments_json = json.dumps(segments_data, ensure_ascii=False)
    return ATTRIBUTION_USER_PROMPT_TEMPLATE.format(
        segments_json=segments_json,
        count=len(segments),
    )


def parse_attribution_response(
    response: str,
    segments: list[TranscriptSegment],
) -> list[TranscriptSegment]:
    """Parse the LLM JSON response and apply updated speaker/confidence to segments."""
    segment_map: dict[str, TranscriptSegment] = {seg.id: seg for seg in segments}

    try:
        parsed = json.loads(response)
        if not isinstance(parsed, list):
            raise ValueError("Expected a JSON array")
    except (json.JSONDecodeError, ValueError) as exc:
        logger.warning("Failed to parse attribution response: %s", exc)
        updated = []
        for seg in segments:
            flags = list(seg.flags)
            if SegmentFlag.ATTRIBUTION_PARSE_ERROR not in flags:
                flags.append(SegmentFlag.ATTRIBUTION_PARSE_ERROR)
            updated.append(seg.model_copy(update={"confidence": 0.0, "flags": flags}))
        return updated

    # Index parsed results by segment id
    response_by_id: dict[str, dict] = {}
    for item in parsed:
        if not isinstance(item, dict):
            continue
        seg_id = item.get("id")
        if seg_id is None:
            continue
        if seg_id not in segment_map:
            # Unknown id — skip silently
            continue
        response_by_id[seg_id] = item

    updated_segments = []
    for seg in segments:
        item = response_by_id.get(seg.id)
        if item is None:
            # No response entry for this segment — preserve original, set confidence 0.0
            updated_segments.append(seg.model_copy(update={"confidence": 0.0}))
            continue

        new_anonymous_id = item.get("speaker", seg.speaker.anonymous_id)
        raw_confidence = item.get("confidence", 0.0)
        # Clamp to valid range
        confidence = max(0.0, min(1.0, float(raw_confidence)))

        new_speaker = seg.speaker.model_copy(update={"anonymous_id": new_anonymous_id})
        updated_segments.append(
            seg.model_copy(update={"speaker": new_speaker, "confidence": confidence})
        )

    return updated_segments


def score_attribution_confidence(
    segment: TranscriptSegment,
    threshold: float,
) -> TranscriptSegment:
    """Add LOW_CONFIDENCE flag if segment confidence is below threshold."""
    if segment.confidence < threshold and SegmentFlag.LOW_CONFIDENCE not in segment.flags:
        flags = list(segment.flags)
        flags.append(SegmentFlag.LOW_CONFIDENCE)
        return segment.model_copy(update={"flags": flags})
    return segment
