/**
 * Small helpers for showing data on the page.
 */

export const STATUSES = ['open', 'in_progress', 'blocked', 'resolved', 'closed']
export const ROLES = ['employee', 'engineer', 'facility_admin']

// "in_progress" -> "in progress", "facility_admin" -> "facility admin"
export function label(value) {
  return value ? value.replaceAll('_', ' ') : ''
}

export function formatDate(isoString) {
  if (!isoString) return ''
  return new Date(isoString).toLocaleString()
}

export function formatLocation(location) {
  if (!location) return '—'
  let text = `${location.building.name}, floor ${location.floor}`
  if (location.room) text += `, room ${location.room}`
  return text
}

// [1, 2, ..., n] for the floor dropdown
export function range(n) {
  const numbers = []
  for (let i = 1; i <= n; i++) numbers.push(i)
  return numbers
}

export function isAdmin(user) {
  return user.role === 'facility_admin'
}

export function isStaff(user) {
  return user.role === 'facility_admin' || user.role === 'engineer'
}
