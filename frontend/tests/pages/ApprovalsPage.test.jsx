import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('../../src/services/api', async () => (await import('../helpers')).mockApiModule())

import * as api from '../../src/services/api'
import ApprovalsPage from '../../src/pages/ApprovalsPage'
import { engineer, message, resetApi, ticket } from '../helpers'

const pending = ticket({
  id: 12, status: 'in_progress', assignedTo: { id: engineer.id, name: engineer.name },
  pendingApproval: { status: 'resolved', note: 'Pipe replaced', requestedAt: '2026-09-22T15:00:00Z', requestedBy: { id: engineer.id, name: engineer.name } },
})
const blocked = ticket({
  id: 13, title: 'No power', status: 'assigned', description: '', location: null,
  pendingApproval: { status: 'blocked', note: '', requestedAt: '2026-09-22T15:10:00Z', requestedBy: null },
})

function renderPage() {
  const onOpen = vi.fn()
  render(<ApprovalsPage onOpen={onOpen} />)
  return onOpen
}

beforeEach(() => resetApi(api))

describe('ApprovalsPage', () => {
  it('lists every waiting request with its reason and thread', async () => {
    api.incidents.list.mockResolvedValue([pending, blocked])
    api.messages.list.mockImplementation((id) => Promise.resolve(id === 12 ? [message(), message({ id: 32, message: 'Done.' })] : []))
    renderPage()

    expect(await screen.findByText('#12 Leaking pipe')).toBeInTheDocument()
    expect(api.incidents.list).toHaveBeenCalledWith({ scope: 'pending' })
    expect(screen.getByText('Reason: Pipe replaced')).toBeInTheDocument()
    expect(screen.getByText('Thread (2 messages)')).toBeInTheDocument()
    expect(screen.getByText('No reason given.')).toBeInTheDocument()
    expect(screen.getByText('Thread (0 messages)')).toBeInTheDocument()
    expect(screen.getByText('An engineer')).toBeInTheDocument()
    expect(screen.getByText('Resolved?')).toBeInTheDocument()
    expect(screen.getByText('Blocked?')).toBeInTheDocument()
  })

  it('opens the thread and the ticket', async () => {
    api.incidents.list.mockResolvedValue([pending])
    api.messages.list.mockResolvedValue([message()])
    const onOpen = renderPage()
    fireEvent.click(await screen.findByText('Thread (1 message)'))
    expect(await screen.findByText('On my way up.')).toBeInTheDocument()
    fireEvent.click(screen.getByText('#12 Leaking pipe'))
    expect(onOpen).toHaveBeenCalledWith(12)
  })

  it('approves with a note and reloads', async () => {
    api.incidents.list.mockResolvedValueOnce([pending]).mockResolvedValueOnce([])
    api.incidents.decideApproval.mockResolvedValue(ticket({ status: 'resolved' }))
    renderPage()
    await screen.findByText('#12 Leaking pipe')

    await userEvent.type(screen.getByPlaceholderText('Note for the thread (optional)'), 'Thanks')
    fireEvent.click(screen.getByRole('button', { name: /Approve/ }))

    await waitFor(() => expect(api.incidents.decideApproval).toHaveBeenCalledWith(12, 'approve', 'Thanks'))
    expect(await screen.findByRole('alert')).toHaveTextContent('#12: approved.')
    expect(await screen.findByText('Nothing is waiting for approval.')).toBeInTheDocument()
  })

  it('rejects without a note', async () => {
    api.incidents.list.mockResolvedValue([pending])
    api.incidents.decideApproval.mockResolvedValue(ticket())
    renderPage()
    await screen.findByText('#12 Leaking pipe')
    fireEvent.click(screen.getByRole('button', { name: /Reject/ }))
    await waitFor(() => expect(api.incidents.decideApproval).toHaveBeenCalledWith(12, 'reject', undefined))
    expect(await screen.findByRole('alert')).toHaveTextContent('#12: rejected.')
  })

  it('shows errors from the decision and from loading', async () => {
    api.incidents.list.mockResolvedValue([pending])
    api.incidents.decideApproval.mockRejectedValue(new Error('Nothing is waiting for approval on this ticket'))
    renderPage()
    await screen.findByText('#12 Leaking pipe')
    fireEvent.click(screen.getByRole('button', { name: /Approve/ }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Nothing is waiting for approval on this ticket')
  })

  it('has an empty state and a refresh button', async () => {
    renderPage()
    expect(await screen.findByText('Nothing is waiting for approval.')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /Refresh/ }))
    await waitFor(() => expect(api.incidents.list).toHaveBeenCalledTimes(2))
  })
})
