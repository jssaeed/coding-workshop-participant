/**
 * Small helpers for showing data on the page.
 */

export const STATUSES = ['open', 'assigned', 'in_progress', 'blocked', 'resolved', 'closed']
export const ROLES = ['employee', 'engineer', 'facility_admin', 'db_admin']
// The roles a facility admin may hand out; only a db admin can hand out db_admin
export const BRANCH_ROLES = ['employee', 'engineer', 'facility_admin']

// Most senior first, for sorting the employee directory by role
export const ROLE_ORDER = { db_admin: 0, facility_admin: 1, engineer: 2, employee: 3 }
export const PRIORITIES = [1, 2, 3, 4, 5]
// Statuses an engineer can only request; a facility admin approves them
export const APPROVAL_STATUSES = ['blocked', 'resolved']

// Chart colours for each status, one hue per status so a status always has
// the same colour wherever it is drawn. Checked for colour-blind safety.
export const STATUS_CHART_COLORS = {
  open: '#2a78d6',
  assigned: '#1baf7a',
  in_progress: '#eda100',
  blocked: '#e34948',
  resolved: '#008300',
  closed: '#4a3aa7',
}

// Ant Design tag colours for each status and priority
export const STATUS_COLORS = {
  open: 'blue',
  assigned: 'cyan',
  in_progress: 'orange',
  blocked: 'red',
  resolved: 'green',
  closed: 'default',
}

export const PRIORITY_COLORS = {
  1: 'red',
  2: 'volcano',
  3: 'gold',
  4: 'blue',
  5: 'default',
}

// "in_progress" -> "In progress", "facility_admin" -> "Facility admin"
export function label(value) {
  if (!value) return ''
  if (value === 'db_admin') return 'DB admin'
  const words = value.replaceAll('_', ' ')
  return words.charAt(0).toUpperCase() + words.slice(1)
}

// "Ana Lopez" -> "A", used for the avatar in the header
export function initial(name) {
  return name ? name.trim().charAt(0).toUpperCase() : '?'
}

// The reporter or author of something. null means the account was deleted
// after they wrote it, so the ticket or message is kept but has no owner.
export function personName(person) {
  return person ? person.name : 'Deleted user'
}

export function formatDate(isoString) {
  if (!isoString) return ''
  return new Date(isoString).toLocaleString()
}

// Floors are numbered 1..n above ground and -1..-m below ground.
// -1 is shown as "B1", -2 as "B2", and so on.
export function floorLabel(floor) {
  return floor < 0 ? `B${-floor}` : String(floor)
}

export function formatLocation(location) {
  if (!location) return '—'
  let text = `${location.building.name}, floor ${floorLabel(location.floor)}`
  // roomLabel is how the building writes the room ("512" or "12")
  if (location.room) text += `, room ${location.roomLabel || location.room}`
  return text
}

// How a building writes room number `room` on `floor`. Buildings that
// "number rooms by floor" show room 1 on floor 5 as "501", or "5001" once
// any floor has 100 or more rooms. Otherwise it is just "1".
export function roomLabel(building, floor, room) {
  if (!building || !building.roomNumbersIncludeFloor) return String(room)
  const maxRooms = Math.max(0, ...building.rooms.map((f) => f.rooms))
  const digits = maxRooms < 100 ? 2 : 3
  return `${floorLabel(floor)}${String(room).padStart(digits, '0')}`
}

// The floor dropdown options for a building, in the order the server sends
// them: top floor down to 1, then B1, B2, ...
export function floorOptions(building) {
  if (!building) return []
  return building.rooms.map((f) => ({ value: f.floor, label: floorLabel(f.floor) }))
}

// How many rooms a floor has, or 0 when the admin did not say
export function roomsOnFloor(building, floor) {
  if (!building) return 0
  const entry = building.rooms.find((f) => f.floor === floor)
  return entry ? entry.rooms : 0
}

// [1, 2, ..., n]
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

export function isDbAdmin(user) {
  return user.role === 'db_admin'
}

// Who gets the Employee directory: facility admins (their branch) and the
// db admin (every branch)
export function canManageUsers(user) {
  return isAdmin(user) || isDbAdmin(user)
}
