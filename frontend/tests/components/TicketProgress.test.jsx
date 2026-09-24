import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import TicketProgress from '../../src/components/TicketProgress'

function states() {
  return screen.getAllByRole('listitem').map((item) => {
    const cls = item.className
    return cls.includes('progress-done') ? 'done' : cls.includes('progress-current') ? 'current' : 'todo'
  })
}

describe('TicketProgress', () => {
  it('lists the four stages in order', () => {
    render(<TicketProgress status="open" />)
    expect(screen.getAllByRole('listitem').map((li) => li.textContent)).toEqual(['1Open', '2Assigned', '3In progress', '4Resolved'])
  })

  it.each([
    ['open', ['current', 'todo', 'todo', 'todo'], 'blue'],
    ['assigned', ['done', 'current', 'todo', 'todo'], 'blue'],
    ['in_progress', ['done', 'done', 'current', 'todo'], 'blue'],
    ['blocked', ['done', 'done', 'current', 'todo'], 'red'],
    ['resolved', ['done', 'done', 'done', 'current'], 'green'],
    ['closed', ['done', 'done', 'done', 'done'], 'grey'],
  ])('%s fills the bar to the right stage', (status, expected, tone) => {
    render(<TicketProgress status={status} />)
    expect(states()).toEqual(expected)
    expect(screen.getByLabelText('Ticket progress')).toHaveClass(`progress-${tone}`)
  })

  it('marks a blocked ticket as stuck at in progress', () => {
    render(<TicketProgress status="blocked" />)
    expect(screen.getByText('Blocked')).toBeInTheDocument()
  })

  it('shows a closed marker only when closed', () => {
    render(<TicketProgress status="closed" />)
    expect(screen.getByText('Closed')).toBeInTheDocument()
    render(<TicketProgress status="resolved" />)
    expect(screen.getAllByText('Closed')).toHaveLength(1)
  })
})
