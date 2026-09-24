import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import HomePage from '../../src/pages/HomePage'
import { admin, dbAdmin, employee, engineer } from '../helpers'

// The welcome page: static text, plus a list of abilities worded for the role.
function abilities() {
  return [...document.querySelectorAll('.abilities li')].map((li) => li.textContent)
}

describe('HomePage', () => {
  it('greets the user and lists what an employee can do', () => {
    render(<HomePage user={employee} onNavigate={vi.fn()} />)
    expect(screen.getByText('Signed in as Ana Lopez')).toBeInTheDocument()
    expect(screen.getByText('Report building issues and track them to resolution')).toBeInTheDocument()
    expect(abilities()).toHaveLength(2)
    expect(screen.getAllByText(/^Step \d$/)).toHaveLength(3)
  })

  it.each([
    [engineer, 3, /tickets assigned to you/],
    [admin, 4, /assign engineers/],
    [dbAdmin, 3, /run the database migration/],
  ])('adds the abilities of the role', (user, count, extra) => {
    render(<HomePage user={user} onNavigate={vi.fn()} />)
    expect(abilities()).toHaveLength(count)
    expect(abilities().some((text) => extra.test(text))).toBe(true)
  })

  it('both buttons open the Tickets page', () => {
    const onNavigate = vi.fn()
    render(<HomePage user={employee} onNavigate={onNavigate} />)
    fireEvent.click(screen.getByRole('button', { name: 'File a ticket' }))
    fireEvent.click(screen.getByRole('button', { name: 'View my tickets' }))
    expect(onNavigate).toHaveBeenCalledTimes(2)
    expect(onNavigate).toHaveBeenCalledWith('tickets')
  })
})
