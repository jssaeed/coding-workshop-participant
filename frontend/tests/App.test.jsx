// The app shell: who is signed in, which page shows, and the header polling.

import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { MemoryRouter } from 'react-router-dom'

vi.mock('../src/services/api', async () => (await import('./helpers')).mockApiModule())

import * as api from '../src/services/api'
import App from '../src/App'
import { admin, employee, engineer, pageOf, resetApi, ticket } from './helpers'

// main.jsx wraps App in a HashRouter; tests use an in-memory one
// history: the addresses visited so far, the last one being the current page
function renderApp(history = ['/']) {
  return render(<MemoryRouter initialEntries={history} initialIndex={history.length - 1}><App /></MemoryRouter>)
}

function signedInAs(user) {
  api.getToken.mockReturnValue('tok')
  api.getStoredUser.mockReturnValue(user)
  api.users.me.mockResolvedValue(user)
}

beforeEach(() => resetApi(api))

describe('App', () => {
  it('shows the login page when nobody is signed in', () => {
    renderApp()
    expect(screen.getByRole('button', { name: 'Sign in' })).toBeInTheDocument()
    expect(screen.queryByRole('menu')).not.toBeInTheDocument()
    expect(api.inbox.count).not.toHaveBeenCalled()
  })

  it('restores the session from storage and shows the home page', async () => {
    signedInAs(employee)
    api.inbox.count.mockResolvedValue({ unread: 2 })
    renderApp()
    expect(screen.getByText('Signed in as Ana Lopez')).toBeInTheDocument()
    expect(screen.getByText('File a ticket for any problem in an ACME building')).toBeInTheDocument()
    await waitFor(() => expect(screen.getByLabelText('Inbox').closest('.ant-badge')).toHaveTextContent('2'))
    expect(api.incidents.list).not.toHaveBeenCalled() // only admins poll for approvals
  })

  it('signs in from the login page', async () => {
    api.users.login.mockResolvedValue({ user: employee, token: 'tok', refreshToken: 'ref' })
    renderApp()
    fireEvent.change(screen.getByPlaceholderText('you@acme.inc'), { target: { value: 'ana@acme.inc' } })
    fireEvent.change(screen.getByLabelText('Password'), { target: { value: 'hunter22!' } })
    fireEvent.click(screen.getByRole('button', { name: 'Sign in' }))

    expect(await screen.findByText('Signed in as Ana Lopez')).toBeInTheDocument()
    expect(api.saveSession).toHaveBeenCalledWith(employee, 'tok', 'ref')
  })

  it.each([
    [employee, 'Tickets'],
    [engineer, 'Tickets'],
    [admin, 'Statistics'],
  ])('sends each role to the page they use most after signing in', async (user, heading) => {
    api.users.login.mockResolvedValue({ user, token: 'tok', refreshToken: 'ref' })
    api.users.me.mockResolvedValue(user) // the role poll agrees with the login
    renderApp()
    fireEvent.change(screen.getByPlaceholderText('you@acme.inc'), { target: { value: user.email } })
    fireEvent.change(screen.getByLabelText('Password'), { target: { value: 'hunter22!' } })
    fireEvent.click(screen.getByRole('button', { name: 'Sign in' }))

    expect(await screen.findByRole('heading', { name: heading })).toBeInTheDocument()
  })

  it('navigates between pages from the header', async () => {
    signedInAs(employee)
    renderApp()
    fireEvent.click(screen.getByText('Tickets'))
    expect(await screen.findByRole('heading', { name: 'Tickets' })).toBeInTheDocument()
    fireEvent.click(screen.getByLabelText('Inbox'))
    expect(await screen.findByRole('heading', { name: 'Inbox' })).toBeInTheDocument()
    fireEvent.click(screen.getByText('ACME Inc'))
    expect(screen.getByText('Signed in as Ana Lopez')).toBeInTheDocument()
  })

  it('shows the admin pages to an admin and polls for approvals', async () => {
    signedInAs(admin)
    api.incidents.list.mockResolvedValue(pageOf([{ id: 1 }], 2))
    renderApp()
    expect(await screen.findByText('Approvals (2)')).toBeInTheDocument()
    expect(api.incidents.list).toHaveBeenCalledWith({ scope: 'pending', limit: 1 }) // only the total is needed
    fireEvent.click(screen.getByText('Employee directory'))
    expect(await screen.findByRole('heading', { name: /Employee directory/ })).toBeInTheDocument()
  })

  it('drops the approvals count as soon as a request is decided', async () => {
    signedInAs(admin)
    // The header asks for the pending total; the Approvals page asks for the pending tickets
    let waiting = 2
    const pending = ticket({ pendingApproval: { status: 'resolved', note: '', requestedAt: '2026-09-22T15:00:00Z', requestedBy: null } })
    api.incidents.list.mockImplementation((filters) => Promise.resolve(
      filters.limit === 1 ? pageOf([{ id: 1 }], waiting) : pageOf(waiting ? [pending] : [], waiting),
    ))
    api.incidents.decideApproval.mockImplementation(() => { waiting -= 1; return Promise.resolve(ticket({ status: 'resolved' })) })
    renderApp()
    expect(await screen.findByText('Approvals (2)')).toBeInTheDocument()

    fireEvent.click(screen.getByText('Approvals (2)'))
    fireEvent.click(await screen.findByRole('button', { name: /Approve/ }))
    // no poll has fired: the count was refreshed by the decision itself
    expect(await screen.findByText('Approvals (1)')).toBeInTheDocument()
  })

  it('opens a ticket from its address and goes back to where it came from', async () => {
    signedInAs(employee)
    api.incidents.get.mockResolvedValue(ticket({ id: 12 }))
    renderApp(['/tickets', '/tickets/12'])
    expect(await screen.findByText('#12 Leaking pipe')).toBeInTheDocument()
    expect(api.incidents.get).toHaveBeenCalledWith(12)
    fireEvent.click(screen.getByRole('button', { name: /Back to tickets/ }))
    expect(await screen.findByRole('heading', { name: 'Tickets' })).toBeInTheDocument()
  })

  it('signs out', async () => {
    signedInAs(employee)
    renderApp()
    fireEvent.click(screen.getByLabelText('Account'))
    fireEvent.click(await screen.findByText('Sign out'))
    expect(await screen.findByRole('button', { name: 'Sign in' })).toBeInTheDocument()
    expect(api.users.logout).toHaveBeenCalled()
    expect(api.clearSession).toHaveBeenCalled()
  })

  it('picks up a promotion on the next poll without signing out', async () => {
    signedInAs(employee)
    api.users.me.mockResolvedValue({ ...employee, role: 'engineer' })
    renderApp()
    await waitFor(() => expect(api.saveSession).toHaveBeenCalledWith({ ...employee, role: 'engineer' }, 'tok'))
    fireEvent.click(screen.getByText('Tickets'))
    await screen.findByRole('heading', { name: 'Tickets' })
    expect(engineer.role).toBe('engineer')
  })
})
