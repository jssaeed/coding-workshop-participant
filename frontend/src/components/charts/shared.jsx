import {
  CATEGORIES, CATEGORY_CHART_COLORS, ENGINEER_CHART_COLORS, PRIORITIES, PRIORITY_CHART_COLORS, STATUSES, STATUS_CHART_COLORS,
  categoryLabel, label,
} from '../../services/format'

// Date ranges offered by every statistics view
export const RANGES = [
  { label: 'Last 7 days', value: 7 },
  { label: 'Last 14 days', value: 14 },
  { label: 'Last 30 days', value: 30 },
  { label: 'Last 90 days', value: 90 },
]
export const DEFAULT_DAYS = 14

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

// {"1": 4, "2": 7, ...} (the API's byPriority) -> Donut items, most urgent
// first, so the ring and legend always run 1 to 5.
export function priorityItems(byPriority) {
  return PRIORITIES.map((priority) => ({
    key: priority,
    label: priority === 1 ? 'Priority 1 · most urgent' : priority === 5 ? 'Priority 5 · least urgent' : `Priority ${priority}`,
    value: byPriority[priority] ?? 0,
    color: PRIORITY_CHART_COLORS[priority],
  }))
}

// {plumbing: 6, electrical: 3, ...} (the API's byCategory) -> Donut items,
// always in the same order and colour, like the status and priority rings.
// A category with no tickets is still listed in the legend (as 0).
export function categoryItems(byCategory) {
  return CATEGORIES.map((category) => ({
    key: category,
    label: categoryLabel(category),
    value: byCategory[category] ?? 0,
    color: CATEGORY_CHART_COLORS[category],
  }))
}

// The engineers list (the API's GET /incidents/stats/engineers) -> Donut
// items: one slice per engineer, sized by the tickets assigned to them. The
// key is the engineer's id, so a click can select them.
export function engineerItems(engineers) {
  return engineers.map((engineer, index) => ({
    key: engineer.id,
    label: engineer.name,
    value: engineer.assigned,
    color: ENGINEER_CHART_COLORS[index % ENGINEER_CHART_COLORS.length],
  }))
}

// A stat tile: one big number with a caption. With onClick it is a button
// (the Statistics page opens the tickets behind the number).
export function Tile({ value, caption, onClick }) {
  const body = (
    <>
      <div className="tile-value">{value}</div>
      <div className="tile-caption">{caption}</div>
    </>
  )
  if (!onClick) return <div className="tile">{body}</div>
  return (
    <button type="button" className="tile tile-clickable" onClick={onClick}>
      {body}
    </button>
  )
}
