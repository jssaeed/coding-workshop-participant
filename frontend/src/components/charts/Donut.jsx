import { useState } from 'react'
import Tooltip from './Tooltip'

// A ring split into one arc per item, with the total in the middle and a
// legend beside it listing every item's count (so nothing depends on colour
// alone). items: [{ key, label, value, color }]. Items with value 0 are
// listed in the legend but drawn as nothing.
const SIZE = 150
const STROKE = 20
const GAP_DEGREES = 2 // a small gap between arcs so they read as separate

function arcPath(cx, cy, r, startDeg, endDeg) {
  const toXY = (deg) => {
    const rad = ((deg - 90) * Math.PI) / 180
    return [cx + r * Math.cos(rad), cy + r * Math.sin(rad)]
  }
  const [x1, y1] = toXY(startDeg)
  const [x2, y2] = toXY(endDeg)
  const large = endDeg - startDeg > 180 ? 1 : 0
  return `M ${x1} ${y1} A ${r} ${r} 0 ${large} 1 ${x2} ${y2}`
}

export default function Donut({ items, title, centreLabel = 'tickets' }) {
  const [tip, setTip] = useState(null)
  const [hovered, setHovered] = useState(null)
  const total = items.reduce((sum, item) => sum + item.value, 0)
  const cx = SIZE / 2
  const cy = SIZE / 2
  const r = SIZE / 2 - STROKE / 2 - 2

  // Work out each arc's start and end angle
  let angle = 0
  const arcs = items
    .filter((item) => item.value > 0)
    .map((item) => {
      const sweep = (item.value / total) * 360
      const arc = { ...item, start: angle, end: angle + sweep }
      angle += sweep
      return arc
    })

  function showTip(event, item) {
    const box = event.currentTarget.closest('.chart').getBoundingClientRect()
    setTip({ x: event.clientX - box.left, y: event.clientY - box.top, value: item.value, label: item.label, color: item.color })
    setHovered(item.key)
  }
  function hideTip() {
    setTip(null)
    setHovered(null)
  }

  return (
    <div className="chart donut">
      {title && <div className="chart-title">{title}</div>}
      <div className="donut-body">
        <svg width={SIZE} height={SIZE} viewBox={`0 0 ${SIZE} ${SIZE}`} role="img" aria-label={`${title || 'Breakdown'}: ${total} ${centreLabel}`}>
          {total === 0 && <circle cx={cx} cy={cy} r={r} fill="none" stroke="#e5e7eb" strokeWidth={STROKE} />}
          {arcs.map((arc) => {
            // Shrink each arc by the gap unless it is the only one (a full ring)
            const trim = arcs.length > 1 ? GAP_DEGREES / 2 : 0
            const start = arc.start + trim
            const end = Math.max(start + 0.5, arc.end - trim)
            const full = arcs.length === 1
            return (
              <g key={arc.key} onPointerMove={(e) => showTip(e, arc)} onPointerLeave={hideTip} tabIndex={0}
                 onFocus={(e) => showTip({ currentTarget: e.currentTarget, clientX: 0, clientY: 0 }, arc)} onBlur={hideTip}>
                {full ? (
                  <circle cx={cx} cy={cy} r={r} fill="none" stroke={arc.color} strokeWidth={STROKE} />
                ) : (
                  <path d={arcPath(cx, cy, r, start, end)} fill="none" stroke={arc.color} strokeWidth={STROKE}
                        strokeLinecap="butt" opacity={hovered && hovered !== arc.key ? 0.45 : 1} />
                )}
              </g>
            )
          })}
          <text x={cx} y={cy - 4} textAnchor="middle" className="donut-total">{total}</text>
          <text x={cx} y={cy + 16} textAnchor="middle" className="donut-caption">{centreLabel}</text>
        </svg>
        <table className="chart-legend">
          <tbody>
            {items.map((item) => (
              <tr key={item.key} className={hovered && hovered !== item.key ? 'legend-dim' : ''}
                  onPointerEnter={() => setHovered(item.key)} onPointerLeave={() => setHovered(null)}>
                <td><span className="legend-swatch" style={{ background: item.color }} /></td>
                <td>{item.label}</td>
                <td className="legend-value">{item.value}</td>
                <td className="legend-pct">{total ? Math.round((item.value / total) * 100) : 0}%</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <Tooltip tip={tip} />
    </div>
  )
}
