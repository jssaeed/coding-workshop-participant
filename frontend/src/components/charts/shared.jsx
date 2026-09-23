import { STATUSES, STATUS_CHART_COLORS, label } from '../../services/format'

// Date ranges offered by every statistics view
export const RANGES = [
  { label: 'Last 7 days', value: 7 },
  { label: 'Last 30 days', value: 30 },
  { label: 'Last 90 days', value: 90 },
]

// {open: 5, in_progress: 2, ...} -> the items a Donut wants, always in the
// same order and colour so the chart reads the same on every page.
// omit lists statuses to leave out (an assigned ticket can never be "open").
export function statusItems(byStatus, omit = []) {
  return STATUSES.filter((status) => !omit.includes(status)).map((status) => ({
    key: status,
    label: label(status),
    value: byStatus[status],
    color: STATUS_CHART_COLORS[status],
  }))
}

// A stat tile: one big number with a caption
export function Tile({ value, caption }) {
  return (
    <div className="tile">
      <div className="tile-value">{value}</div>
      <div className="tile-caption">{caption}</div>
    </div>
  )
}
