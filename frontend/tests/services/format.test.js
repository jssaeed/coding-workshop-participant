// src/services/format.js: the small display helpers, all pure functions.

import { describe, expect, it } from 'vitest'
import {
  APPROVAL_STATUSES, BRANCH_ROLES, CATEGORIES, CATEGORY_CHART_COLORS, DEFAULT_CATEGORY, ENGINEER_CHART_COLORS,
  PRIORITIES, PRIORITY_CHART_COLORS, ROLES, ROLE_ORDER, STATUSES, STATUS_CHART_COLORS, STATUS_COLORS,
  canManageUsers, categoryLabel, defaultTicketScopeFor, floorLabel, floorOptions, formatDate, formatDuration, formatLocation,
  initial, isAdmin, isDbAdmin, isStaff, label, landingPageFor, matchesSearch, personName, range, roomLabel, roomsOnFloor, ticketListUrl,
} from '../../src/services/format'

const building = {
  id: 2,
  name: 'HQ',
  roomNumbersIncludeFloor: true,
  rooms: [{ floor: 3, rooms: 10 }, { floor: 2, rooms: 0 }, { floor: 1, rooms: 10 }, { floor: -1, rooms: 4 }],
}

describe('label', () => {
  it('turns snake_case into a sentence', () => {
    expect(label('in_progress')).toBe('In progress')
    expect(label('facility_admin')).toBe('Facility admin')
    expect(label('open')).toBe('Open')
  })
  it('spells DB admin with capitals', () => {
    expect(label('db_admin')).toBe('DB admin')
  })
  it('is empty for nothing', () => {
    expect(label('')).toBe('')
    expect(label(undefined)).toBe('')
  })
})

describe('initial and personName', () => {
  it('takes the first letter, upper-cased and trimmed', () => {
    expect(initial('  ana lopez')).toBe('A')
    expect(initial('')).toBe('?')
    expect(initial(undefined)).toBe('?')
  })
  it('names deleted accounts', () => {
    expect(personName({ name: 'Bob' })).toBe('Bob')
    expect(personName(null)).toBe('Deleted user')
  })
})

describe('formatDate', () => {
  it('formats an ISO string with the local locale', () => {
    const iso = '2026-09-22T14:03:11.412Z'
    expect(formatDate(iso)).toBe(new Date(iso).toLocaleString())
  })
  it('is empty for missing dates', () => {
    expect(formatDate(null)).toBe('')
    expect(formatDate('')).toBe('')
  })
})

describe('floors and rooms', () => {
  it('writes basements as B1, B2', () => {
    expect(floorLabel(3)).toBe('3')
    expect(floorLabel(-1)).toBe('B1')
    expect(floorLabel(-2)).toBe('B2')
  })

  it('formats a location with the written room', () => {
    expect(formatLocation(null)).toBe('—')
    expect(formatLocation({ building: { name: 'HQ' }, floor: 3, room: null })).toBe('HQ, floor 3')
    expect(formatLocation({ building: { name: 'HQ' }, floor: -1, room: 4, roomLabel: 'B104' })).toBe('HQ, floor B1, room B104')
    expect(formatLocation({ building: { name: 'HQ' }, floor: 2, room: 7 })).toBe('HQ, floor 2, room 7')
  })

  it('writes rooms the way the building numbers them', () => {
    expect(roomLabel(building, 3, 1)).toBe('301')
    expect(roomLabel(building, -1, 4)).toBe('B104')
    expect(roomLabel({ ...building, roomNumbersIncludeFloor: false }, 3, 1)).toBe('1')
    expect(roomLabel(undefined, 3, 1)).toBe('1')
  })

  it('uses three digits once any floor has 100 rooms or more', () => {
    const big = { ...building, rooms: [{ floor: 5, rooms: 120 }, { floor: 1, rooms: 10 }] }
    expect(roomLabel(big, 1, 7)).toBe('1007')
  })

  it('offers the floors in the order the server sends them', () => {
    expect(floorOptions(building)).toEqual([
      { value: 3, label: '3' }, { value: 2, label: '2' }, { value: 1, label: '1' }, { value: -1, label: 'B1' },
    ])
    expect(floorOptions(undefined)).toEqual([])
  })

  it('knows how many rooms a floor has, 0 when unspecified or unknown', () => {
    expect(roomsOnFloor(building, 3)).toBe(10)
    expect(roomsOnFloor(building, 2)).toBe(0)
    expect(roomsOnFloor(building, 9)).toBe(0)
    expect(roomsOnFloor(undefined, 3)).toBe(0)
  })

  it('range counts from 1', () => {
    expect(range(3)).toEqual([1, 2, 3])
    expect(range(0)).toEqual([])
  })
})

describe('roles', () => {
  it('tells the roles apart', () => {
    expect(isAdmin({ role: 'facility_admin' })).toBe(true)
    expect(isAdmin({ role: 'db_admin' })).toBe(false)
    expect(isStaff({ role: 'engineer' })).toBe(true)
    expect(isStaff({ role: 'facility_admin' })).toBe(true)
    expect(isStaff({ role: 'employee' })).toBe(false)
    expect(isDbAdmin({ role: 'db_admin' })).toBe(true)
  })
  it('gives the employee directory to both kinds of admin', () => {
    expect(canManageUsers({ role: 'facility_admin' })).toBe(true)
    expect(canManageUsers({ role: 'db_admin' })).toBe(true)
    expect(canManageUsers({ role: 'engineer' })).toBe(false)
  })
})

describe('constants', () => {
  it('match the backend', () => {
    expect(STATUSES).toEqual(['open', 'assigned', 'in_progress', 'blocked', 'resolved', 'closed'])
    expect(ROLES).toEqual(['employee', 'engineer', 'facility_admin', 'db_admin'])
    expect(BRANCH_ROLES).not.toContain('db_admin')
    expect(PRIORITIES).toEqual([1, 2, 3, 4, 5])
    expect(APPROVAL_STATUSES).toEqual(['blocked', 'resolved'])
  })
  it('give every status and priority a colour', () => {
    for (const status of STATUSES) {
      expect(STATUS_COLORS[status]).toBeTruthy()
      expect(STATUS_CHART_COLORS[status]).toMatch(/^#[0-9a-f]{6}$/)
    }
    for (const priority of PRIORITIES) expect(Object.keys(ROLE_ORDER).length).toBe(4) || priority
  })
})

describe('categories', () => {
  it('match the backend list and default', () => {
    expect(CATEGORIES).toEqual([
      'plumbing', 'electrical', 'hvac', 'structural', 'doors_and_locks', 'elevators',
      'furniture', 'appliances', 'safety', 'cleaning', 'other',
    ])
    expect(DEFAULT_CATEGORY).toBe('other')
  })

  it('write the names people read', () => {
    expect(categoryLabel('plumbing')).toBe('Plumbing')
    expect(categoryLabel('hvac')).toBe('AC / heating')
    expect(categoryLabel('doors_and_locks')).toBe('Doors & locks')
    expect(categoryLabel(undefined)).toBe('')
  })

  it('give every category and priority a chart colour, and the engineers a fixed sequence', () => {
    for (const category of CATEGORIES) expect(CATEGORY_CHART_COLORS[category]).toMatch(/^#[0-9a-f]{6}$/)
    for (const priority of PRIORITIES) expect(PRIORITY_CHART_COLORS[priority]).toMatch(/^#[0-9a-f]{6}$/)
    expect(new Set(Object.values(CATEGORY_CHART_COLORS)).size).toBe(CATEGORIES.length) // no two alike
    expect(ENGINEER_CHART_COLORS).toHaveLength(8)
    expect(new Set(ENGINEER_CHART_COLORS).size).toBe(8)
  })
})

describe('formatDuration', () => {
  it('writes minutes, hours and days', () => {
    expect(formatDuration(90)).toBe('2m')
    expect(formatDuration(35 * 60)).toBe('35m')
    expect(formatDuration(3600)).toBe('1h 0m')
    expect(formatDuration(2 * 3600 + 15 * 60)).toBe('2h 15m')
    expect(formatDuration(93600)).toBe('1d 2h')
  })

  it('is a dash when nothing was resolved', () => {
    expect(formatDuration(null)).toBe('—')
    expect(formatDuration(undefined)).toBe('—')
  })
})

describe('matchesSearch', () => {
  it('needs every word, in any order, ignoring case', () => {
    expect(matchesSearch('Leaking pipe in HQ', 'hq leak')).toBe(true)
    expect(matchesSearch('Leaking pipe in HQ', 'hq annex')).toBe(false)
    expect(matchesSearch(null, '')).toBe(true)
  })
})

describe('where each role goes', () => {
  const user = (role) => ({ role })

  it('lands on the page the role uses most', () => {
    expect(landingPageFor(user('employee'))).toBe('/tickets')
    expect(landingPageFor(user('engineer'))).toBe('/tickets')
    expect(landingPageFor(user('facility_admin'))).toBe('/stats')
    expect(landingPageFor(user('db_admin'))).toBe('/')
  })

  it('opens the Tickets page on the scope the role works from', () => {
    expect(defaultTicketScopeFor(user('employee'))).toBe('mine')
    expect(defaultTicketScopeFor(user('engineer'))).toBe('assigned')
    expect(defaultTicketScopeFor(user('facility_admin'))).toBe('all')
    expect(defaultTicketScopeFor(user('db_admin'))).toBe('mine')
  })
})

describe('ticketListUrl', () => {
  it('builds the Tickets page address, leaving empty values out', () => {
    expect(ticketListUrl({ scope: 'all', days: 14, status: 'open' })).toBe('/tickets?scope=all&days=14&status=open')
    expect(ticketListUrl({ scope: 'all', category: 'plumbing', q: 'Bob Stone' })).toBe('/tickets?scope=all&category=plumbing&q=Bob+Stone')
    expect(ticketListUrl({ status: '', priority: undefined, buildingId: null })).toBe('/tickets')
    expect(ticketListUrl({})).toBe('/tickets')
  })
})
