import { useEffect, useRef, useState } from 'react'
import { getSettings, listModels, uploadAudio, uploadTranscript } from '../api'
import type { CleaningConfigRequest, FillerWordBehavior, LLMProviderConfig } from '../types'

interface Props {
  onSuccess: (sessionId: string) => void
  onCancel: () => void
}

type InputMode = 'transcript' | 'audio'

const WHISPER_MODELS = ['tiny', 'base', 'small', 'medium', 'large-v2', 'large-v3']
const AUDIO_BACKENDS = [
  { value: 'whisperx', label: 'WhisperX (CPU)' },
  { value: 'mlx', label: 'mlx-whisper (Apple GPU)' },
]

export default function UploadForm({ onSuccess, onCancel }: Props) {
  const fileRef = useRef<HTMLInputElement>(null)
  const [inputMode, setInputMode] = useState<InputMode>('transcript')
  const [providers, setProviders] = useState<LLMProviderConfig[]>([])
  const [models, setModels] = useState<string[]>([])
  const [model, setModel] = useState('')
  const [providerId, setProviderId] = useState('')
  const [whisperModel, setWhisperModel] = useState('base')
  const [backend, setBackend] = useState('whisperx')
  const [fillerWords, setFillerWords] = useState<FillerWordBehavior>('off')
  const [removeFalseStarts, setRemoveFalseStarts] = useState(false)
  const [verbatim, setVerbatim] = useState(false)
  const [threshold, setThreshold] = useState(0.6)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  // Stages switched off globally in Settings apply to this run too, so say so
  // rather than letting the result come back mysteriously unscored.
  const [disabledStages, setDisabledStages] = useState<string[]>([])
  const abortRef = useRef<AbortController | null>(null)

  useEffect(() => {
    let defaultModel = ''
    getSettings()
      .then((s) => {
        setProviders(s.llm_providers.filter((p) => p.enabled))
        setProviderId(s.default_provider_id)
        defaultModel = s.default_model
        setDisabledStages([
          ...(s.run_cleaning ? [] : ['text cleaning']),
          ...(s.run_attribution ? [] : ['LLM speaker attribution']),
        ])
        return listModels(s.default_provider_id)
      })
      .then((m) => {
        setModels(m)
        // Honour the model chosen in Settings; fall back to the first one the
        // provider offers only when that model isn't installed there.
        if (m.length > 0) setModel(m.includes(defaultModel) ? defaultModel : m[0]!)
      })
      .catch(() => {})
  }, [])

  function handleProviderChange(newProviderId: string) {
    setProviderId(newProviderId)
    setModel('')
    setModels([])
    listModels(newProviderId)
      .then((m) => {
        setModels(m)
        if (m.length > 0) setModel(m[0]!)
      })
      .catch(() => {})
  }

  // Reset file input when mode changes
  function handleModeChange(mode: InputMode) {
    setInputMode(mode)
    setError(null)
    if (fileRef.current) fileRef.current.value = ''
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    const file = fileRef.current?.files?.[0]
    if (!file) {
      setError('Please select a file.')
      return
    }

    const abort = new AbortController()
    abortRef.current = abort
    setLoading(true)
    setError(null)

    try {
      if (inputMode === 'audio') {
        const session = await uploadAudio(file, whisperModel, backend, abort.signal)
        onSuccess(session.session_id)
      } else {
        const config: CleaningConfigRequest = {
          model: model || undefined,
          provider_id: providerId || undefined,
          mode: verbatim ? 'verbatim' : 'standard',
          filler_words: verbatim ? 'off' : fillerWords,
          remove_false_starts: verbatim ? false : removeFalseStarts,
          handle_crosstalk: !verbatim,
          low_confidence_threshold: threshold,
        }
        const session = await uploadTranscript(file, config, abort.signal)
        onSuccess(session.session_id)
      }
    } catch (e) {
      if (e instanceof DOMException && e.name === 'AbortError') return
      const msg = e instanceof Error ? e.message : 'Upload failed'
      if (msg.toLowerCase().includes('ollama') && msg.toLowerCase().includes('not running')) {
        setError(`${msg} — open a terminal and run "ollama serve"`)
      } else if (msg.toLowerCase().includes('not running')) {
        setError(`${msg} — check the provider's base URL in Settings and make sure it's running.`)
      } else {
        setError(msg)
      }
    } finally {
      setLoading(false)
      abortRef.current = null
    }
  }

  return (
    <form className="upload-form" onSubmit={handleSubmit}>
      <h2>New Session</h2>

      {disabledStages.length > 0 && (
        <p className="warning-msg" style={{ marginTop: 0 }}>
          {disabledStages.join(' and ')} {disabledStages.length > 1 ? 'are' : 'is'} turned off
          in Settings, so this run will skip {disabledStages.length > 1 ? 'them' : 'it'}.
        </p>
      )}

      {/* Mode toggle */}
      <div className="form-group">
        <label>Input type</label>
        <div className="mode-toggle">
          <button
            type="button"
            className={inputMode === 'transcript' ? 'mode-btn mode-btn--active' : 'mode-btn'}
            onClick={() => handleModeChange('transcript')}
          >
            Transcript
          </button>
          <button
            type="button"
            className={inputMode === 'audio' ? 'mode-btn mode-btn--active' : 'mode-btn'}
            onClick={() => handleModeChange('audio')}
          >
            Audio file
          </button>
        </div>
      </div>

      {inputMode === 'transcript' ? (
        <>
          <div className="form-group">
            <label>Transcript file (.txt, .srt, .vtt, .json)</label>
            <input
              ref={fileRef}
              type="file"
              accept=".txt,.srt,.vtt,.json"
              required
            />
          </div>

          <div className="form-group">
            <label>LLM provider</label>
            <select
              value={providerId}
              onChange={(e) => handleProviderChange(e.target.value)}
            >
              {providers.length === 0 ? (
                <option value="">No providers configured</option>
              ) : (
                providers.map((p) => (
                  <option key={p.id} value={p.id}>{p.label}</option>
                ))
              )}
            </select>
          </div>

          <div className="form-group">
            <label>Model</label>
            <select value={model} onChange={(e) => setModel(e.target.value)}>
              {models.length === 0 ? (
                <option value="">Loading models…</option>
              ) : (
                models.map((m) => <option key={m} value={m}>{m}</option>)
              )}
            </select>
          </div>

          <div className="form-row" style={{ marginBottom: 14 }}>
            <input
              type="checkbox"
              id="verbatim"
              checked={verbatim}
              onChange={(e) => setVerbatim(e.target.checked)}
            />
            <label htmlFor="verbatim">Verbatim mode (no cleaning)</label>
          </div>

          <div className="form-group">
            <label>Filler words</label>
            <select
              value={fillerWords}
              disabled={verbatim}
              onChange={(e) => setFillerWords(e.target.value as FillerWordBehavior)}
            >
              <option value="off">Off</option>
              <option value="flag">Flag</option>
              <option value="strip">Strip</option>
            </select>
          </div>

          <div className="form-row" style={{ marginBottom: 14 }}>
            <input
              type="checkbox"
              id="false_starts"
              checked={removeFalseStarts}
              disabled={verbatim}
              onChange={(e) => setRemoveFalseStarts(e.target.checked)}
            />
            <label htmlFor="false_starts">Remove false starts</label>
          </div>

          <div className="form-group">
            <label>Low-confidence threshold (0.0 – 1.0)</label>
            <input
              type="number"
              min={0}
              max={1}
              step={0.05}
              value={threshold}
              onChange={(e) => setThreshold(parseFloat(e.target.value))}
              style={{ width: 80 }}
            />
          </div>
        </>
      ) : (
        <>
          <div className="form-group">
            <label>Audio file (.mp3, .wav, .m4a, .flac, .ogg, .mp4)</label>
            <input
              ref={fileRef}
              type="file"
              accept=".mp3,.wav,.m4a,.flac,.ogg,.mp4"
              required
            />
          </div>

          <div className="form-group">
            <label>Transcription backend</label>
            <select value={backend} onChange={(e) => setBackend(e.target.value)}>
              {AUDIO_BACKENDS.map((b) => (
                <option key={b.value} value={b.value}>{b.label}</option>
              ))}
            </select>
            <span style={{ fontSize: 12, color: '#6b7280', marginTop: 4 }}>
              WhisperX runs on CPU only. mlx-whisper uses Apple's GPU/Neural Engine and is
              typically much faster on Apple Silicon. First-time setup only: run{' '}
              <code>uv sync --extra mlx</code> once to install it — after that it's just
              a dropdown choice, no need to run it again. Try both to compare speed and quality.
            </span>
          </div>

          <div className="form-group">
            <label>Whisper model</label>
            <select value={whisperModel} onChange={(e) => setWhisperModel(e.target.value)}>
              {WHISPER_MODELS.map((m) => (
                <option key={m} value={m}>{m}</option>
              ))}
            </select>
            <span style={{ fontSize: 12, color: '#6b7280', marginTop: 4 }}>
              Larger models are more accurate but slower. <code>base</code> is a good starting point.
            </span>
          </div>

          <div className="form-group" style={{ background: '#f0f9ff', border: '1px solid #bae6fd', borderRadius: 4, padding: '10px 12px' }}>
            <p style={{ margin: 0, fontSize: 12, color: '#0369a1' }}>
              Audio processing uses Whisper (via the selected backend) for transcription and
              pyannote.audio for speaker diarization. Processing time depends on file length,
              model size, and backend.
            </p>
          </div>
        </>
      )}

      {error && <div className="error-msg">{error}</div>}

      <div className="form-row" style={{ marginTop: 20, gap: 12 }}>
        <button type="submit" className="btn btn-primary" disabled={loading}>
          {loading && <span className="spinner" />}
          {loading
            ? inputMode === 'audio' ? 'Processing audio…' : 'Processing…'
            : inputMode === 'audio' ? 'Upload & Transcribe' : 'Upload & Process'}
        </button>
        <button
          type="button"
          onClick={() => {
            abortRef.current?.abort()
            onCancel()
          }}
        >
          Cancel
        </button>
      </div>
    </form>
  )
}
