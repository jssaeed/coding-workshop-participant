// A small floating readout that follows the pointer over a chart. Position
// is relative to the chart's wrapper (which has position: relative).
export default function Tooltip({ tip }) {
  if (!tip) return null
  return (
    <div className="chart-tooltip" style={{ left: tip.x + 12, top: tip.y + 12 }} role="status">
      <strong>{tip.value}</strong>
      <span className="chart-tooltip-key" style={{ background: tip.color }} />
      {tip.label}
    </div>
  )
}
