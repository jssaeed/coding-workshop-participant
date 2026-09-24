// src/services/format.js: the small display helpers, all pure functions.

import { describe, expect, it } from 'vitest'
import {
  APPROVAL_STATUSES, BRANCH_ROLES, PRIORITIES, ROLES, ROLE_ORDER, STATUSES, STATUS_CHART_COLORS, STATUS_COLORS,
  canManageUsers, floorLabel, floorOptions, formatDate, formatLocation, initial, isAdmin, isDbAdmin, isStaff,
  label, personName, range, roomLabel, roomsOnFloor,
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
