from __future__ import annotations

import json
import re
from unittest.mock import MagicMock

import pytest

from transcribe3.shared.types import (
    TranscriptSegment,
    TranscriptSession,
    SpeakerLabel,
    CleaningConfig,
    CleaningMode,
    FillerWordBehavior,
)
from transcribe3.core.llm.client import OllamaClient


# ---------------------------------------------------------------------------
# Speaker fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def speaker_a():
    return SpeakerLabel(anonymous_id="Speaker_A", resolved_name="Jane Smith")


@pytest.fixture
def speaker_b():
    return SpeakerLabel(anonymous_id="Speaker_B", resolved_name="John Doe")


# ---------------------------------------------------------------------------
# Segment / session fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def sample_segments(speaker_a, speaker_b):
    """10 segments, realistic interview content, alternating speakers."""
    return [
        TranscriptSegment(
            start_time=0.0, end_time=3.5, speaker=speaker_a,
            text="So tell me, um, how did you first get into this field?", confidence=0.95,
        ),
        TranscriptSegment(
            start_time=3.5, end_time=8.2, speaker=speaker_b,
            text="Well, I — I started back in 2010, actually.", confidence=0.9,
        ),
        TranscriptSegment(
            start_time=8.2, end_time=12.0, speaker=speaker_a,
            text="That's interesting. And what was, uh, your initial role?", confidence=0.88,
        ),
        TranscriptSegment(
            start_time=12.0, end_time=18.5, speaker=speaker_b,
            text="I was a junior analyst, you know, just learning the ropes.", confidence=0.92,
        ),
        TranscriptSegment(
            start_time=18.5, end_time=22.0, speaker=speaker_a,
            text="Right. And how did you grow from there?", confidence=0.97,
        ),
        TranscriptSegment(
            start_time=22.0, end_time=28.0, speaker=speaker_b,
            text="Slowly at first. The learning curve was steep.", confidence=0.85,
        ),
        TranscriptSegment(
            start_time=28.0, end_time=33.0, speaker=speaker_a,
            text="What would you say was your biggest challenge?", confidence=0.93,
        ),
        TranscriptSegment(
            start_time=33.0, end_time=40.0, speaker=speaker_b,
            text="Honestly, the — the communication side more than the technical.", confidence=0.78,
        ),
        TranscriptSegment(
            start_time=40.0, end_time=44.5, speaker=speaker_a,
            text="That's a common theme. Did you have a mentor?", confidence=0.91,
        ),
        TranscriptSegment(
            start_time=44.5, end_time=52.0, speaker=speaker_b,
            text="Yes, fortunately. She really helped me find my footing.", confidence=0.96,
        ),
    ]


@pytest.fixture
def sample_session(sample_segments):
    return TranscriptSession(
        source_file="sample_interview.txt",
        speaker_map={"Speaker_A": "Jane Smith", "Speaker_B": "John Doe"},
        segments=sample_segments,
    )


# ---------------------------------------------------------------------------
# Config fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def default_config():
    return CleaningConfig()


# ---------------------------------------------------------------------------
# LLM mock fixture
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_llm_client():
    """Mock OllamaClient that returns valid attribution JSON for any prompt."""
    client = MagicMock(spec=OllamaClient)

    def fake_complete(prompt: str, model: str) -> str:
        # Extract segment IDs and speakers from the prompt JSON
        ids = re.findall(r'"id":\s*"([^"]+)"', prompt)
        speakers = re.findall(r'"speaker":\s*"([^"]+)"', prompt)
        result = [
            {"id": i, "speaker": s, "confidence": 0.9}
            for i, s in zip(ids, speakers)
        ]
        return json.dumps(result)

    client.complete.side_effect = fake_complete
    return client
