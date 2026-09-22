/**
 * Display helpers shared by the pages.
 */

export const STATUSES = ['open', 'in_progress', 'blocked', 'resolved', 'closed']

export const ROLES = ['employee', 'engineer', 'facility_admin']

/** in_progress -> "in progress", facility_admin -> "facility admin" */
export function label(value) {
  return value ? value.replace(/_/g, ' ') : ''
}

export function formatDate(iso) {
  if (!iso) return ''
  return new Date(iso).toLocaleString()
}

export function formatLocation(location) {
  if (!location) return '—'
  const parts = [location.building, `floor ${location.floor}`]
  if (location.room) parts.push(location.room)
  return parts.join(', ')
}

export function isAdmin(user) {
  return user?.role === 'facility_admin'
}

export function isStaff(user) {
  return user?.role === 'facility_admin' || user?.role === 'engineer'
}
