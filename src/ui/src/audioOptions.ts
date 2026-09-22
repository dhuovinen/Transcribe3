export const WHISPER_MODELS = ['tiny', 'base', 'small', 'medium', 'large-v2', 'large-v3']

export const AUDIO_BACKENDS = [
  { value: 'whisperx', label: 'WhisperX (CPU)' },
  { value: 'mlx', label: 'mlx-whisper (Apple GPU)' },
]
