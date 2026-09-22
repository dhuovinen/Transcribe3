import { useEffect, useState } from 'react'
import { listSessions } from '../api'
import type { SessionSummary } from '../types'

interface Props {
  onBack: () => void
}

const HISTORY_LIMIT = 10

/** Durations run from seconds to tens of minutes, so pick the unit per value. */
function formatDuration(seconds: number): string {
  if (seconds < 60) return `${seconds.toFixed(seconds < 10 ? 1 : 0)}s`
  const mins = Math.floor(seconds / 60)
  const secs = Math.round(seconds % 60)
  if (mins < 60) return `${mins}m ${String(secs).padStart(2, '0')}s`
  return `${Math.floor(mins / 60)}h ${String(mins % 60).padStart(2, '0')}m`
}

interface StageAverage {
  stage: string
  runs: number
  total: number
  average: number
  longest: number
}

/** Aggregate stage timings across runs, ordered by total time spent — the stage
 *  at the top is the one worth attacking. */
function averageByStage(sessions: SessionSummary[]): StageAverage[] {
  const acc = new Map<string, { runs: number; total: number; longest: number }>()
  for (const session of sessions) {
    for (const timing of session.stage_timings ?? []) {
      const entry = acc.get(timing.stage) ?? { runs: 0, total: 0, longest: 0 }
      entry.runs += 1
      entry.total += timing.seconds
      entry.longest = Math.max(entry.longest, timing.seconds)
      acc.set(timing.stage, entry)
    }
  }
  return [...acc.entries()]
    .map(([stage, e]) => ({ stage, runs: e.runs, total: e.total, average: e.total / e.runs, longest: e.longest }))
    .sort((a, b) => b.total - a.total)
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

export default function AdminView({ onBack }: Props) {
  const [sessions, setSessions] = useState<SessionSummary[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [expanded, setExpanded] = useState<string | null>(null)

  useEffect(() => {
    listSessions()
      .then((data) => {
        const sorted = [...data].sort(
          (a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime(),
        )
        setSessions(sorted.slice(0, HISTORY_LIMIT))
      })
      .catch((e) => setError(e instanceof Error ? e.message : 'Failed to load sessions'))
      .finally(() => setLoading(false))
  }, [])

  const timedSessions = sessions.filter((s) => (s.stage_timings ?? []).length > 0)
  const stageAverages = averageByStage(sessions)
  const totalStageSeconds = stageAverages.reduce((sum, r) => sum + r.total, 0) || 1

  return (
    <div>
      <h2>Admin: Recent Processing Runs</h2>
      <p style={{ fontSize: 13, color: '#6b7280', margin: '0 0 16px' }}>
        The exact parameters used for the last {HISTORY_LIMIT} sessions — useful for tracking
        down why a given run came out differently (different model, backend, or cleaning
        settings than you expected). Sessions created before this feature shipped show "—".
      </p>

      {loading && <p>Loading…</p>}
      {error && <div className="error-msg">{error}</div>}

      {!loading && !error && stageAverages.length > 0 && (
        <section className="panel settings-section" style={{ marginBottom: 20 }}>
          <h3>Time by stage</h3>
          <p className="settings-hint">
            Averaged over the {timedSessions.length} of the last {HISTORY_LIMIT} runs that
            recorded timings, longest first. Runs processed before this shipped aren't counted.
          </p>
          <table className="stage-table">
            <thead>
              <tr>
                <th>Stage</th>
                <th>Share of time</th>
                <th>Runs</th>
                <th>Average</th>
                <th>Longest</th>
              </tr>
            </thead>
            <tbody>
              {stageAverages.map((row) => (
                <tr key={row.stage}>
                  <td>{row.stage}</td>
                  <td>
                    <div className="stage-bar-wrap">
                      <div
                        className="stage-bar"
                        style={{ width: `${Math.max(2, (row.total / totalStageSeconds) * 100)}%` }}
                      />
                      <span className="stage-bar-label">
                        {((row.total / totalStageSeconds) * 100).toFixed(0)}%
                      </span>
                    </div>
                  </td>
                  <td>{row.runs}</td>
                  <td>{formatDuration(row.average)}</td>
                  <td>{formatDuration(row.longest)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )}

      {!loading && !error && sessions.length === 0 && <p>No sessions yet.</p>}

      {!loading && !error && sessions.length > 0 && (
        <div style={{ overflowX: 'auto' }}>
          <table>
            <thead>
              <tr>
                <th>Created</th>
                <th>Session</th>
                <th>LLM provider</th>
                <th>LLM model</th>
                <th>Mode</th>
                <th>Filler words</th>
                <th>False starts</th>
                <th>Threshold</th>
                <th>Transcription</th>
                <th>Time</th>
                <th>Mean conf.</th>
                <th>Notes</th>
              </tr>
            </thead>
            <tbody>
              {sessions.flatMap((s) => {
                const p = s.processing_params
                const timings = s.stage_timings ?? []
                const runSeconds = timings.reduce((sum, t) => sum + t.seconds, 0)
                const isOpen = expanded === s.session_id
                const rows = [
                  <tr key={s.session_id}>
                    <td>{formatDate(s.created_at)}</td>
                    <td>
                      <code style={{ fontSize: 12 }}>{s.session_id.slice(0, 8)}</code>
                      <div style={{ fontSize: 12, color: '#6b7280' }}>
                        {s.display_name ?? s.source_file}
                      </div>
                    </td>
                    <td>{p?.llm_provider_label ?? p?.llm_provider_id ?? '—'}</td>
                    <td>{p?.llm_model ?? '—'}</td>
                    <td>{p?.cleaning_mode ?? '—'}</td>
                    <td>{p?.filler_words ?? '—'}</td>
                    <td>{p?.remove_false_starts === null || p?.remove_false_starts === undefined ? '—' : p.remove_false_starts ? 'yes' : 'no'}</td>
                    <td>{p?.low_confidence_threshold ?? '—'}</td>
                    <td>
                      {p?.transcription_backend
                        ? `${p.transcription_backend}${p.whisper_model ? ` (${p.whisper_model})` : ''}`
                        : '—'}
                    </td>
                    <td>
                      {timings.length === 0 ? (
                        '—'
                      ) : (
                        <button
                          type="button"
                          className="stage-expand"
                          onClick={() => setExpanded(isOpen ? null : s.session_id)}
                          title={isOpen ? 'Hide stage breakdown' : 'Show stage breakdown'}
                        >
                          {isOpen ? '▾' : '▸'} {formatDuration(runSeconds)}
                        </button>
                      )}
                    </td>
                    <td>
                      {p?.attribution_enabled === false ? (
                        // Nothing scored these segments — they carry the parser's
                        // placeholder value, so a percentage here would be fiction.
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
                    <td style={{ maxWidth: 260, fontSize: 12, color: s.warning ? '#b45309' : '#6b7280' }}>
                      {p?.attribution_enabled === false && (
                        <span className="stage-off-chip">attribution off</span>
                      )}
                      {p?.cleaning_enabled === false && (
                        <span className="stage-off-chip">cleaning off</span>
                      )}
                      {s.warning ?? (s.status === 'error' ? 'Processing failed' : '—')}
                    </td>
                  </tr>,
                ]

                if (isOpen) {
                  rows.push(
                    <tr key={`${s.session_id}-stages`} className="stage-detail-row">
                      <td colSpan={12}>
                        <table className="stage-table stage-table--nested">
                          <tbody>
                            {timings.map((t, i) => (
                              <tr key={`${t.stage}-${i}`}>
                                <td>{t.stage}</td>
                                <td>
                                  <div className="stage-bar-wrap">
                                    <div
                                      className="stage-bar"
                                      style={{
                                        width: `${Math.max(2, (t.seconds / (runSeconds || 1)) * 100)}%`,
                                      }}
                                    />
                                    <span className="stage-bar-label">
                                      {((t.seconds / (runSeconds || 1)) * 100).toFixed(0)}%
                                    </span>
                                  </div>
                                </td>
                                <td>{formatDuration(t.seconds)}</td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </td>
                    </tr>,
                  )
                }
                return rows
              })}
            </tbody>
          </table>
        </div>
      )}

      <div className="form-row" style={{ marginTop: 24, gap: 12 }}>
        <button onClick={onBack}>Back</button>
      </div>
    </div>
  )
}
