interface Props {
  totalSegments: number
  lowConfidenceCount: number
  meanConfidence: number
}

export default function ConfidenceSummary({
  totalSegments,
  lowConfidenceCount,
  meanConfidence,
}: Props) {
  const pct = (meanConfidence * 100).toFixed(1)
  const confClass =
    meanConfidence >= 0.8 ? 'conf-high' : meanConfidence >= 0.6 ? 'conf-mid' : 'conf-low'

  return (
    <div className="panel">
      <h3>Confidence Summary</h3>
      <div className="conf-summary-grid">
        <div className="conf-summary-item">
          <div className="value">{totalSegments}</div>
          <div className="label">Segments</div>
        </div>
        <div className="conf-summary-item">
          <div className={`value ${lowConfidenceCount > 0 ? 'conf-low' : 'conf-high'}`}>
            {lowConfidenceCount}
          </div>
          <div className="label">Low Conf.</div>
        </div>
        <div className="conf-summary-item">
          <div className={`value ${confClass}`}>{pct}%</div>
          <div className="label">Mean Conf.</div>
        </div>
      </div>
    </div>
  )
}
