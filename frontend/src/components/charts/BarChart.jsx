import { useState } from 'react'
import Tooltip from './Tooltip'

// Horizontal bars, one series, one colour. items: [{ key, label, value }].
// Each bar is clickable when onSelect is given (used for the drill-down).
const BAR = 14
const ROW = 30
const LABEL_WIDTH = 120
const WIDTH = 520
const COLOR = '#2a78d6'

export default function BarChart({ items, title, onSelect, emptyText = 'No tickets in this range.' }) {
  const [tip, setTip] = useState(null)
  const [hovered, setHovered] = useState(null)
  const max = Math.max(1, ...items.map((item) => item.value))
  const plotWidth = WIDTH - LABEL_WIDTH - 48
  const height = Math.max(ROW, items.length * ROW) + 8

  function showTip(event, item) {
    const box = event.currentTarget.closest('.chart').getBoundingClientRect()
    setTip({ x: event.clientX - box.left, y: event.clientY - box.top, value: item.value, label: item.label, color: COLOR })
    setHovered(item.key)
  }
  function hideTip() {
    setTip(null)
    setHovered(null)
  }

  return (
    <div className="chart bars">
      {title && <div className="chart-title">{title}</div>}
      {items.length === 0 && <p className="muted">{emptyText}</p>}
      {items.length > 0 && (
        <svg width="100%" viewBox={`0 0 ${WIDTH} ${height}`} role="img" aria-label={title}>
          {items.map((item, index) => {
            const y = index * ROW + 4
            const w = Math.max(2, (item.value / max) * plotWidth)
            const clickable = Boolean(onSelect && item.selectable !== false)
            return (
              <g key={item.key}
                 className={clickable ? 'bar-row bar-clickable' : 'bar-row'}
                 onPointerMove={(e) => showTip(e, item)} onPointerLeave={hideTip}
                 onClick={clickable ? () => onSelect(item) : undefined}
                 tabIndex={clickable ? 0 : -1}
                 onKeyDown={clickable ? (e) => { if (e.key === 'Enter' || e.key === ' ') onSelect(item) } : undefined}>
                {/* a full-width invisible hit area, bigger than the bar */}
                <rect x={0} y={y} width={WIDTH} height={ROW - 2} fill="transparent" />
                <text x={LABEL_WIDTH - 10} y={y + ROW / 2 + 1} textAnchor="end" dominantBaseline="middle" className="bar-label">
                  {item.label}
                </text>
                <rect x={LABEL_WIDTH} y={y + (ROW - 2 - BAR) / 2} width={w} height={BAR} rx={0}
                      fill={COLOR} opacity={hovered && hovered !== item.key ? 0.45 : 1} />
                <text x={LABEL_WIDTH + w + 8} y={y + ROW / 2 + 1} dominantBaseline="middle" className="bar-value">
                  {item.value}
                </text>
              </g>
            )
          })}
        </svg>
      )}
      <Tooltip tip={tip} />
    </div>
  )
}
