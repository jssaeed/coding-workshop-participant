import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { MemoryRouter } from 'react-router-dom'

vi.mock('../../src/services/api', async () => (await import('../helpers')).mockApiModule())

import * as api from '../../src/services/api'
import TicketsPage from '../../src/pages/TicketsPage'
import { DEFAULT_DAYS } from '../../src/components/charts/shared'
import { admin, chooseOption, employee, engineer, openedOptions, pageOf, resetApi, rowContaining, ticket } from '../helpers'

// What the page asks the server for before anyone touches a filter
const DEFAULT_QUERY = { scope: 'mine', status: '', priority: '', category: '', days: DEFAULT_DAYS, buildingId: '', floor: '', q: '', sort: 'priority', order: 'asc', page: 1, limit: 25 }

const tickets = [
  ticket({ id: 12 }),
  ticket({ id: 13, title: 'No power', status: 'assigned', priority: 1, assignedTo: { id: engineer.id, name: engineer.name }, location: null,
           pendingApproval: { status: 'blocked', note: '', requestedAt: '2026-09-22T15:00:00Z', requestedBy: null } }),
]

// url: the address the page is opened at (filters can come from it)
function renderPage(user = employee, url = '/tickets') {
  const onOpen = vi.fn()
  render(<MemoryRouter initialEntries={[url]}><TicketsPage user={user} onOpen={onOpen} /></MemoryRouter>)
  return onOpen
}

beforeEach(() => resetApi(api))

describe('the list', () => {
  it('loads my tickets by default and shows their details', async () => {
    api.incidents.list.mockResolvedValue(pageOf(tickets))
    renderPage()
    expect(await screen.findByText('Leaking pipe')).toBeInTheDocument()
    expect(api.incidents.list).toHaveBeenCalledWith(DEFAULT_QUERY)

    const leak = rowContaining('Leaking pipe')
    expect(within(leak).getByText('Open')).toBeInTheDocument()
    expect(within(leak).getByText('P2')).toBeInTheDocument()
    expect(within(leak).getByText('Plumbing')).toBeInTheDocument()
    expect(within(leak).getByText('HQ, floor 3, room 312')).toBeInTheDocument()
    expect(within(leak).getByText('Ana Lopez')).toBeInTheDocument()

    const power = rowContaining('No power')
    expect(within(power).getByText('Bob Stone')).toBeInTheDocument()
    expect(within(power).getByText('→ Blocked?')).toBeInTheDocument()
    expect(within(power).getByText('—')).toBeInTheDocument()
  })

  it('opens a ticket when its row is clicked', async () => {
    api.incidents.list.mockResolvedValue(pageOf(tickets))
    const onOpen = renderPage()
    fireEvent.click(await screen.findByText('No power'))
    expect(onOpen).toHaveBeenCalledWith(13)
  })

  it('reloads when a filter changes', async () => {
    renderPage()
    await waitFor(() => expect(api.incidents.list).toHaveBeenCalledTimes(1))
    await chooseOption(screen.getAllByRole('combobox')[1], 'In progress')
    await waitFor(() => expect(api.incidents.list).toHaveBeenLastCalledWith({ ...DEFAULT_QUERY, status: 'in_progress' }))
    // a second status adds to the first: tickets in either are shown
    await chooseOption(screen.getAllByRole('combobox')[1], 'Blocked')
    await waitFor(() => expect(api.incidents.list).toHaveBeenLastCalledWith({ ...DEFAULT_QUERY, status: 'in_progress,blocked' }))
    await chooseOption(screen.getAllByRole('combobox')[2], 'P1')
    await waitFor(() => expect(api.incidents.list).toHaveBeenLastCalledWith({ ...DEFAULT_QUERY, status: 'in_progress,blocked', priority: '1' }))
    fireEvent.click(screen.getByRole('button', { name: /Refresh/ }))
    await waitFor(() => expect(api.incidents.list).toHaveBeenCalledTimes(5))
  })

  it('narrows to a building and then one of its floors', async () => {
    renderPage()
    await waitFor(() => expect(api.incidents.list).toHaveBeenCalledTimes(1))
    const [, , , , buildingBox, floorBox] = screen.getAllByRole('combobox') // show, status, priority, category, building, floor
    expect(floorBox).toBeDisabled() // no building chosen yet, so no floors to offer
    expect(await openedOptions(buildingBox)).toEqual(['Any building', 'HQ'])

    await chooseOption(buildingBox, 'HQ')
    await waitFor(() => expect(api.incidents.list).toHaveBeenLastCalledWith({ ...DEFAULT_QUERY, buildingId: 2 }))
    await waitFor(() => expect(floorBox).toBeEnabled())
    expect(await openedOptions(floorBox)).toEqual(['Any floor', '3', '2', '1', 'B1'])
    await chooseOption(floorBox, 'B1')
    await waitFor(() => expect(api.incidents.list).toHaveBeenLastCalledWith({ ...DEFAULT_QUERY, buildingId: 2, floor: -1 }))

    // Back to any building: the floor no longer applies, and one request covers both
    const calls = api.incidents.list.mock.calls.length
    await chooseOption(buildingBox, 'Any building')
    await waitFor(() => expect(api.incidents.list).toHaveBeenLastCalledWith(DEFAULT_QUERY))
    expect(api.incidents.list).toHaveBeenCalledTimes(calls + 1)
    expect(floorBox).toBeDisabled()
  })

  it('goes back to the default order when a column sort is cleared', async () => {
    renderPage()
    await waitFor(() => expect(api.incidents.list).toHaveBeenCalledTimes(1))
    fireEvent.click(screen.getByText('Title')) // ascending
    await waitFor(() => expect(api.incidents.list).toHaveBeenLastCalledWith({ ...DEFAULT_QUERY, sort: 'title', order: 'asc' }))
    fireEvent.click(screen.getByText('Title')) // descending
    await waitFor(() => expect(api.incidents.list).toHaveBeenLastCalledWith({ ...DEFAULT_QUERY, sort: 'title', order: 'desc' }))
    fireEvent.click(screen.getByText('Title')) // cleared: most urgent first again
    await waitFor(() => expect(api.incidents.list).toHaveBeenLastCalledWith(DEFAULT_QUERY))
  })

  it('clears the status filter back to every status', async () => {
    renderPage(employee, '/tickets?status=open,blocked')
    await waitFor(() => expect(api.incidents.list).toHaveBeenLastCalledWith({ ...DEFAULT_QUERY, status: 'open,blocked' }))
    const statusBox = screen.getAllByRole('combobox')[1].closest('.ant-select')
    fireEvent.click(statusBox.querySelector('.ant-select-clear')) // the "x" on the multi-select
    await waitFor(() => expect(api.incidents.list).toHaveBeenLastCalledWith(DEFAULT_QUERY))
  })

  it('sorts by location on the server', async () => {
    api.incidents.list.mockResolvedValue(pageOf(tickets))
    renderPage()
    await screen.findByText('Leaking pipe')
    fireEvent.click(screen.getByText('Location'))
    await waitFor(() => expect(api.incidents.list).toHaveBeenLastCalledWith({ ...DEFAULT_QUERY, sort: 'location', order: 'asc' }))
  })

  it('searches on the server once typing pauses', async () => {
    renderPage()
    await waitFor(() => expect(api.incidents.list).toHaveBeenCalledTimes(1))
    await userEvent.type(screen.getByPlaceholderText('Search tickets'), 'leak kitchen')
    await waitFor(() => expect(api.incidents.list).toHaveBeenLastCalledWith({ ...DEFAULT_QUERY, q: 'leak kitchen' }))
    expect(api.incidents.list).toHaveBeenCalledTimes(2) // one request for the whole phrase, not one per letter
    expect(await screen.findByText('No tickets match your search.')).toBeInTheDocument()
  })

  it('turns pages, sorts on the server, and goes back to page 1 when a filter changes', async () => {
    api.incidents.list.mockResolvedValue(pageOf(tickets, 60))
    renderPage()
    expect(await screen.findByText('1–25 of 60')).toBeInTheDocument()

    fireEvent.click(screen.getByTitle('2'))
    await waitFor(() => expect(api.incidents.list).toHaveBeenLastCalledWith({ ...DEFAULT_QUERY, page: 2 }))

    fireEvent.click(screen.getByText('Title'))
    await waitFor(() => expect(api.incidents.list).toHaveBeenLastCalledWith({ ...DEFAULT_QUERY, page: 2, sort: 'title', order: 'asc' }))
    fireEvent.click(screen.getByText('Title'))
    await waitFor(() => expect(api.incidents.list).toHaveBeenLastCalledWith({ ...DEFAULT_QUERY, page: 2, sort: 'title', order: 'desc' }))

    // A new filter starts from the first page, in one request
    const calls = api.incidents.list.mock.calls.length
    await chooseOption(screen.getAllByRole('combobox')[1], 'Open')
    await waitFor(() => expect(api.incidents.list).toHaveBeenLastCalledWith({ ...DEFAULT_QUERY, status: 'open', sort: 'title', order: 'desc' }))
    expect(api.incidents.list).toHaveBeenCalledTimes(calls + 1)
  })

  it.each([
    [employee, ['My tickets']],
    [engineer, ['My tickets', 'Assigned to me']],
    [admin, ['My tickets', 'Assigned to me', 'Unassigned', 'Awaiting approval', 'All tickets']],
  ])('offers each role its scopes', async (user, expected) => {
    renderPage(user)
    await waitFor(() => expect(api.incidents.list).toHaveBeenCalled())
    expect(await openedOptions(screen.getAllByRole('combobox')[0])).toEqual(expected)
  })

  it.each([
    [employee, 'mine', 'My tickets'],
    [engineer, 'assigned', 'Assigned to me'],
    [admin, 'all', 'All tickets'],
  ])('starts each role on the scope it uses most', async (user, scope, shown) => {
    renderPage(user)
    await waitFor(() => expect(api.incidents.list).toHaveBeenCalledWith({ ...DEFAULT_QUERY, scope }))
    expect(screen.getAllByRole('combobox')[0].closest('.ant-select')).toHaveTextContent(shown)
  })

  it('starts from the filters in the URL, as the Statistics page links to it', async () => {
    renderPage(admin, '/tickets?scope=all&days=90&status=open,blocked&priority=2&category=hvac&buildingId=2&floor=-1&q=leak')
    await waitFor(() => expect(api.incidents.list).toHaveBeenCalledWith({
      ...DEFAULT_QUERY, scope: 'all', days: 90, status: 'open,blocked', priority: '2', category: 'hvac', buildingId: 2, floor: -1, q: 'leak',
    }))
    expect(screen.getByDisplayValue('leak')).toBeInTheDocument()
    const selects = screen.getAllByRole('combobox').map((box) => box.closest('.ant-select').textContent)
    expect(selects.slice(0, 7)).toEqual(['All tickets', 'OpenBlocked', 'P2', 'AC / heating', 'HQ', 'B1', 'Last 90 days'])
  })

  it('ignores a scope in the URL the user may not pick', async () => {
    renderPage(employee, '/tickets?scope=all')
    await waitFor(() => expect(api.incidents.list).toHaveBeenCalledWith(DEFAULT_QUERY))
  })

  it('shows an empty message and a load error', async () => {
    renderPage()
    expect(await screen.findByText(`No tickets in the last ${DEFAULT_DAYS} days.`)).toBeInTheDocument()
    api.incidents.list.mockRejectedValue(new Error('Access denied'))
    fireEvent.click(screen.getByRole('button', { name: /Refresh/ }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Access denied')
  })

  it('shows the personal statistics, with the assigned card for staff only', async () => {
    api.stats.mine.mockResolvedValue({
      reported: { total: 5, byStatus: { open: 2, assigned: 0, in_progress: 1, blocked: 0, resolved: 1, closed: 1 } },
      assigned: { total: 3, byStatus: { open: 0, assigned: 1, in_progress: 2, blocked: 0, resolved: 0, closed: 0 } },
    })
    renderPage(engineer)
    expect(await screen.findByText('My Tickets')).toBeInTheDocument()
    expect(screen.getByText('Assigned Tickets')).toBeInTheDocument()
    expect(api.stats.mine).toHaveBeenCalledWith(DEFAULT_DAYS)
  })
})

describe('filing a ticket', () => {
  async function openForm(user = employee) {
    const onOpen = renderPage(user)
    await waitFor(() => expect(api.buildings.list).toHaveBeenCalled())
    fireEvent.click(screen.getByRole('button', { name: /New ticket/ }))
    await screen.findByRole('dialog')
    return onOpen
  }

  it('requires a title', async () => {
    await openForm()
    fireEvent.click(screen.getByRole('button', { name: 'File ticket' }))
    expect(await screen.findByText('Give the ticket a title')).toBeInTheDocument()
    expect(api.incidents.create).not.toHaveBeenCalled()
  })

  it('can be cancelled without filing anything', async () => {
    await openForm()
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }))
    // antd starts the closing animation; jsdom never finishes one, so this is as closed as a dialog gets here
    await waitFor(() => expect(screen.getByRole('dialog').className).toMatch(/-leave/))
    expect(api.incidents.create).not.toHaveBeenCalled()
  })

  it('files a ticket without a location and opens it', async () => {
    api.incidents.create.mockResolvedValue(ticket({ id: 40 }))
    const onOpen = await openForm()
    await userEvent.type(screen.getByPlaceholderText('Leaking pipe in the kitchen'), 'Cold office')
    fireEvent.click(screen.getByRole('button', { name: 'File ticket' }))

    await waitFor(() => expect(api.incidents.create).toHaveBeenCalledWith({ title: 'Cold office', description: undefined, priority: 3, category: 'other' }))
    expect(onOpen).toHaveBeenCalledWith(40)
  })

  it('offers floors and rooms from the chosen building', async () => {
    api.incidents.create.mockResolvedValue(ticket({ id: 41 }))
    const onOpen = await openForm()
    const dialog = screen.getByRole('dialog')
    await userEvent.type(within(dialog).getByPlaceholderText('Leaking pipe in the kitchen'), 'Leak')

    const [priorityBox, categoryBox, buildingBox, floorBox] = within(dialog).getAllByRole('combobox')
    expect(floorBox).toBeDisabled()
    await chooseOption(priorityBox, 'P1')
    await chooseOption(categoryBox, 'AC / heating')
    await chooseOption(buildingBox, 'HQ')
    await waitFor(() => expect(floorBox).toBeEnabled()) // the floor list follows the building
    expect(await openedOptions(floorBox)).toEqual(['3', '2', '1', 'B1'])
    await chooseOption(floorBox, '3')
    // floor 3 has 10 rooms, so the room field becomes a list, written with the floor in front
    await waitFor(() => expect(within(dialog).getAllByRole('combobox')).toHaveLength(5))
    const roomBox = within(dialog).getAllByRole('combobox')[4]
    expect(await openedOptions(roomBox)).toEqual(['301', '302', '303', '304', '305', '306', '307', '308', '309', '310'])
    await chooseOption(roomBox, '307')

    fireEvent.click(screen.getByRole('button', { name: 'File ticket' }))
    await waitFor(() => expect(api.incidents.create).toHaveBeenCalledWith({
      title: 'Leak', description: undefined, priority: 1, category: 'hvac', location: { buildingId: 2, floor: 3, room: 7 },
    }))
    expect(onOpen).toHaveBeenCalledWith(41)
  })

  it('requires a floor once a building is chosen', async () => {
    await openForm()
    const dialog = screen.getByRole('dialog')
    await userEvent.type(within(dialog).getByPlaceholderText('Leaking pipe in the kitchen'), 'Leak')
    await chooseOption(within(dialog).getAllByRole('combobox')[2], 'HQ')
    await waitFor(() => expect(within(dialog).getAllByRole('combobox')[3]).toBeEnabled())
    fireEvent.click(screen.getByRole('button', { name: 'File ticket' }))
    expect(await screen.findByText('Choose a floor')).toBeInTheDocument()
    expect(api.incidents.create).not.toHaveBeenCalled()
  })

  it('shows the backend error inside the dialog', async () => {
    api.incidents.create.mockRejectedValue(new Error("'priority' must be between 1 and 5"))
    await openForm()
    await userEvent.type(screen.getByPlaceholderText('Leaking pipe in the kitchen'), 'Leak')
    fireEvent.click(screen.getByRole('button', { name: 'File ticket' }))
    expect(await within(screen.getByRole('dialog')).findByRole('alert')).toHaveTextContent("'priority' must be between 1 and 5")
  })

  it('tells the user when no buildings exist yet', async () => {
    api.buildings.list.mockResolvedValue([])
    await openForm()
    expect(screen.getByText('No buildings defined yet. An admin can add them on the Buildings page.')).toBeInTheDocument()
  })
})

describe('the personal statistics on top', () => {
  it('reload for another range', async () => {
    renderPage()
    await waitFor(() => expect(api.stats.mine).toHaveBeenCalledWith(DEFAULT_DAYS))
    fireEvent.click(screen.getByText('Last 7 days'))
    await waitFor(() => expect(api.stats.mine).toHaveBeenLastCalledWith(7))
    expect(await screen.findByText('opened in the last 7 days')).toBeInTheDocument()
  })

  it('show their own load error without hiding the list', async () => {
    api.stats.mine.mockRejectedValue(new Error('Access denied'))
    api.incidents.list.mockResolvedValue(pageOf(tickets))
    renderPage()
    expect(await screen.findByRole('alert')).toHaveTextContent('Access denied')
    expect(await screen.findByText('Leaking pipe')).toBeInTheDocument()
  })
})
