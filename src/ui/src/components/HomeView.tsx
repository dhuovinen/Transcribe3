import { useEffect, useState } from 'react'
import { listSessions } from '../api'
import { formatDate, formatHoursCompact } from '../format'
import type { SessionSummary } from '../types'

interface Props {
  onNewSession: () => void
  onViewSessions: () => void
  onSelectSession: (sessionId: string) => void
}

interface Feature {
  icon: string
  title: string
  body: string
}

const FEATURES: Feature[] = [
  {
    icon: '🎙️',
    title: 'Audio Transcription',
    body: 'WhisperX (CPU) or mlx-whisper (Apple GPU) — pick a model from tiny to large-v3 per upload, or set a default in Settings.',
  },
  {
    icon: '🗣️',
    title: 'Speaker Diarization',
    body: "pyannote.audio automatically figures out who's speaking and when — no manual tagging before review.",
  },
  {
    icon: '🧹',
    title: 'Rule-Based Cleaning',
    body: 'Filler words, false starts, and crosstalk handled in a fraction of a second — no LLM, no wait.',
  },
  {
    icon: '🧠',
    title: 'LLM Speaker Attribution',
    body: 'A local LLM (Ollama or any OpenAI-compatible endpoint) validates diarized labels and scores every segment for confidence.',
  },
  {
    icon: '🔒',
    title: 'Fully Local & Private',
    body: 'Every stage — transcription, diarization, cleaning, attribution — runs on your machine. No cloud calls, nothing leaves your network.',
  },
  {
    icon: '✏️',
    title: 'Review & Correct',
    body: 'Rename speakers, edit text inline, and click any line to jump the audio player straight to that moment.',
  },
  {
    icon: '📤',
    title: 'Export Anywhere',
    body: 'Pull a clean transcript out as JSON, TXT, SRT, or VTT, or download the original recording, whenever you need it.',
  },
  {
    icon: '📊',
    title: 'Archive & Benchmark',
    body: 'Offload recordings to verified external storage, and benchmark backends/models for speed and Word Error Rate against a gold-standard reference set.',
  },
]

export default function HomeView({ onNewSession, onViewSessions, onSelectSession }: Props) {
  const [sessions, setSessions] = useState<SessionSummary[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    listSessions()
      .then(setSessions)
      .catch((e) => setError(e instanceof Error ? e.message : 'Failed to load sessions'))
  }, [])

  return (
    <div>
      <div className="hero-intro">
        <h2>Turn raw recordings into reviewed, speaker-attributed transcripts</h2>
        <p className="hero-tagline">
          Transcribe3 runs the full pipeline — transcription, speaker diarization,
          rule-based cleaning, and LLM-validated speaker attribution — entirely on
          your own machine. Drop in audio or an existing transcript, review and
          correct it inline, and export it in the format you need. No cloud APIs,
          no subscriptions, no recordings leaving your network.
        </p>

        <div className="hero-actions">
          <button className="btn btn-primary" onClick={onNewSession}>
            New Session
          </button>
          <button className="btn" onClick={onViewSessions}>
            View All Sessions{sessions ? ` (${sessions.length})` : ''}
          </button>
        </div>
      </div>

      {error && <div className="error-msg">{error}</div>}

      <div className="hero-features-grid">
        {FEATURES.map((f) => (
          <div className="panel hero-feature" key={f.title}>
            <div className="hero-feature-icon" aria-hidden="true">{f.icon}</div>
            <h3>{f.title}</h3>
            <p>{f.body}</p>
          </div>
        ))}
      </div>

      {sessions && (
        <>
          <h3 className="hero-section-label">Your Activity</h3>
          <Stats sessions={sessions} />
        </>
      )}

      {sessions && sessions.length > 0 && (
        <p className="hero-recent">
          Most recent:{' '}
          <a onClick={() => onSelectSession(sessions[0]!.session_id)}>
            {sessions[0]!.display_name ?? sessions[0]!.source_file}
          </a>{' '}
          — {formatDate(sessions[0]!.created_at)}
        </p>
      )}
    </div>
  )
}

function Stats({ sessions }: { sessions: SessionSummary[] }) {
  const totalSessions = sessions.length
  const processingCount = sessions.filter((s) => s.status === 'processing').length
  const totalAudioSeconds = sessions.reduce((sum, s) => sum + (s.audio_duration_seconds ?? 0), 0)

  // Only average across sessions where attribution actually scored confidence —
  // an "unscored" session (attribution off) has a meaningless mean_confidence of 0,
  // which would otherwise drag the average down for a reason that isn't accuracy.
  const scored = sessions.filter(
    (s) => s.status === 'complete' && s.processing_params?.attribution_enabled !== false && s.segment_count > 0,
  )
  const meanConfidence =
    scored.length > 0 ? scored.reduce((sum, s) => sum + s.mean_confidence, 0) / scored.length : null
  const confClass =
    meanConfidence == null
      ? ''
      : meanConfidence >= 0.8
      ? 'conf-high'
      : meanConfidence >= 0.6
      ? 'conf-mid'
      : 'conf-low'

  return (
    <div className="panel hero-stats-grid">
      <div className="conf-summary-item">
        <div className="value">{totalSessions}</div>
        <div className="label">Sessions</div>
      </div>
      <div className="conf-summary-item">
        <div className="value">{formatHoursCompact(totalAudioSeconds)}</div>
        <div className="label">Audio Transcribed</div>
      </div>
      <div className="conf-summary-item">
        <div className={`value ${processingCount > 0 ? 'conf-mid' : ''}`}>{processingCount}</div>
        <div className="label">Processing Now</div>
      </div>
      <div className="conf-summary-item">
        <div className={`value ${confClass}`}>
          {meanConfidence == null ? '—' : `${(meanConfidence * 100).toFixed(0)}%`}
        </div>
        <div className="label">Avg. Confidence</div>
      </div>
    </div>
  )
}
