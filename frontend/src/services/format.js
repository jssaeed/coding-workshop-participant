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
  let text = `${location.building}, floor ${location.floor}`
  if (location.room) text += `, ${location.room}`
  return text
}

export function isAdmin(user) {
  return user.role === 'facility_admin'
}

export function isStaff(user) {
  return user.role === 'facility_admin' || user.role === 'engineer'
}
