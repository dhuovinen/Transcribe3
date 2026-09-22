from __future__ import annotations

from pydantic import BaseModel, Field
from transcribe3.shared.types import (
    ConfidenceScore,
    OutputFormat,
    CleaningMode,
    FillerWordBehavior,
    ProcessingParams,
    StageTiming,
)


class CleaningConfigRequest(BaseModel):
    model: str = "llama3"
    provider_id: str | None = None  # None = use the server's configured default provider
    mode: CleaningMode = CleaningMode.STANDARD
    filler_words: FillerWordBehavior = FillerWordBehavior.OFF
    remove_false_starts: bool = False
    handle_crosstalk: bool = True
    low_confidence_threshold: ConfidenceScore = 0.6


class SpeakerMapUpdate(BaseModel):
    speaker_map: dict[str, str]  # anonymous_id -> resolved name


class SessionRenameUpdate(BaseModel):
    display_name: str | None  # None (or empty string) clears the override, reverting to source_file


class SegmentSpeakerUpdate(BaseModel):
    speaker: str  # resolved name or anonymous_id
    confidence: ConfidenceScore = 1.0


class SegmentTextUpdate(BaseModel):
    text: str


class SessionSummary(BaseModel):
    session_id: str
    source_file: str
    display_name: str | None = None
    created_at: str
    segment_count: int
    low_confidence_count: int
    mean_confidence: float
    status: str = "complete"
    warning: str | None = None
    processing_params: ProcessingParams | None = None
    stage_timings: list[StageTiming] = Field(default_factory=list)
    audio_file: str | None = None


class ConfidenceSummary(BaseModel):
    total_segments: int
    low_confidence_count: int
    mean_confidence: float
    threshold: float


class ArchiveConfigurationUpdate(BaseModel):
    archive_dir: str = Field(min_length=1, max_length=4096)


class ArchiveRecordingRequest(BaseModel):
    remove_local: bool = False


class ArchiveRecordingStatus(BaseModel):
    session_id: str
    source_file: str
    display_name: str | None = None
    audio_file: str
    local_available: bool
    archive_available: bool
    local_size_bytes: int | None = None
    archive_size_bytes: int | None = None


class ArchiveStatusResponse(BaseModel):
    archive_dir: str | None = None
    suggested_archive_dir: str
    archive_connected: bool
    local_free_bytes: int | None = None
    archive_free_bytes: int | None = None
    recordings: list[ArchiveRecordingStatus] = Field(default_factory=list)
