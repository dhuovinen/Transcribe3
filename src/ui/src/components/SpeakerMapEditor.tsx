import { useState } from 'react'

interface Props {
  anonymousIds: string[]
  speakerMap: Record<string, string>
  onSave: (map: Record<string, string>) => Promise<void>
}

export default function SpeakerMapEditor({ anonymousIds, speakerMap, onSave }: Props) {
  const [names, setNames] = useState<Record<string, string>>(() => {
    const initial: Record<string, string> = {}
    for (const id of anonymousIds) {
      initial[id] = speakerMap[id] ?? ''
    }
    return initial
  })
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  const [error, setError] = useState<string | null>(null)

  function handleChange(id: string, value: string) {
    setNames((prev) => ({ ...prev, [id]: value }))
    setSaved(false)
  }

  async function handleSave() {
    // Build map excluding empty entries
    const map: Record<string, string> = {}
    for (const [id, name] of Object.entries(names)) {
      if (name.trim()) map[id] = name.trim()
    }

    setSaving(true)
    setError(null)
    try {
      await onSave(map)
      setSaved(true)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Save failed')
    } finally {
      setSaving(false)
    }
  }

  if (anonymousIds.length === 0) {
    return (
      <div className="panel">
        <h3>Speaker Names</h3>
        <p style={{ color: '#9ca3af', fontSize: 13 }}>No speakers detected in this session.</p>
      </div>
    )
  }

  return (
    <div className="panel">
      <h3>Speaker Names</h3>
      <p style={{ color: '#6b7280', fontSize: 12, marginTop: 0, marginBottom: 12 }}>
        Assign real names to anonymous speaker IDs.
      </p>
      {anonymousIds.map((id) => (
        <div key={id} className="speaker-map-row">
          <span className="anon-id">{id}</span>
          <span style={{ color: '#9ca3af', fontSize: 12 }}>→</span>
          <input
            type="text"
            placeholder="Real name…"
            value={names[id] ?? ''}
            onChange={(e) => handleChange(id, e.target.value)}
            style={{ flex: 1 }}
          />
        </div>
      ))}

      {error && <div className="error-msg">{error}</div>}

      <div style={{ marginTop: 12, display: 'flex', alignItems: 'center', gap: 10 }}>
        <button className="btn btn-primary" onClick={handleSave} disabled={saving}>
          {saving ? 'Saving…' : 'Save Names'}
        </button>
        {saved && <span style={{ color: '#16a34a', fontSize: 13 }}>Saved!</span>}
      </div>
    </div>
  )
}
