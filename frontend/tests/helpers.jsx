// Shared fixtures and helpers for the component and page tests.
//
// Pages talk to the backend only through src/services/api.js, so every page
// test mocks that one module:
//
//   vi.mock('../../src/services/api', async () => (await import('../helpers')).mockApiModule())
//   import * as api from '../../src/services/api'
//   beforeEach(() => resetApi(api))
//
// resetApi() gives every function a sensible default (empty lists, zero
// counts) so a page renders; a test then overrides what it cares about:
//
//   api.incidents.list.mockResolvedValue([ticket({ id: 12 })])

import { fireEvent, screen, waitFor, within } from '@testing-library/react'
import { vi } from 'vitest'

export const branch = { id: 1, name: 'Princeton-Plainsboro' }

export const employee = { id: 4, name: 'Ana Lopez', email: 'ana@acme.inc', role: 'employee', branch }
export const engineer = { id: 7, name: 'Bob Stone', email: 'bob@acme.inc', role: 'engineer', branch }
export const otherEngineer = { id: 8, name: 'Cy Park', email: 'cy@acme.inc', role: 'engineer', branch }
export const admin = { id: 1, name: 'Dee Admin', email: 'dee@acme.inc', role: 'facility_admin', branch }
export const dbAdmin = { id: 9, name: 'Root', email: 'admin@admin.com', role: 'db_admin', branch }

export const building = {
  id: 2, branchId: 1, name: 'HQ', floors: 3, basementFloors: 1, roomNumbersIncludeFloor: true,
  rooms: [{ floor: 3, rooms: 10 }, { floor: 2, rooms: 0 }, { floor: 1, rooms: 10 }, { floor: -1, rooms: 4 }],
}

export function ticket(overrides = {}) {
  return {
    id: 12,
    title: 'Leaking pipe',
    description: 'Under the sink',
    status: 'open',
    priority: 2,
    location: { id: 1, building: { id: 2, name: 'HQ' }, floor: 3, room: 12, roomLabel: '312' },
    reportedBy: { id: employee.id, name: employee.name, email: employee.email },
    assignedTo: null,
    pendingApproval: null,
    createdAt: '2026-09-22T14:10:02.101Z',
    updatedAt: '2026-09-22T15:42:37.880Z',
    resolvedAt: null,
    ...overrides,
  }
}

export function message(overrides = {}) {
  return {
    id: 31,
    incidentId: 12,
    message: 'On my way up.',
    author: { id: engineer.id, name: engineer.name, email: engineer.email, role: 'engineer' },
    createdAt: '2026-09-22T15:44:09.216Z',
    updatedAt: '2026-09-22T15:44:09.216Z',
    ...overrides,
  }
}

export const zeroStats = {
  total: 0,
  byStatus: { open: 0, assigned: 0, in_progress: 0, blocked: 0, resolved: 0, closed: 0 },
}

// The shape of src/services/api.js, every function a vi.fn()
export function mockApiModule() {
  const fn = () => vi.fn()
  return {
    getToken: fn(),
    getStoredUser: fn(),
    getRefreshToken: fn(),
    saveSession: fn(),
    clearSession: fn(),
    users: { branches: fn(), signup: fn(), login: fn(), me: fn(), logout: fn(), list: fn(), updateRole: fn(), remove: fn() },
    buildings: { list: fn(), create: fn(), update: fn(), remove: fn() },
    incidents: { create: fn(), list: fn(), get: fn(), assign: fn(), updateStatus: fn(), decideApproval: fn(), updatePriority: fn(), updateLocation: fn() },
    stats: { overview: fn(), locations: fn(), mine: fn() },
    messages: { list: fn(), create: fn() },
    inbox: { list: fn(), count: fn(), markRead: fn(), markAllRead: fn() },
  }
}

// Forget previous calls and give every function its default answer
export function resetApi(api) {
  for (const value of Object.values(api)) {
    if (typeof value === 'function') value.mockReset()
    else for (const inner of Object.values(value)) inner.mockReset()
  }
  api.getToken.mockReturnValue(null)
  api.getStoredUser.mockReturnValue(null)
  api.getRefreshToken.mockReturnValue(null)
  api.users.branches.mockResolvedValue([{ id: 2, name: 'Miami' }, branch])
  api.users.list.mockResolvedValue([])
  api.users.me.mockResolvedValue(employee)
  api.users.logout.mockResolvedValue(null)
  api.users.remove.mockResolvedValue(null)
  api.buildings.list.mockResolvedValue([building])
  api.incidents.list.mockResolvedValue([])
  api.stats.mine.mockResolvedValue({ reported: zeroStats, assigned: null })
  api.stats.overview.mockResolvedValue(zeroStats)
  api.stats.locations.mockResolvedValue({ level: 'building', items: [] })
  api.messages.list.mockResolvedValue([])
  api.inbox.list.mockResolvedValue({ unread: 0, items: [] })
  api.inbox.count.mockResolvedValue({ unread: 0 })
  api.inbox.markRead.mockResolvedValue({ incidentId: 12, lastReadAt: '2026-09-22T16:00:00Z', unread: 0 })
  api.inbox.markAllRead.mockResolvedValue({ unread: 0 })
}

// Ant Design's Select is not a native <select>: open it with mousedown on
// the combobox, then click the option's text in the dropdown. Dropdowns
// opened earlier stay in the DOM hidden, so only the visible one counts.
async function openDropdown(combobox) {
  fireEvent.mouseDown(combobox)
  // Only one dropdown is open at a time; ones opened earlier stay in the DOM
  // either hidden or fading out ("-leave"). (In test environments antd gives
  // every Select the same id, so aria-controls cannot tell them apart.)
  return waitFor(() => {
    const open = [...document.querySelectorAll('.ant-select-dropdown')].filter(
      (dropdown) => !dropdown.classList.contains('ant-select-dropdown-hidden')
        && ![...dropdown.classList].some((name) => name.includes('-leave')),
    )
    if (open.length === 0) throw new Error('dropdown not open')
    return open[open.length - 1]
  })
}

// The visible option elements of a Select, once opened
export async function openedOptionElements(combobox) {
  const dropdown = await openDropdown(combobox)
  return [...dropdown.querySelectorAll('.ant-select-item-option')]
}

// The option labels a Select offers
export async function openedOptions(combobox) {
  return (await openedOptionElements(combobox)).map((option) => option.textContent)
}

export async function chooseOption(combobox, optionText) {
  const options = await openedOptionElements(combobox)
  const option = options.find((element) => element.textContent === optionText)
  if (!option) throw new Error(`no option "${optionText}" among: ${options.map((o) => o.textContent).join(', ')}`)
  fireEvent.click(option.querySelector('.ant-select-item-option-content'))
}

// The table row whose text contains `text`
export function rowContaining(text) {
  return screen.getAllByRole('row').find((row) => within(row).queryByText(text, { exact: false }))
}
