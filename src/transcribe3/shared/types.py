from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Annotated
import re
import uuid

from pydantic import BaseModel, Field, computed_field, field_validator

from transcribe3.shared.constants import LLM_API_KEY_ENV_PREFIX, OLLAMA_BASE_URL, OLMX_BASE_URL


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class LLMProtocol(str, Enum):
    """The wire protocol an LLM provider speaks — determines which client adapter to use.
    Nearly every non-Ollama local or hosted server (LM Studio, vLLM, llama.cpp server,
    OpenRouter, ...) speaks OPENAI_COMPATIBLE, so adding a new provider is normally a
    Settings-only change, not a code change."""
    OLLAMA = "ollama"
    OPENAI_COMPATIBLE = "openai_compatible"


class FillerWordBehavior(str, Enum):
    OFF = "off"
    FLAG = "flag"
    STRIP = "strip"


class CleaningMode(str, Enum):
    VERBATIM = "verbatim"      # no cleaning at all
    STANDARD = "standard"      # default
    AGGRESSIVE = "aggressive"  # remove more aggressively


class OutputFormat(str, Enum):
    JSON = "json"
    SRT = "srt"
    VTT = "vtt"
    TXT = "txt"
    DOCX = "docx"


class SegmentFlag(str, Enum):
    LOW_CONFIDENCE = "low_confidence"
    FILLER_WORD = "filler_word"
    FALSE_START = "false_start"
    CROSSTALK = "crosstalk"
    ATTRIBUTION_PARSE_ERROR = "attribution_parse_error"
    SUSPICIOUS_DURATION = "suspicious_duration"
    CONFLICT = "conflict"  # used in Scenario 3 audio+transcript alignment


# ---------------------------------------------------------------------------
# Core domain types
# ---------------------------------------------------------------------------

# ConfidenceScore is a float 0.0–1.0
ConfidenceScore = Annotated[float, Field(ge=0.0, le=1.0)]


class SpeakerLabel(BaseModel):
    # anonymous_id: what diarization gave us, e.g. "SPEAKER_00", "Speaker A"
    anonymous_id: str
    # resolved_name: human-assigned name, e.g. "Jane Smith". None until assigned.
    resolved_name: str | None = None

    @property
    def display_name(self) -> str:
        return self.resolved_name or self.anonymous_id


class TranscriptSegment(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    start_time: float  # seconds from start of audio (0.0 if no audio)
    end_time: float
    speaker: SpeakerLabel
    text: str
    # Set on the first manual edit. `text` always remains the single current
    # version used by the UI and exports; no edit history is maintained.
    original_text: str | None = None
    confidence: ConfidenceScore = 1.0
    flags: list[SegmentFlag] = Field(default_factory=list)

    @field_validator("end_time")
    @classmethod
    def end_after_start(cls, v: float, info) -> float:
        if "start_time" in info.data and v < info.data["start_time"]:
            raise ValueError("end_time must be >= start_time")
        return v


# Maps anonymous speaker IDs to resolved names
SpeakerMap = dict[str, str]


class SessionStatus(str, Enum):
    PROCESSING = "processing"
    COMPLETE = "complete"
    ERROR = "error"


class StageTiming(BaseModel):
    """How long one pipeline stage took, recorded as the run progresses.

    Kept on the session rather than only in the server log so the admin screen can
    answer "where did those 40 minutes go?" after the fact.
    """
    stage: str  # the label shown while the stage ran, e.g. "Transcribing audio…"
    seconds: float


class ProcessingParams(BaseModel):
    """Snapshot of the settings actually used to produce a session, for later audit/debugging.

    None on sessions created before this field existed (old session.json files on disk).
    """
    llm_provider_id: str | None = None
    # Captured alongside the id since a provider can be renamed or removed from
    # settings later — the label at the time of the run stays meaningful in history.
    llm_provider_label: str | None = None
    llm_model: str | None = None
    cleaning_mode: CleaningMode | None = None
    filler_words: FillerWordBehavior | None = None
    remove_false_starts: bool | None = None
    handle_crosstalk: bool | None = None
    low_confidence_threshold: ConfidenceScore | None = None
    # Whether each optional stage actually ran (both are switchable in Settings).
    # None on sessions created before the stages became optional.
    cleaning_enabled: bool | None = None
    attribution_enabled: bool | None = None
    # Audio-sourced sessions only:
    transcription_backend: str | None = None  # "whisperx" or "mlx"
    whisper_model: str | None = None


class TranscriptSession(BaseModel):
    session_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    source_file: str  # original filename (not full path — for portability)
    display_name: str | None = None  # user-set label; falls back to source_file when unset
    created_at: datetime = Field(default_factory=datetime.utcnow)
    speaker_map: SpeakerMap = Field(default_factory=dict)
    segments: list[TranscriptSegment] = Field(default_factory=list)
    audio_file: str | None = None  # filename within session dir; set for audio-sourced sessions
    # Relative to AppSettings.archive_dir. The original audio may be removed from
    # the local session directory once this verified archive copy exists.
    archived_audio_path: str | None = None
    archived_at: datetime | None = None
    status: SessionStatus = SessionStatus.COMPLETE  # pre-existing sessions default to complete
    processing_stage: str | None = None  # human-readable stage while status == processing
    error: str | None = None  # populated when status == error
    warning: str | None = None  # non-fatal issues, e.g. LLM cleaning skipped
    processing_params: ProcessingParams | None = None
    # Per-stage durations in run order; empty on sessions processed before this existed.
    stage_timings: list[StageTiming] = Field(default_factory=list)

    def apply_speaker_map(self) -> TranscriptSession:
        """Return a copy with resolved_name set on all segments from speaker_map."""
        updated_segments = []
        for seg in self.segments:
            resolved = self.speaker_map.get(seg.speaker.anonymous_id)
            updated_speaker = SpeakerLabel(
                anonymous_id=seg.speaker.anonymous_id,
                resolved_name=resolved,
            )
            updated_segments.append(seg.model_copy(update={"speaker": updated_speaker}))
        return self.model_copy(update={"segments": updated_segments})


# ---------------------------------------------------------------------------
# Config types
# ---------------------------------------------------------------------------


class CleaningConfig(BaseModel):
    mode: CleaningMode = CleaningMode.STANDARD
    filler_words: FillerWordBehavior = FillerWordBehavior.OFF
    remove_false_starts: bool = False
    handle_crosstalk: bool = True  # flag crosstalk segments
    low_confidence_threshold: ConfidenceScore = 0.6
    # Provider is an id into AppSettings.llm_providers, never hardcoded — required for benchmarking
    llm_provider_id: str = "ollama"
    llm_model: str = "qwen3.6:27b"  # model name for the selected provider — swappable for benchmarking


class LLMProviderConfig(BaseModel):
    """One entry in the configurable provider registry (AppSettings.llm_providers).

    Any server speaking the OpenAI v1 protocol (LM Studio, vLLM, llama.cpp server,
    olmx, a hosted API, ...) can be added here with protocol=OPENAI_COMPATIBLE and no
    code changes — the registry is what makes providers data instead of code.
    """
    id: str  # stable slug used to reference this provider elsewhere (e.g. "ollama")
    label: str  # display name shown in the UI
    protocol: LLMProtocol
    base_url: str
    enabled: bool = True
    # Name of the environment variable holding this provider's bearer token, for
    # servers that require one. Only the variable NAME is stored here; the token
    # itself stays in the environment. None means the convention below applies.
    api_key_env: str | None = None

    @computed_field  # serialized to the UI so a provider's row can name its variable
    @property
    def api_key_env_var(self) -> str:
        """The environment variable this provider's bearer token is read from."""
        if self.api_key_env:
            return self.api_key_env
        slug = re.sub(r"[^A-Za-z0-9]+", "_", self.id).strip("_").upper()
        return f"{LLM_API_KEY_ENV_PREFIX}{slug}"


def _default_llm_providers() -> list[LLMProviderConfig]:
    return [
        LLMProviderConfig(id="ollama", label="Ollama", protocol=LLMProtocol.OLLAMA, base_url=OLLAMA_BASE_URL),
        LLMProviderConfig(
            id="olmx", label="olmx (OpenAI-compatible)", protocol=LLMProtocol.OPENAI_COMPATIBLE, base_url=OLMX_BASE_URL
        ),
    ]


class AppSettings(BaseModel):
    llm_timeout: float = Field(default=60.0, ge=1.0, le=1800.0)
    llm_providers: list[LLMProviderConfig] = Field(default_factory=_default_llm_providers)
    default_provider_id: str = "ollama"
    default_model: str = "qwen3.6:27b"
    # Preselected on the New Session screen for audio uploads; a session can
    # still override both per-run.
    default_transcription_backend: str = "whisperx"
    default_whisper_model: str = "base"
    low_confidence_threshold: ConfidenceScore = 0.6
    # Optional pipeline stages. LLM attribution makes one sequential call per
    # 10-segment window, so on a long recording it dominates total runtime —
    # turning it off keeps the diarization speaker labels unvalidated but returns
    # a transcript in a fraction of the time.
    run_cleaning: bool = True
    run_attribution: bool = True
    # The external-drive archive root is configured through the admin archive
    # screen, which validates and creates it before saving this value.
    archive_dir: str | None = None

    def find_provider(self, provider_id: str) -> LLMProviderConfig | None:
        return next((p for p in self.llm_providers if p.id == provider_id), None)


class ValidationResult(BaseModel):
    is_valid: bool
    issues: list[str] = Field(default_factory=list)
    confidence: ConfidenceScore = 1.0
