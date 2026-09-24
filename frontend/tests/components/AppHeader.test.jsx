import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import AppHeader from '../../src/components/AppHeader'
import { admin, dbAdmin, employee, engineer } from '../helpers'

function renderHeader(props = {}) {
  const onNavigate = vi.fn()
  const onLogout = vi.fn()
  render(<AppHeader user={employee} page="home" unread={0} onNavigate={onNavigate} onLogout={onLogout} {...props} />)
  return { onNavigate, onLogout }
}

function menuLabels() {
  return screen.getAllByRole('menuitem').map((item) => item.textContent)
}

describe('AppHeader', () => {
  it('shows only the brand when nobody is signed in', () => {
    renderHeader({ user: null })
    expect(screen.getByText('ACME Inc')).toBeInTheDocument()
    expect(screen.queryByRole('menu')).not.toBeInTheDocument()
    expect(screen.queryByLabelText('Inbox')).not.toBeInTheDocument()
  })

  it.each([
    [employee, ['Home', 'Tickets']],
    [engineer, ['Home', 'Tickets']],
    [admin, ['Home', 'Tickets', 'Approvals', 'Statistics', 'Employee directory', 'Buildings']],
    [dbAdmin, ['Home', 'Tickets', 'Employee directory']],
  ])('offers each role its pages', (user, expected) => {
    renderHeader({ user })
    expect(menuLabels()).toEqual(expected)
  })

  it('counts waiting approvals on the tab', () => {
    renderHeader({ user: admin, pendingCount: 3 })
    expect(menuLabels()).toContain('Approvals (3)')
  })

  it('navigates from the menu, the bell and the brand', () => {
    const { onNavigate } = renderHeader({ page: 'home' })
    fireEvent.click(screen.getByText('Tickets'))
    expect(onNavigate).toHaveBeenCalledWith('tickets')
    fireEvent.click(screen.getByLabelText('Inbox'))
    expect(onNavigate).toHaveBeenCalledWith('inbox')
    fireEvent.click(screen.getByText('ACME Inc'))
    expect(onNavigate).toHaveBeenCalledWith('home')
  })

  it('shows the unread count on the bell', () => {
    renderHeader({ unread: 5 })
    expect(screen.getByLabelText('Inbox').closest('.ant-badge')).toHaveTextContent('5')
  })

  it('keeps Tickets selected while a ticket is open', () => {
    renderHeader({ page: 'ticket' })
    expect(screen.getByText('Tickets').closest('li')).toHaveClass('ant-menu-item-selected')
  })

  it('signs out from the account menu', async () => {
    const { onLogout } = renderHeader()
    fireEvent.click(screen.getByLabelText('Account'))
    fireEvent.click(await screen.findByText('Sign out'))
    expect(onLogout).toHaveBeenCalledTimes(1)
    expect(screen.getByText(employee.email)).toBeInTheDocument()
    expect(screen.getByText('Employee · Princeton-Plainsboro')).toBeInTheDocument()
  })
})
