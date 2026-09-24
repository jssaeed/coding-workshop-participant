import { fireEvent, render, screen, within } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import BarChart from '../../src/components/charts/BarChart'
import Donut from '../../src/components/charts/Donut'
import { Tile, categoryItems, engineerItems, priorityItems, statusItems } from '../../src/components/charts/shared'

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

  it('priorityItems runs 1 to 5 with the ends named, 0 when a priority is missing', () => {
    const result = priorityItems({ 1: 4, 3: 9 })
    expect(result.map((i) => i.value)).toEqual([4, 0, 9, 0, 0])
    expect(result[0].label).toBe('Priority 1 · most urgent')
    expect(result[4].label).toBe('Priority 5 · least urgent')
  })

  it('categoryItems keeps every category in order with its colour, 0 when missing', () => {
    const result = categoryItems({ plumbing: 6, other: 1 })
    expect(result).toHaveLength(11)
    expect(result[0]).toEqual({ key: 'plumbing', label: 'Plumbing', value: 6, color: '#8f6bd9' })
    expect(result[2].label).toBe('AC / heating')
    expect(result[2].value).toBe(0)
    expect(result[10]).toMatchObject({ key: 'other', value: 1 })
  })

  it('engineerItems makes one slice per engineer, sized by tickets assigned, colours repeating past eight', () => {
    const engineers = Array.from({ length: 9 }, (_, i) => ({ id: i + 1, name: `E${i + 1}`, assigned: 9 - i, resolved: 0, averageSeconds: null }))
    const result = engineerItems(engineers)
    expect(result[0]).toEqual({ key: 1, label: 'E1', value: 9, color: '#2a78d6' })
    expect(result[8].color).toBe(result[0].color) // the ninth takes the first hue again
    expect(engineerItems([])).toEqual([])
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

  it('keeps the readout by the pointer when a click focuses the arc', () => {
    render(<Donut items={items} onSelect={() => {}} />)
    const arc = document.querySelector('.donut svg g')
    fireEvent.pointerMove(arc, { clientX: 40, clientY: 30 })
    const before = screen.getByRole('status').style.left
    fireEvent.focus(arc) // what a mouse click does after the pointer readout is up
    expect(screen.getByRole('status').style.left).toBe(before)
    expect(screen.getByRole('status')).toHaveTextContent('7Open')
  })
})

describe('Donut keyboard use', () => {
  it('Enter or Space on a focused arc or a legend name selects it, other keys do not', () => {
    const onSelect = vi.fn()
    render(<Donut items={items} onSelect={onSelect} />)
    const arc = screen.getByRole('button', { name: 'Open: 7' })
    fireEvent.keyDown(arc, { key: 'Enter' })
    fireEvent.keyDown(arc, { key: ' ' })
    fireEvent.keyDown(arc, { key: 'Tab' })
    expect(onSelect).toHaveBeenCalledTimes(2)
    expect(onSelect).toHaveBeenLastCalledWith(expect.objectContaining({ key: 'open', value: 7 }))
    fireEvent.click(screen.getByRole('button', { name: 'Closed' })) // the legend name
    expect(onSelect).toHaveBeenCalledTimes(3)
  })

  it('shows the readout at the arc when it is focused from the keyboard', () => {
    render(<Donut items={items} />)
    const arc = document.querySelector('.donut svg g')
    fireEvent.focus(arc) // no pointer readout was showing, so it is placed at the arc
    expect(screen.getByRole('status')).toHaveTextContent('7Open')
    expect(screen.getByRole('status').style.left).not.toBe('')
    fireEvent.blur(arc)
    expect(screen.queryByRole('status')).not.toBeInTheDocument()
  })
})
