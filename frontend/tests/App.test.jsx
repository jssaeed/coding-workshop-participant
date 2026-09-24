// The app shell: who is signed in, which page shows, and the header polling.

import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('../src/services/api', async () => (await import('./helpers')).mockApiModule())

import * as api from '../src/services/api'
import App from '../src/App'
import { admin, employee, engineer, resetApi } from './helpers'

function signedInAs(user) {
  api.getToken.mockReturnValue('tok')
  api.getStoredUser.mockReturnValue(user)
  api.users.me.mockResolvedValue(user)
}

beforeEach(() => resetApi(api))

describe('App', () => {
  it('shows the login page when nobody is signed in', () => {
    render(<App />)
    expect(screen.getByRole('button', { name: 'Sign in' })).toBeInTheDocument()
    expect(screen.queryByRole('menu')).not.toBeInTheDocument()
    expect(api.inbox.count).not.toHaveBeenCalled()
  })

  it('restores the session from storage and shows the home page', async () => {
    signedInAs(employee)
    api.inbox.count.mockResolvedValue({ unread: 2 })
    render(<App />)
    expect(screen.getByText('Signed in as Ana Lopez')).toBeInTheDocument()
    expect(screen.getByText('File a ticket for any problem in an ACME building')).toBeInTheDocument()
    await waitFor(() => expect(screen.getByLabelText('Inbox').closest('.ant-badge')).toHaveTextContent('2'))
    expect(api.incidents.list).not.toHaveBeenCalled() // only admins poll for approvals
  })

  it('signs in from the login page', async () => {
    api.users.login.mockResolvedValue({ user: employee, token: 'tok', refreshToken: 'ref' })
    render(<App />)
    fireEvent.change(screen.getByPlaceholderText('you@acme.inc'), { target: { value: 'ana@acme.inc' } })
    fireEvent.change(screen.getByLabelText('Password'), { target: { value: 'hunter22!' } })
    fireEvent.click(screen.getByRole('button', { name: 'Sign in' }))

    expect(await screen.findByText('Signed in as Ana Lopez')).toBeInTheDocument()
    expect(api.saveSession).toHaveBeenCalledWith(employee, 'tok', 'ref')
  })

  it('navigates between pages from the header', async () => {
    signedInAs(employee)
    render(<App />)
    fireEvent.click(screen.getByText('Tickets'))
    expect(await screen.findByRole('heading', { name: 'Tickets' })).toBeInTheDocument()
    fireEvent.click(screen.getByLabelText('Inbox'))
    expect(await screen.findByRole('heading', { name: 'Inbox' })).toBeInTheDocument()
    fireEvent.click(screen.getByText('ACME Inc'))
    expect(screen.getByText('Signed in as Ana Lopez')).toBeInTheDocument()
  })

  it('shows the admin pages to an admin and polls for approvals', async () => {
    signedInAs(admin)
    api.incidents.list.mockResolvedValue([{ id: 1 }, { id: 2 }])
    render(<App />)
    expect(await screen.findByText('Approvals (2)')).toBeInTheDocument()
    expect(api.incidents.list).toHaveBeenCalledWith({ scope: 'pending' })
    fireEvent.click(screen.getByText('Employee directory'))
    expect(await screen.findByRole('heading', { name: /Employee directory/ })).toBeInTheDocument()
  })

  it('signs out', async () => {
    signedInAs(employee)
    render(<App />)
    fireEvent.click(screen.getByLabelText('Account'))
    fireEvent.click(await screen.findByText('Sign out'))
    expect(await screen.findByRole('button', { name: 'Sign in' })).toBeInTheDocument()
    expect(api.users.logout).toHaveBeenCalled()
    expect(api.clearSession).toHaveBeenCalled()
  })

  it('picks up a promotion on the next poll without signing out', async () => {
    signedInAs(employee)
    api.users.me.mockResolvedValue({ ...employee, role: 'engineer' })
    render(<App />)
    await waitFor(() => expect(api.saveSession).toHaveBeenCalledWith({ ...employee, role: 'engineer' }, 'tok'))
    fireEvent.click(screen.getByText('Tickets'))
    await screen.findByRole('heading', { name: 'Tickets' })
    expect(engineer.role).toBe('engineer')
  })
})
