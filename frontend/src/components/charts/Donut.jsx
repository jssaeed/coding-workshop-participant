import { useState } from 'react'
import Tooltip from './Tooltip'

// A ring split into one arc per item, with the total in the middle and a
// legend beside it listing every item's count (so nothing depends on colour
// alone). items: [{ key, label, value, color }]. Items with value 0 are
// listed in the legend but drawn as nothing. When onSelect is given, every
// arc and legend row is clickable and calls it with the item.
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

export default function Donut({ items, title, centreLabel = 'tickets', onSelect }) {
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

  // An arc got keyboard focus: put the readout at the middle of that arc.
  // A click focuses the arc too, but by then the pointer readout is already
  // showing for it, so leave that one where it is (otherwise the readout
  // would jump to a fixed spot on every click).
  function showFocusTip(element, arc) {
    if (hovered === arc.key) return
    const chart = element.closest('.chart').getBoundingClientRect()
    const svgBox = element.closest('svg').getBoundingClientRect()
    const middle = ((arc.start + arc.end) / 2 - 90) * (Math.PI / 180)
    const scale = svgBox.width ? svgBox.width / SIZE : 1
    const x = svgBox.left - chart.left + (cx + r * Math.cos(middle)) * scale
    const y = svgBox.top - chart.top + (cy + r * Math.sin(middle)) * scale
    setTip({ x, y, value: arc.value, label: arc.label, color: arc.color })
    setHovered(arc.key)
  }
  function hideTip() {
    setTip(null)
    setHovered(null)
  }

  // Enter or Space on a focused arc or row counts as a click
  function pressKey(event, item) {
    if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault()
      onSelect(item)
    }
  }

  return (
    <div className={onSelect ? 'chart donut donut-clickable' : 'chart donut'}>
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
                 onFocus={(e) => showFocusTip(e.currentTarget, arc)} onBlur={hideTip}
                 role={onSelect ? 'button' : undefined} aria-label={onSelect ? `${arc.label}: ${arc.value}` : undefined}
                 onClick={onSelect ? () => onSelect(arc) : undefined}
                 onKeyDown={onSelect ? (e) => pressKey(e, arc) : undefined}>
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
                <td>
                  {onSelect
                    ? <button type="button" className="legend-link" onClick={() => onSelect(item)}>{item.label}</button>
                    : item.label}
                </td>
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
