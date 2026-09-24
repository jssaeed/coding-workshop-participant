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
// What kind of problem a ticket is about, in the backend's order (models/incident.py)
export const CATEGORIES = [
  'plumbing', 'electrical', 'hvac', 'structural', 'doors_and_locks', 'elevators',
  'furniture', 'appliances', 'safety', 'cleaning', 'other',
]
export const DEFAULT_CATEGORY = 'other'
// Category names that label() would get wrong
const CATEGORY_NAMES = { hvac: 'AC / heating', doors_and_locks: 'Doors & locks' }

// Chart colours for the engineers ring. Engineers are not a fixed list, so
// each one takes the next hue in this order (the order the backend lists
// them: most tickets first, then by name). Every neighbouring pair in this
// order was checked for colour-blind safety; past eight the hues repeat.
export const ENGINEER_CHART_COLORS = ['#2a78d6', '#eb6834', '#1baf7a', '#eda100', '#e87ba4', '#008300', '#4a3aa7', '#e34948']

// Chart colours for each category, one fixed hue per category so a category
// always has the same colour wherever it is drawn. The ring draws them in
// CATEGORIES order, and every neighbouring pair in that order (including
// "other" back round to "plumbing") was checked for colour-blind safety
// and for plain-sight difference.
export const CATEGORY_CHART_COLORS = {
  plumbing: '#8f6bd9',
  electrical: '#c65a2c',
  hvac: '#4a3aa7',
  structural: '#d4487f',
  doors_and_locks: '#2a78d6',
  elevators: '#e34948',
  furniture: '#3aa9e0',
  appliances: '#eb6834',
  safety: '#5b8def',
  cleaning: '#008300',
  other: '#e87ba4',
}
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

// Chart colours for each priority: warm for urgent, cool for not. Taken from
// the same colour-blind-checked set as the status colours, in an order
// where neighbouring slices (including 5 next to 1 on a ring) stay apart.
export const PRIORITY_CHART_COLORS = {
  1: '#e34948',
  2: '#eda100',
  3: '#1baf7a',
  4: '#2a78d6',
  5: '#4a3aa7',
}

// "in_progress" -> "In progress", "facility_admin" -> "Facility admin"
export function label(value) {
  if (!value) return ''
  if (value === 'db_admin') return 'DB admin'
  const words = value.replaceAll('_', ' ')
  return words.charAt(0).toUpperCase() + words.slice(1)
}

// "plumbing" -> "Plumbing", "hvac" -> "AC / heating"
export function categoryLabel(category) {
  return CATEGORY_NAMES[category] || label(category)
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

// 93600 seconds -> "1d 2h"; under an hour -> "35m"
export function formatDuration(seconds) {
  if (seconds === null || seconds === undefined) return '—'
  const minutes = Math.round(seconds / 60)
  if (minutes < 60) return `${minutes}m`
  const hours = Math.floor(minutes / 60)
  if (hours < 24) return `${hours}h ${minutes % 60}m`
  const days = Math.floor(hours / 24)
  return `${days}d ${hours % 24}h`
}

// Does this text contain the search words? Case-insensitive, any order.
export function matchesSearch(text, search) {
  const words = search.trim().toLowerCase().split(/\s+/).filter(Boolean)
  const haystack = (text || '').toLowerCase()
  return words.every((word) => haystack.includes(word))
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

// Where each role lands after signing in: employees on the tickets they
// reported, engineers on the tickets they work through, facility admins on
// the statistics for their branch. Anyone else (the db admin) goes home.
export function landingPageFor(user) {
  if (user.role === 'employee' || user.role === 'engineer') return '/tickets'
  if (isAdmin(user)) return '/stats'
  return '/'
}

// The Tickets page address for a set of filters, e.g. {scope: 'all',
// status: 'open'} -> "/tickets?scope=all&status=open". The Tickets page reads
// them back from the URL, so a statistic can link to the tickets behind it.
// Empty values are left out.
export function ticketListUrl(filters) {
  const params = new URLSearchParams()
  for (const [name, value] of Object.entries(filters)) {
    if (value !== '' && value !== undefined && value !== null) params.set(name, value)
  }
  const query = params.toString()
  return query ? `/tickets?${query}` : '/tickets'
}

// Which "Show" option the Tickets page starts on: employees see the tickets
// they reported, engineers the ones assigned to them, facility admins all of
// their branch's tickets. The options themselves are listed on TicketsPage.
export function defaultTicketScopeFor(user) {
  if (user.role === 'engineer') return 'assigned'
  if (isAdmin(user)) return 'all'
  return 'mine'
}
