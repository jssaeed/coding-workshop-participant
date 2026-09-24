import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('../../src/services/api', async () => (await import('../helpers')).mockApiModule())

import * as api from '../../src/services/api'
import TicketsPage from '../../src/pages/TicketsPage'
import { admin, chooseOption, employee, engineer, openedOptions, resetApi, rowContaining, ticket } from '../helpers'

const tickets = [
  ticket({ id: 12 }),
  ticket({ id: 13, title: 'No power', status: 'assigned', priority: 1, assignedTo: { id: engineer.id, name: engineer.name }, location: null,
           pendingApproval: { status: 'blocked', note: '', requestedAt: '2026-09-22T15:00:00Z', requestedBy: null } }),
]

function renderPage(user = employee) {
  const onOpen = vi.fn()
  render(<TicketsPage user={user} onOpen={onOpen} />)
  return onOpen
}

beforeEach(() => resetApi(api))

describe('the list', () => {
  it('loads my tickets by default and shows their details', async () => {
    api.incidents.list.mockResolvedValue(tickets)
    renderPage()
    expect(await screen.findByText('Leaking pipe')).toBeInTheDocument()
    expect(api.incidents.list).toHaveBeenCalledWith({ scope: 'mine', status: '', priority: '' })

    const leak = rowContaining('Leaking pipe')
    expect(within(leak).getByText('Open')).toBeInTheDocument()
    expect(within(leak).getByText('P2')).toBeInTheDocument()
    expect(within(leak).getByText('HQ, floor 3, room 312')).toBeInTheDocument()
    expect(within(leak).getByText('Ana Lopez')).toBeInTheDocument()

    const power = rowContaining('No power')
    expect(within(power).getByText('Bob Stone')).toBeInTheDocument()
    expect(within(power).getByText('→ Blocked?')).toBeInTheDocument()
    expect(within(power).getByText('—')).toBeInTheDocument()
  })

  it('opens a ticket when its row is clicked', async () => {
    api.incidents.list.mockResolvedValue(tickets)
    const onOpen = renderPage()
    fireEvent.click(await screen.findByText('No power'))
    expect(onOpen).toHaveBeenCalledWith(13)
  })

  it('reloads when a filter changes', async () => {
    renderPage()
    await waitFor(() => expect(api.incidents.list).toHaveBeenCalledTimes(1))
    await chooseOption(screen.getAllByRole('combobox')[1], 'In progress')
    await waitFor(() => expect(api.incidents.list).toHaveBeenLastCalledWith({ scope: 'mine', status: 'in_progress', priority: '' }))
    await chooseOption(screen.getAllByRole('combobox')[2], 'P1')
    await waitFor(() => expect(api.incidents.list).toHaveBeenLastCalledWith({ scope: 'mine', status: 'in_progress', priority: '1' }))
    fireEvent.click(screen.getByRole('button', { name: /Refresh/ }))
    await waitFor(() => expect(api.incidents.list).toHaveBeenCalledTimes(4))
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

  it('shows an empty message and a load error', async () => {
    renderPage()
    expect(await screen.findByText('No tickets.')).toBeInTheDocument()
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
    expect(api.stats.mine).toHaveBeenCalledWith(30)
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

  it('files a ticket without a location and opens it', async () => {
    api.incidents.create.mockResolvedValue(ticket({ id: 40 }))
    const onOpen = await openForm()
    await userEvent.type(screen.getByPlaceholderText('Leaking pipe in the kitchen'), 'Cold office')
    fireEvent.click(screen.getByRole('button', { name: 'File ticket' }))

    await waitFor(() => expect(api.incidents.create).toHaveBeenCalledWith({ title: 'Cold office', description: undefined, priority: 3 }))
    expect(onOpen).toHaveBeenCalledWith(40)
  })

  it('offers floors and rooms from the chosen building', async () => {
    api.incidents.create.mockResolvedValue(ticket({ id: 41 }))
    const onOpen = await openForm()
    const dialog = screen.getByRole('dialog')
    await userEvent.type(within(dialog).getByPlaceholderText('Leaking pipe in the kitchen'), 'Leak')

    const [priorityBox, buildingBox, floorBox] = within(dialog).getAllByRole('combobox')
    expect(floorBox).toBeDisabled()
    await chooseOption(priorityBox, 'P1')
    await chooseOption(buildingBox, 'HQ')
    await waitFor(() => expect(floorBox).toBeEnabled()) // the floor list follows the building
    expect(await openedOptions(floorBox)).toEqual(['3', '2', '1', 'B1'])
    await chooseOption(floorBox, '3')
    // floor 3 has 10 rooms, so the room field becomes a list, written with the floor in front
    await waitFor(() => expect(within(dialog).getAllByRole('combobox')).toHaveLength(4))
    const roomBox = within(dialog).getAllByRole('combobox')[3]
    expect(await openedOptions(roomBox)).toEqual(['301', '302', '303', '304', '305', '306', '307', '308', '309', '310'])
    await chooseOption(roomBox, '307')

    fireEvent.click(screen.getByRole('button', { name: 'File ticket' }))
    await waitFor(() => expect(api.incidents.create).toHaveBeenCalledWith({
      title: 'Leak', description: undefined, priority: 1, location: { buildingId: 2, floor: 3, room: 7 },
    }))
    expect(onOpen).toHaveBeenCalledWith(41)
  })

  it('requires a floor once a building is chosen', async () => {
    await openForm()
    const dialog = screen.getByRole('dialog')
    await userEvent.type(within(dialog).getByPlaceholderText('Leaking pipe in the kitchen'), 'Leak')
    await chooseOption(within(dialog).getAllByRole('combobox')[1], 'HQ')
    await waitFor(() => expect(within(dialog).getAllByRole('combobox')[2]).toBeEnabled())
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
