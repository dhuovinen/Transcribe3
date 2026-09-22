import { useEffect, useState } from 'react'
import {
  archiveRecording,
  configureArchive,
  deleteLocalRecording,
  getArchiveStatus,
  restoreRecording,
} from '../api'
import type { ArchiveRecordingStatus, ArchiveStatus } from '../types'

interface Props {
  onBack: () => void
}

function formatBytes(value: number | null): string {
  if (value === null) return '—'
  const units = ['B', 'KB', 'MB', 'GB', 'TB']
  let size = value
  let index = 0
  while (size >= 1024 && index < units.length - 1) {
    size /= 1024
    index += 1
  }
  return `${size.toFixed(index === 0 ? 0 : 1)} ${units[index]}`
}

function locationLabel(recording: ArchiveRecordingStatus): string {
  if (recording.local_available && recording.archive_available) return 'Local + archive'
  if (recording.local_available) return 'Local only'
  if (recording.archive_available) return 'Archive only'
  return 'Recording unavailable'
}

export default function ArchiveView({ onBack }: Props) {
  const [status, setStatus] = useState<ArchiveStatus | null>(null)
  const [archiveDir, setArchiveDir] = useState('')
  const [busy, setBusy] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)

  async function load() {
    setError(null)
    try {
      const result = await getArchiveStatus()
      setStatus(result)
      setArchiveDir((current) => current || result.archive_dir || result.suggested_archive_dir)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load archive storage')
    }
  }

  useEffect(() => { void load() }, [])

  async function handleConfigure() {
    setBusy('configure')
    setError(null)
    setNotice(null)
    try {
      const result = await configureArchive(archiveDir)
      setStatus(result)
      setArchiveDir(result.archive_dir ?? archiveDir)
      setNotice('Archive folder is ready.')
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not configure archive folder')
    } finally {
      setBusy(null)
    }
  }

  async function perform(
    recording: ArchiveRecordingStatus,
    action: 'copy' | 'offload' | 'delete' | 'restore',
  ) {
    const prompts = {
      copy: `Copy “${recording.display_name ?? recording.source_file}” to the archive and keep the local recording?`,
      offload: `Offload “${recording.display_name ?? recording.source_file}”? The app will verify the archive copy before removing the local recording.`,
      delete: `Remove the local recording for “${recording.display_name ?? recording.source_file}”? The verified archive copy will be kept.`,
      restore: `Restore a local copy of “${recording.display_name ?? recording.source_file}” from the archive?`,
    }
    if (!confirm(prompts[action])) return

    setBusy(`${action}:${recording.session_id}`)
    setError(null)
    setNotice(null)
    try {
      if (action === 'copy') await archiveRecording(recording.session_id, false)
      if (action === 'offload') await archiveRecording(recording.session_id, true)
      if (action === 'delete') await deleteLocalRecording(recording.session_id)
      if (action === 'restore') await restoreRecording(recording.session_id)
      await load()
      setNotice(
        action === 'copy' ? 'Recording copied to archive.'
          : action === 'offload' ? 'Recording offloaded to archive.'
          : action === 'delete' ? 'Local recording removed.'
          : 'Local recording restored.',
      )
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Storage operation failed')
    } finally {
      setBusy(null)
    }
  }

  if (!status && !error) return <p>Loading archive storage…</p>

  return (
    <div className="admin-view">
      <div className="admin-heading">
        <div>
          <h2>Archive administration</h2>
          <p>Archive stores verified copies of original recordings. Session transcripts and metadata always stay on this computer.</p>
        </div>
        <button onClick={onBack}>Back to sessions</button>
      </div>

      <section className="panel archive-config">
        <h3>Archive folder</h3>
        <div className="form-row archive-config-row">
          <input
            type="text"
            aria-label="Archive folder"
            value={archiveDir}
            onChange={(e) => setArchiveDir(e.target.value)}
            placeholder="/Volumes/Extreme SSD/Transcribe3 Archive"
          />
          <button className="btn btn-primary" disabled={busy === 'configure'} onClick={handleConfigure}>
            {busy === 'configure' ? 'Preparing…' : 'Set up archive'}
          </button>
        </div>
        <p className={status?.archive_connected ? 'storage-connected' : 'storage-disconnected'}>
          {status?.archive_connected
            ? `Connected: ${status.archive_dir}`
            : 'Not connected. Connect the external drive, then set up or confirm the folder above.'}
        </p>
      </section>

      {status && (
        <div className="storage-summary" aria-label="Storage capacity">
          <div className="panel"><span>Local free space</span><strong>{formatBytes(status.local_free_bytes)}</strong></div>
          <div className="panel"><span>Archive free space</span><strong>{formatBytes(status.archive_free_bytes)}</strong></div>
          <div className="panel"><span>Audio recordings</span><strong>{status.recordings.length}</strong></div>
        </div>
      )}

      <section className="panel archive-guide" aria-labelledby="archive-actions-heading">
        <h3 id="archive-actions-heading">How storage actions work</h3>
        <dl>
          <div>
            <dt>Archive copy</dt>
            <dd>
              Copies the original recording to the external archive and keeps the local
              recording available for playback. Use this when you want a second copy
              before freeing any disk space.
            </dd>
          </div>
          <div>
            <dt>Offload</dt>
            <dd>
              Copies the recording to the archive, verifies that copy with a SHA-256
              checksum, then removes the local recording. The transcript and session
              details stay on this computer; restore the recording locally any time
              from this page.
            </dd>
          </div>
        </dl>
      </section>

      {error && <div className="error-msg">{error}</div>}
      {notice && <div className="success-msg">{notice}</div>}

      <section className="archive-recordings">
        <h3>Recordings</h3>
        {!status || status.recordings.length === 0 ? (
          <div className="empty-state"><p>No audio recordings are available to manage.</p></div>
        ) : (
          <table>
            <thead><tr><th>Recording</th><th>Storage</th><th>Size</th><th>Actions</th></tr></thead>
            <tbody>
              {status.recordings.map((recording) => {
                const actionKey = (action: string) => `${action}:${recording.session_id}`
                const isBusy = busy?.endsWith(recording.session_id) ?? false
                return (
                  <tr key={recording.session_id}>
                    <td>
                      <strong>{recording.display_name ?? recording.source_file}</strong>
                      {recording.display_name && <small>Source: {recording.source_file}</small>}
                    </td>
                    <td><span className="storage-badge">{locationLabel(recording)}</span></td>
                    <td>{formatBytes(recording.local_size_bytes ?? recording.archive_size_bytes)}</td>
                    <td className="archive-actions">
                      {recording.local_available && !recording.archive_available && <>
                        <button disabled={isBusy || !status.archive_connected} onClick={() => void perform(recording, 'copy')}>
                          {busy === actionKey('copy') ? 'Copying…' : 'Archive copy'}
                        </button>
                        <button className="btn btn-primary" disabled={isBusy || !status.archive_connected} onClick={() => void perform(recording, 'offload')}>
                          {busy === actionKey('offload') ? 'Offloading…' : 'Offload'}
                        </button>
                      </>}
                      {recording.local_available && recording.archive_available && (
                        <button className="btn btn-danger" disabled={isBusy} onClick={() => void perform(recording, 'delete')}>
                          {busy === actionKey('delete') ? 'Removing…' : 'Remove local'}
                        </button>
                      )}
                      {!recording.local_available && recording.archive_available && (
                        <button className="btn btn-primary" disabled={isBusy || !status.archive_connected} onClick={() => void perform(recording, 'restore')}>
                          {busy === actionKey('restore') ? 'Restoring…' : 'Restore locally'}
                        </button>
                      )}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        )}
      </section>
    </div>
  )
}
