import { useEffect, useRef, useState } from 'react'
import {
  audioUrl,
  getSession,
  renameSession,
  updateSegmentSpeaker,
  updateSegmentText,
  updateSpeakerMap,
} from '../api'
import type { TranscriptSession } from '../types'
import ConfidenceSummary from './ConfidenceSummary'
import ExportBar from './ExportBar'
import SegmentRow from './SegmentRow'
import SpeakerMapEditor from './SpeakerMapEditor'

interface Props {
  sessionId: string
  onBack?: () => void
}

export default function ReviewView({ sessionId }: Props) {
  const [session, setSession] = useState<TranscriptSession | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [editingName, setEditingName] = useState(false)
  const [nameValue, setNameValue] = useState('')
  const [savingName, setSavingName] = useState(false)
  const [stageElapsedSec, setStageElapsedSec] = useState(0)
  const [pollFailing, setPollFailing] = useState(false)
  const audioRef = useRef<HTMLAudioElement>(null)
  const stageStartRef = useRef<number>(Date.now())
  const lastStageRef = useRef<string | null>(null)
  const pollFailureCountRef = useRef(0)

  async function load() {
    setLoading(true)
    setError(null)
    try {
      const data = await getSession(sessionId)
      setSession(data)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load session')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { void load() }, [sessionId])

  // Poll while the session is still processing (audio pipeline runs in background).
  // A poll can fail transiently (a dev-server reload, a blip in connectivity) and
  // is worth retrying silently — but if it keeps failing, staring at an unchanging
  // spinner with no indication anything is wrong is indistinguishable from a real
  // hang. Surface it after a few consecutive misses instead of retrying forever
  // in silence.
  useEffect(() => {
    if (session?.status !== 'processing') return
    pollFailureCountRef.current = 0
    setPollFailing(false)
    const timer = setInterval(async () => {
      try {
        const data = await getSession(sessionId)
        pollFailureCountRef.current = 0
        setPollFailing(false)
        setSession(data)
      } catch {
        pollFailureCountRef.current += 1
        if (pollFailureCountRef.current >= 3) setPollFailing(true)
      }
    }, 2000)
    return () => clearInterval(timer)
  }, [sessionId, session?.status])

  // Track how long the current processing_stage has been active. The backend
  // doesn't report a percentage — this just shows the page is still moving.
  useEffect(() => {
    if (session?.status !== 'processing') return
    if (session.processing_stage !== lastStageRef.current) {
      lastStageRef.current = session.processing_stage ?? null
      stageStartRef.current = Date.now()
      setStageElapsedSec(0)
    }
    const timer = setInterval(() => {
      setStageElapsedSec(Math.floor((Date.now() - stageStartRef.current) / 1000))
    }, 5000)
    return () => clearInterval(timer)
  }, [session?.status, session?.processing_stage])

  function handleStartEditName() {
    if (!session) return
    setNameValue(session.display_name ?? session.source_file)
    setEditingName(true)
  }

  async function handleSaveName() {
    if (!session) return
    const trimmed = nameValue.trim()
    setSavingName(true)
    try {
      const updated = await renameSession(sessionId, trimmed || null)
      setSession(updated)
      setEditingName(false)
    } catch (e) {
      alert(e instanceof Error ? e.message : 'Rename failed')
    } finally {
      setSavingName(false)
    }
  }

  async function handleSaveSpeakerMap(map: Record<string, string>) {
    const updated = await updateSpeakerMap(sessionId, map)
    setSession(updated)
  }

  async function handleSpeakerChange(segmentId: string, speaker: string) {
    const updated = await updateSegmentSpeaker(sessionId, segmentId, speaker, 1.0)
    setSession(updated)
  }

  async function handleTextChange(segmentId: string, text: string) {
    const updated = await updateSegmentText(sessionId, segmentId, text)
    setSession(updated)
  }

  function handleSeek(startTime: number) {
    if (audioRef.current) {
      audioRef.current.currentTime = startTime
      audioRef.current.play().catch(() => {})
    }
  }

  if (loading) return <p>Loading session…</p>
  if (error) return <div className="error-msg">{error}</div>
  if (!session) return null

  if (session.status === 'processing') {
    const mins = Math.floor(stageElapsedSec / 60)
    const secs = stageElapsedSec % 60
    const elapsedLabel = mins > 0 ? `${mins}m ${secs}s` : `${secs}s`
    return (
      <div className="processing-panel">
        <span className="spinner" style={{ width: 20, height: 20 }} />
        <h3 style={{ margin: '12px 0 4px' }}>Processing {session.display_name ?? session.source_file}</h3>
        <p style={{ color: '#6b7280', margin: 0 }}>
          {session.processing_stage ?? 'Working…'}
          <span style={{ color: '#9ca3af' }}> — running {elapsedLabel}</span>
        </p>
        {pollFailing && (
          <p className="warning-msg" style={{ marginTop: 12 }}>
            Lost contact with the server — still retrying every few seconds. If this
            doesn't recover, the API process may have restarted or crashed; check
            that it's running, then reload this page.
          </p>
        )}
        <p style={{ color: '#9ca3af', fontSize: 12, marginTop: 12 }}>
          This page updates automatically. You can leave and come back — processing
          continues on the server. Longer audio files and larger Whisper models
          take longer at the transcribing/diarizing stage — there's no fixed
          percentage, but the elapsed time above resets each time it reaches a
          new stage, so it's still moving forward even if a stage runs for a
          while.
        </p>
      </div>
    )
  }

  if (session.status === 'error') {
    return (
      <div className="error-msg">
        <strong>Processing failed:</strong> {session.error ?? 'Unknown error'}
      </div>
    )
  }

  const anonymousIds = Array.from(
    new Set(session.segments.map((s) => s.speaker.anonymous_id)),
  )

  const knownSpeakers = Object.values(session.speaker_map).filter(Boolean)

  const totalSegments = session.segments.length
  const lowConfidenceCount = session.segments.filter((s) =>
    s.flags.includes('low_confidence'),
  ).length
  const meanConfidence =
    totalSegments > 0
      ? session.segments.reduce((acc, s) => acc + s.confidence, 0) / totalSegments
      : 0

  return (
    <div>
      <div className="review-sticky-header">
        <div className="review-session-heading review-session-heading--row">
          <div>
            {editingName ? (
              <div style={{ display: 'flex', gap: 4, alignItems: 'center', marginBottom: 2 }}>
                <input
                  autoFocus
                  value={nameValue}
                  placeholder={session.source_file}
                  onChange={(e) => setNameValue(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') void handleSaveName()
                    if (e.key === 'Escape') setEditingName(false)
                  }}
                  disabled={savingName}
                  style={{ fontSize: 18, padding: '2px 6px' }}
                />
                <button className="btn btn-primary" disabled={savingName} onClick={handleSaveName}>
                  {savingName ? '…' : 'Save'}
                </button>
                <button disabled={savingName} onClick={() => setEditingName(false)}>
                  Cancel
                </button>
              </div>
            ) : (
              <h2 style={{ marginBottom: 2 }}>
                {session.display_name ?? session.source_file}
                <button
                  title="Rename"
                  onClick={handleStartEditName}
                  style={{
                    marginLeft: 8,
                    fontSize: 12,
                    color: '#6b7280',
                    background: 'none',
                    border: 'none',
                    cursor: 'pointer',
                  }}
                >
                  Rename
                </button>
              </h2>
            )}
            <span style={{ fontSize: 12, color: '#6b7280' }}>
              Session: <code>{session.session_id.slice(0, 8)}</code> &nbsp;·&nbsp;
              {new Date(session.created_at).toLocaleString()}
              {session.display_name && <> &nbsp;·&nbsp; Source: {session.source_file}</>}
            </span>
          </div>
          <ExportBar sessionId={sessionId} />
        </div>

        {session.warning && (
          <div className="warning-msg">{session.warning}</div>
        )}

        {/* Audio player — only shown for audio-sourced sessions */}
        {session.audio_file && (
          <div className="audio-player-bar">
            <span className="audio-player-label">Audio</span>
            <audio
              ref={audioRef}
              controls
              src={audioUrl(sessionId)}
              className="audio-player"
            />
            <span className="audio-player-hint">Click a timestamp to jump</span>
          </div>
        )}
      </div>

      <div className="review-layout">
        {/* Sidebar */}
        <div className="review-sidebar">
          <SpeakerMapEditor
            anonymousIds={anonymousIds}
            speakerMap={session.speaker_map}
            onSave={handleSaveSpeakerMap}
          />
          <ConfidenceSummary
            totalSegments={totalSegments}
            lowConfidenceCount={lowConfidenceCount}
            meanConfidence={meanConfidence}
          />
        </div>

        {/* Main segment list */}
        <div className="review-main">
          <h3>Segments ({totalSegments})</h3>
          <div className="segment-list">
            {session.segments.map((seg) => (
              <SegmentRow
                key={seg.id}
                segment={seg}
                knownSpeakers={knownSpeakers}
                onSpeakerChange={handleSpeakerChange}
                onTextChange={handleTextChange}
                onSeek={session.audio_file ? handleSeek : undefined}
              />
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}
