import { exportUrl } from '../api'
import type { OutputFormat } from '../types'

const FORMATS: OutputFormat[] = ['json', 'txt', 'srt', 'vtt']

interface Props {
  sessionId: string
}

export default function ExportBar({ sessionId }: Props) {
  return (
    <div className="export-bar">
      <span>Export as:</span>
      {FORMATS.map((fmt) => (
        <a
          key={fmt}
          href={exportUrl(sessionId, fmt)}
          download
          className="export-btn"
        >
          {fmt.toUpperCase()}
        </a>
      ))}
    </div>
  )
}
