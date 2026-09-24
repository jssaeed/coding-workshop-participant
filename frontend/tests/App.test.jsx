// The app shell: who is signed in, which page shows, and the header polling.

import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { MemoryRouter } from 'react-router-dom'

vi.mock('../src/services/api', async () => (await import('./helpers')).mockApiModule())

import * as api from '../src/services/api'
import App from '../src/App'
import { admin, employee, engineer, pageOf, resetApi } from './helpers'

// main.jsx wraps App in a HashRouter; tests use an in-memory one
function renderApp() {
  return render(<MemoryRouter><App /></MemoryRouter>)
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
