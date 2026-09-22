export type FillerWordBehavior = 'off' | 'flag' | 'strip';
export type CleaningMode = 'verbatim' | 'standard' | 'aggressive';
export type OutputFormat = 'json' | 'txt' | 'srt' | 'vtt';
export type LLMProtocol = 'ollama' | 'openai_compatible';

export interface LLMProviderConfig {
  id: string;
  label: string;
  protocol: LLMProtocol;
  base_url: string;
  enabled: boolean;
  /** Name of an existing env var to read the bearer token from; null uses the
   *  TRANSCRIBE3_LLM_API_KEY_<ID> convention. */
  api_key_env?: string | null;
  /** Server-computed: the variable this provider actually reads. Read-only —
   *  the API ignores it on PUT. */
  api_key_env_var?: string;
  /** Server-computed: whether that variable currently holds a value. The token
   *  itself never reaches the browser. */
  api_key_set?: boolean;
}

export interface SpeakerLabel {
  anonymous_id: string;
  resolved_name: string | null;
}

export interface TranscriptSegment {
  id: string;
  start_time: number;
  end_time: number;
  speaker: SpeakerLabel;
  text: string;
  original_text: string | null;
  confidence: number;
  flags: string[];
}

export type SessionStatus = 'processing' | 'complete' | 'error';

export interface TranscriptSession {
  session_id: string;
  source_file: string;
  display_name: string | null;
  created_at: string;
  speaker_map: Record<string, string>;
  segments: TranscriptSegment[];
  audio_file: string | null;
  status: SessionStatus;
  processing_stage: string | null;
  error: string | null;
  warning: string | null;
}

export interface ProcessingParams {
  llm_provider_id: string | null;
  llm_provider_label: string | null;
  llm_model: string | null;
  cleaning_mode: CleaningMode | null;
  filler_words: FillerWordBehavior | null;
  remove_false_starts: boolean | null;
  handle_crosstalk: boolean | null;
  low_confidence_threshold: number | null;
  cleaning_enabled: boolean | null;
  attribution_enabled: boolean | null;
  transcription_backend: string | null;
  whisper_model: string | null;
}

export interface SessionSummary {
  session_id: string;
  source_file: string;
  display_name: string | null;
  created_at: string;
  segment_count: number;
  low_confidence_count: number;
  mean_confidence: number;
  status: SessionStatus;
  warning: string | null;
  processing_params: ProcessingParams | null;
  stage_timings: StageTiming[];
  audio_file: string | null;
}

export interface StageTiming {
  stage: string;
  seconds: number;
}

export interface AppSettings {
  llm_timeout: number;
  llm_providers: LLMProviderConfig[];
  default_provider_id: string;
  default_model: string;
  default_transcription_backend: string;
  default_whisper_model: string;
  low_confidence_threshold: number;
  /** Optional pipeline stages, both switchable in Settings. */
  run_cleaning: boolean;
  run_attribution: boolean;
  archive_dir: string | null;
}

export interface ArchiveRecordingStatus {
  session_id: string;
  source_file: string;
  display_name: string | null;
  audio_file: string;
  local_available: boolean;
  archive_available: boolean;
  local_size_bytes: number | null;
  archive_size_bytes: number | null;
}

export interface ArchiveStatus {
  archive_dir: string | null;
  suggested_archive_dir: string;
  archive_connected: boolean;
  local_free_bytes: number | null;
  archive_free_bytes: number | null;
  recordings: ArchiveRecordingStatus[];
}

export interface CleaningConfigRequest {
  model?: string;
  provider_id?: string;
  mode?: CleaningMode;
  filler_words?: FillerWordBehavior;
  remove_false_starts?: boolean;
  handle_crosstalk?: boolean;
  low_confidence_threshold?: number;
}
