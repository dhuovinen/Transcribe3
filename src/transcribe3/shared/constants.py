DEFAULT_LOW_CONFIDENCE_THRESHOLD: float = 0.6
DEFAULT_LLM_MODEL: str = "qwen3.6:27b"
DEFAULT_LLM_TIMEOUT: float = 60.0
MAX_LLM_TIMEOUT: float = 1800.0
OLLAMA_BASE_URL: str = "http://localhost:11434"
OLMX_BASE_URL: str = "http://127.0.0.1:8090/v1"

# Providers that need a bearer token read it from the environment (typically .env),
# never from settings.json — that file is served verbatim by the unauthenticated
# /settings endpoint. The variable for provider "olmx" is TRANSCRIBE3_LLM_API_KEY_OLMX
# unless its registry entry names a different one via api_key_env.
LLM_API_KEY_ENV_PREFIX: str = "TRANSCRIBE3_LLM_API_KEY_"

SUPPORTED_AUDIO_FORMATS: list[str] = [".wav", ".mp3", ".m4a", ".flac", ".ogg", ".mp4"]
SUPPORTED_TRANSCRIPT_FORMATS: list[str] = [".txt", ".srt", ".vtt", ".json"]

# Filler words to detect (lowercase)
FILLER_WORDS: list[str] = [
    "um", "uh", "uh-huh", "mm-hmm", "hmm",
    "you know", "like", "right", "okay", "so",
    "actually", "basically", "literally",
]

# Segment duration thresholds for flagging
MIN_SEGMENT_DURATION_SECONDS: float = 0.1
MAX_SEGMENT_DURATION_SECONDS: float = 60.0
