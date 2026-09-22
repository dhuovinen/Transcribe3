import { useEffect, useState } from 'react'
import { audioUrl, deleteSession, listSessions, renameSession } from '../api'
import type { SessionSummary } from '../types'

interface Props {
  onSelectSession: (sessionId: string) => void
  onNewSession: () => void
}

function formatDate(iso: string): string {
  const d = new Date(iso)
  return d.toLocaleString(undefined, {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

function formatDuration(seconds: number | null): string {
  if (seconds == null) return '—'
  const total = Math.round(seconds)
  const h = Math.floor(total / 3600)
  const m = Math.floor((total % 3600) / 60)
  const s = total % 60
  const mm = h > 0 ? String(m).padStart(2, '0') : String(m)
  const ss = String(s).padStart(2, '0')
  return h > 0 ? `${h}:${mm}:${ss}` : `${mm}:${ss}`
}

export default function SessionList({ onSelectSession, onNewSession }: Props) {
  const [sessions, setSessions] = useState<SessionSummary[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [deletingId, setDeletingId] = useState<string | null>(null)
  const [editingId, setEditingId] = useState<string | null>(null)
  const [editValue, setEditValue] = useState('')
  const [savingId, setSavingId] = useState<string | null>(null)

  async function load() {
    setLoading(true)
    setError(null)
    try {
      const data = await listSessions()
      setSessions(data)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load sessions')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { void load() }, [])

  // Refresh periodically while any session is still processing
  useEffect(() => {
    if (!sessions.some((s) => s.status === 'processing')) return
    const timer = setInterval(async () => {
      try {
        setSessions(await listSessions())
      } catch {
        // transient poll failure — keep trying
      }
    }, 3000)
    return () => clearInterval(timer)
  }, [sessions])

  async function handleDelete(e: React.MouseEvent, sessionId: string) {
    e.stopPropagation()
    if (!confirm(`Delete session ${sessionId.slice(0, 8)}…? This cannot be undone.`)) return
    setDeletingId(sessionId)
    try {
      await deleteSession(sessionId)
      setSessions((prev) => prev.filter((s) => s.session_id !== sessionId))
    } catch (e) {
      alert(e instanceof Error ? e.message : 'Delete failed')
    } finally {
      setDeletingId(null)
    }
  }

  function handleStartEdit(e: React.MouseEvent, s: SessionSummary) {
    e.stopPropagation()
    setEditingId(s.session_id)
    setEditValue(s.display_name ?? s.source_file)
  }

  function handleCancelEdit() {
    setEditingId(null)
    setEditValue('')
  }

  async function handleSaveRename(sessionId: string) {
    const trimmed = editValue.trim()
    setSavingId(sessionId)
    try {
      const updated = await renameSession(sessionId, trimmed || null)
      setSessions((prev) =>
        prev.map((s) =>
          s.session_id === sessionId ? { ...s, display_name: updated.display_name } : s,
        ),
      )
      setEditingId(null)
    } catch (e) {
      alert(e instanceof Error ? e.message : 'Rename failed')
    } finally {
      setSavingId(null)
    }
  }

  if (loading) return <p>Loading sessions…</p>

  if (error) return <div className="error-msg">{error}</div>

  if (sessions.length === 0) {
    return (
      <div className="empty-state">
        <p>No sessions yet.</p>
        <button className="btn btn-primary" onClick={onNewSession}>
          Upload a transcript to get started
        </button>
      </div>
    )
  }

  return (
    <table>
      <thead>
        <tr>
          <th>Session ID</th>
          <th>Name</th>
          <th>Created</th>
          <th>Duration</th>
          <th>Segments</th>
          <th>Low-confidence</th>
          <th>Mean Conf.</th>
          <th></th>
        </tr>
      </thead>
      <tbody>
        {sessions.map((s) => (
          <tr key={s.session_id} onClick={() => onSelectSession(s.session_id)}>
            <td>
              <code style={{ fontSize: '12px' }}>{s.session_id.slice(0, 8)}</code>
            </td>
            <td>
              {editingId === s.session_id ? (
                <span onClick={(e) => e.stopPropagation()} style={{ display: 'inline-flex', gap: 4 }}>
                  <input
                    autoFocus
                    value={editValue}
                    placeholder={s.source_file}
                    onChange={(e) => setEditValue(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter') void handleSaveRename(s.session_id)
                      if (e.key === 'Escape') handleCancelEdit()
                    }}
                    disabled={savingId === s.session_id}
                    style={{ fontSize: 14, padding: '2px 6px' }}
                  />
                  <button
                    className="btn btn-primary"
                    disabled={savingId === s.session_id}
                    onClick={() => handleSaveRename(s.session_id)}
                  >
                    {savingId === s.session_id ? '…' : 'Save'}
                  </button>
                  <button onClick={handleCancelEdit} disabled={savingId === s.session_id}>
                    Cancel
                  </button>
                </span>
              ) : (
                <span
                  title={s.display_name ? `Source file: ${s.source_file}` : undefined}
                  onDoubleClick={(e) => handleStartEdit(e, s)}
                >
                  {s.display_name ?? s.source_file}
                  <button
                    className="btn-rename"
                    title="Rename"
                    onClick={(e) => handleStartEdit(e, s)}
                    style={{
                      marginLeft: 6,
                      fontSize: 12,
                      color: '#6b7280',
                      background: 'none',
                      border: 'none',
                      cursor: 'pointer',
                      padding: 0,
                    }}
                  >
                    Rename
                  </button>
                </span>
              )}
              {s.status === 'processing' && (
                <span className="status-badge processing" style={{ marginLeft: 8 }}>
                  processing…
                </span>
              )}
              {s.status === 'error' && (
                <span className="status-badge error" style={{ marginLeft: 8 }}>
                  failed
                </span>
              )}
            </td>
            <td>{formatDate(s.created_at)}</td>
            <td>{formatDuration(s.audio_duration_seconds)}</td>
            <td>{s.segment_count}</td>
            <td>
              {s.low_confidence_count > 0 ? (
                <span className="conf-low">{s.low_confidence_count}</span>
              ) : (
                <span className="conf-high">{s.low_confidence_count}</span>
              )}
            </td>
            <td>
              {s.processing_params?.attribution_enabled === false ? (
                <span className="settings-status--muted" title="Attribution was off — confidence is unscored">
                  not scored
                </span>
              ) : (
                <span
                  className={
                    s.mean_confidence >= 0.8
                      ? 'conf-high'
                      : s.mean_confidence >= 0.6
                      ? 'conf-mid'
                      : 'conf-low'
                  }
                >
                  {(s.mean_confidence * 100).toFixed(1)}%
                </span>
              )}
            </td>
            <td>
              <span style={{ display: 'inline-flex', gap: 8, alignItems: 'center' }}>
                {s.audio_file && (
                  <a
                    href={audioUrl(s.session_id)}
                    download={s.audio_file}
                    className="btn"
                    title="Download audio"
                    onClick={(e) => e.stopPropagation()}
                  >
                    Audio
                  </a>
                )}
                <button
                  className="btn btn-danger"
                  disabled={deletingId === s.session_id}
                  onClick={(e) => handleDelete(e, s.session_id)}
                >
                  {deletingId === s.session_id ? '…' : 'Delete'}
                </button>
              </span>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}
