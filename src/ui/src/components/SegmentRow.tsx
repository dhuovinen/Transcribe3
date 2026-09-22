import { useEffect, useRef, useState } from 'react'
import type { TranscriptSegment } from '../types'

interface Props {
  segment: TranscriptSegment
  knownSpeakers: string[]   // resolved names from speaker_map
  onSpeakerChange: (segmentId: string, speaker: string) => void
  onTextChange: (segmentId: string, text: string) => Promise<void>
  onSeek?: (startTime: number) => void
}

function formatTime(secs: number): string {
  if (secs === 0) return '0.0s'
  const m = Math.floor(secs / 60)
  const s = (secs % 60).toFixed(1)
  return m > 0 ? `${m}m${s}s` : `${s}s`
}

function confClass(c: number): string {
  if (c >= 0.8) return 'conf-high'
  if (c >= 0.6) return 'conf-mid'
  return 'conf-low'
}

export default function SegmentRow({
  segment,
  knownSpeakers,
  onSpeakerChange,
  onTextChange,
  onSeek,
}: Props) {
  const [dropdownOpen, setDropdownOpen] = useState(false)
  const [draftText, setDraftText] = useState(segment.text)
  const [textSaveError, setTextSaveError] = useState<string | null>(null)
  const dropdownRef = useRef<HTMLDivElement>(null)
  const isLowConf = segment.flags.includes('low_confidence')

  useEffect(() => {
    setDraftText(segment.text)
  }, [segment.id, segment.text])

  // Close dropdown on outside click
  useEffect(() => {
    if (!dropdownOpen) return
    function handleClick(e: MouseEvent) {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) {
        setDropdownOpen(false)
      }
    }
    document.addEventListener('mousedown', handleClick)
    return () => document.removeEventListener('mousedown', handleClick)
  }, [dropdownOpen])

  const displayName = segment.speaker.resolved_name ?? segment.speaker.anonymous_id

  // Build option list: known speakers + anonymous_id (if not already present)
  const options = Array.from(
    new Set([
      ...knownSpeakers,
      segment.speaker.anonymous_id,
    ]),
  )

  function handleSelect(name: string) {
    setDropdownOpen(false)
    onSpeakerChange(segment.id, name)
  }

  async function handleTextBlur() {
    if (draftText === segment.text) return
    setTextSaveError(null)
    try {
      await onTextChange(segment.id, draftText)
    } catch (error) {
      setTextSaveError(error instanceof Error ? error.message : 'Could not save text')
    }
  }

  const timestamps =
    segment.start_time === 0 && segment.end_time === 0
      ? '–'
      : `${formatTime(segment.start_time)} – ${formatTime(segment.end_time)}`

  return (
    <div className={`segment-row${isLowConf ? ' low-confidence' : ''}`}>
      {/* Timestamp — clickable when audio is available */}
      <div
        className={`segment-timestamp${onSeek ? ' segment-timestamp--seekable' : ''}`}
        onClick={onSeek ? () => onSeek(segment.start_time) : undefined}
        title={onSeek ? 'Click to jump to this position' : undefined}
      >
        {timestamps}
      </div>

      {/* Speaker */}
      <div className="segment-speaker" ref={dropdownRef}>
        <span
          className="speaker-badge"
          onClick={() => setDropdownOpen((o) => !o)}
          title="Click to change speaker"
        >
          {displayName}
        </span>
        {dropdownOpen && (
          <div className="speaker-dropdown">
            {options.map((name) => (
              <button key={name} onClick={() => handleSelect(name)}>
                {name}
              </button>
            ))}
          </div>
        )}
      </div>

      {/* Text */}
      <div className="segment-text-wrapper">
        <textarea
          className="segment-text"
          aria-label="Edit transcript text"
          value={draftText}
          onChange={(event) => setDraftText(event.target.value)}
          onBlur={() => { void handleTextBlur() }}
        />
        {textSaveError && <span className="segment-text-error">{textSaveError}</span>}
      </div>

      {/* Right column: confidence + flags */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 4, alignItems: 'flex-end' }}>
        <span className={confClass(segment.confidence)} style={{ fontSize: 12 }}>
          {(segment.confidence * 100).toFixed(0)}%
        </span>
        <div className="segment-flags">
          {segment.flags
            .filter((f) => f !== 'low_confidence')
            .map((f) => (
              <span key={f} className={`flag-chip ${f}`}>
                {f.replace(/_/g, ' ')}
              </span>
            ))}
          {isLowConf && (
            <span className="flag-chip low_confidence">low conf</span>
          )}
        </div>
      </div>
    </div>
  )
}
