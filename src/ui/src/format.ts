export function formatDate(iso: string): string {
  const d = new Date(iso)
  return d.toLocaleString(undefined, {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

export function formatDuration(seconds: number | null): string {
  if (seconds == null) return '—'
  const total = Math.round(seconds)
  const h = Math.floor(total / 3600)
  const m = Math.floor((total % 3600) / 60)
  const s = total % 60
  const mm = h > 0 ? String(m).padStart(2, '0') : String(m)
  const ss = String(s).padStart(2, '0')
  return h > 0 ? `${h}:${mm}:${ss}` : `${mm}:${ss}`
}

/** Compact total, e.g. "2.3h" for long totals, "45m" under an hour. */
export function formatHoursCompact(totalSeconds: number): string {
  const hours = totalSeconds / 3600
  if (hours >= 1) return `${hours.toFixed(1)}h`
  return `${Math.round(totalSeconds / 60)}m`
}
