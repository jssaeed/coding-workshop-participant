import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('../../src/services/api', async () => (await import('../helpers')).mockApiModule())

import * as api from '../../src/services/api'
import InboxPage from '../../src/pages/InboxPage'
import { engineer, resetApi } from '../helpers'

const inboxData = {
  unread: 3,
  items: [
    {
      incident: { id: 12, title: 'Leaking pipe', status: 'in_progress', priority: 2 },
      unreadCount: 2,
      latestMessage: { message: 'Ticket #12: status changed to in progress', createdAt: '2026-09-22T15:42:37.880Z', author: { id: engineer.id, name: engineer.name } },
    },
    {
      incident: { id: 9, title: 'Broken light', status: 'open', priority: 4 },
      unreadCount: 1,
      latestMessage: { message: 'Any update?', createdAt: '2026-09-21T10:00:00.000Z', author: null },
    },
  ],
}

function renderInbox() {
  const onOpen = vi.fn()
  const setUnread = vi.fn()
  render(<InboxPage onOpen={onOpen} setUnread={setUnread} />)
  return { onOpen, setUnread }
}

beforeEach(() => resetApi(api))

describe('InboxPage', () => {
  it('lists tickets with unread activity and updates the bell', async () => {
    api.inbox.list.mockResolvedValue(inboxData)
    const { setUnread } = renderInbox()

    expect(await screen.findByText('Leaking pipe', { exact: false })).toBeInTheDocument()
    expect(screen.getByText('Ticket #12: status changed to in progress')).toBeInTheDocument()
    expect(screen.getByText(engineer.name)).toBeInTheDocument()
    expect(screen.getByText('Deleted user')).toBeInTheDocument()
    expect(screen.getByText('In progress')).toBeInTheDocument()
    expect(setUnread).toHaveBeenCalledWith(3)
  })

  it('opens a ticket when its card is clicked', async () => {
    api.inbox.list.mockResolvedValue(inboxData)
    const { onOpen } = renderInbox()
    fireEvent.click(await screen.findByText('Broken light', { exact: false }))
    expect(onOpen).toHaveBeenCalledWith(9)
  })

  it('says so when there is nothing new', async () => {
    renderInbox()
    expect(await screen.findByText('Nothing new. You are all caught up.')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Mark all read/ })).toBeDisabled()
  })

  it('marks everything read and reloads', async () => {
    api.inbox.list.mockResolvedValueOnce(inboxData).mockResolvedValueOnce({ unread: 0, items: [] })
    const { setUnread } = renderInbox()
    await screen.findByText('Leaking pipe', { exact: false })

    fireEvent.click(screen.getByRole('button', { name: /Mark all read/ }))
    expect(await screen.findByText('Nothing new. You are all caught up.')).toBeInTheDocument()
    expect(api.inbox.markAllRead).toHaveBeenCalledTimes(1)
    await waitFor(() => expect(setUnread).toHaveBeenLastCalledWith(0))
  })

  it('shows a load error', async () => {
    api.inbox.list.mockRejectedValue(new Error('Token has expired'))
    renderInbox()
    expect(await screen.findByRole('alert')).toHaveTextContent('Token has expired')
  })
})
