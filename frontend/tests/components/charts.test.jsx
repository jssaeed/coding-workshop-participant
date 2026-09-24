import { fireEvent, render, screen, within } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import BarChart from '../../src/components/charts/BarChart'
import Donut from '../../src/components/charts/Donut'
import { Tile, statusItems } from '../../src/components/charts/shared'

const items = [
  { key: 'open', label: 'Open', value: 7, color: '#2a78d6' },
  { key: 'closed', label: 'Closed', value: 3, color: '#4a3aa7' },
  { key: 'blocked', label: 'Blocked', value: 0, color: '#e34948' },
]

describe('shared', () => {
  it('statusItems keeps every status in order with its colour', () => {
    const result = statusItems({ open: 2, assigned: 0, in_progress: 1, blocked: 0, resolved: 0, closed: 4 })
    expect(result.map((i) => i.key)).toEqual(['open', 'assigned', 'in_progress', 'blocked', 'resolved', 'closed'])
    expect(result[2]).toEqual({ key: 'in_progress', label: 'In progress', value: 1, color: '#eda100' })
    expect(statusItems({ open: 1, assigned: 2 }, ['open']).map((i) => i.key)).not.toContain('open')
  })

  it('Tile shows a number and a caption', () => {
    render(<Tile value={42} caption="tickets" />)
    expect(screen.getByText('42')).toHaveClass('tile-value')
    expect(screen.getByText('tickets')).toBeInTheDocument()
  })
})

describe('BarChart', () => {
  it('says when there is nothing to draw', () => {
    render(<BarChart items={[]} />)
    expect(screen.getByText('No tickets in this range.')).toBeInTheDocument()
    render(<BarChart items={[]} emptyText="Nothing here" />)
    expect(screen.getByText('Nothing here')).toBeInTheDocument()
  })

  it('draws a labelled bar per item', () => {
    render(<BarChart items={items} title="Per building" />)
    const svg = screen.getByRole('img', { name: 'Per building' })
    expect(within(svg).getByText('Open')).toBeInTheDocument()
    expect(within(svg).getByText('7')).toBeInTheDocument()
    expect(within(svg).getByText('3')).toBeInTheDocument()
  })

  it('opens an item on click or Enter, unless it is not selectable', () => {
    const onSelect = vi.fn()
    render(<BarChart items={[...items, { key: 'none', label: 'No location', value: 2, selectable: false }]} onSelect={onSelect} />)
    fireEvent.click(screen.getByText('Open'))
    expect(onSelect).toHaveBeenLastCalledWith(items[0])
    fireEvent.keyDown(screen.getByText('Closed').closest('g'), { key: 'Enter' })
    expect(onSelect).toHaveBeenLastCalledWith(items[1])
    fireEvent.keyDown(screen.getByText('Closed').closest('g'), { key: ' ' })
    expect(onSelect).toHaveBeenCalledTimes(3)
    fireEvent.click(screen.getByText('No location'))
    expect(onSelect).toHaveBeenCalledTimes(3)
    expect(screen.getByText('No location').closest('g')).not.toHaveClass('bar-clickable')
  })

  it('shows a tooltip while the pointer is over a bar', () => {
    render(<BarChart items={items} />)
    const row = screen.getByText('Open').closest('g')
    fireEvent.pointerMove(row, { clientX: 40, clientY: 10 })
    expect(screen.getByRole('status')).toHaveTextContent('7Open')
    fireEvent.pointerLeave(row)
    expect(screen.queryByRole('status')).not.toBeInTheDocument()
  })
})

describe('Donut', () => {
  it('shows the total and a legend with percentages', () => {
    render(<Donut items={items} title="By status" />)
    expect(screen.getByRole('img', { name: 'By status: 10 tickets' })).toBeInTheDocument()
    const legend = document.querySelector('.chart-legend')
    expect(within(legend).getByText('Open').closest('tr')).toHaveTextContent('770%')
    expect(within(legend).getByText('Closed').closest('tr')).toHaveTextContent('330%')
    expect(within(legend).getByText('Blocked').closest('tr')).toHaveTextContent('00%')
    expect(document.querySelectorAll('.donut path')).toHaveLength(2) // zero-value items draw nothing
  })

  it('draws a grey ring when there is nothing, and a full ring for one item', () => {
    render(<Donut items={items.map((i) => ({ ...i, value: 0 }))} />)
    expect(screen.getByRole('img', { name: 'Breakdown: 0 tickets' })).toBeInTheDocument()
    expect(document.querySelectorAll('.donut circle')).toHaveLength(1)
    expect(document.querySelector('.legend-pct')).toHaveTextContent('0%')

    render(<Donut items={[items[0]]} centreLabel="people" />)
    expect(screen.getByRole('img', { name: 'Breakdown: 7 people' })).toBeInTheDocument()
    expect(document.querySelectorAll('.donut circle')).toHaveLength(2)
  })

  it('highlights the hovered or focused item', () => {
    render(<Donut items={items} />)
    const legend = document.querySelector('.chart-legend')
    const openRow = within(legend).getByText('Open').closest('tr')
    fireEvent.pointerEnter(openRow)
    expect(within(legend).getByText('Closed').closest('tr')).toHaveClass('legend-dim')
    expect(openRow).not.toHaveClass('legend-dim')
    fireEvent.pointerLeave(openRow)
    expect(within(legend).getByText('Closed').closest('tr')).not.toHaveClass('legend-dim')

    const arc = document.querySelector('.donut svg g')
    fireEvent.focus(arc)
    expect(screen.getByRole('status')).toHaveTextContent('7Open')
    fireEvent.blur(arc)
    expect(screen.queryByRole('status')).not.toBeInTheDocument()
    fireEvent.pointerMove(arc, { clientX: 5, clientY: 5 })
    expect(screen.getByRole('status')).toBeInTheDocument()
    fireEvent.pointerLeave(arc)
  })
})
