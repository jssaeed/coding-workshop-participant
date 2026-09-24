import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom'

vi.mock('../../src/services/api', async () => (await import('../helpers')).mockApiModule())

import * as api from '../../src/services/api'
import StatsPage from '../../src/pages/StatsPage'
import { resetApi } from '../helpers'

const overview = {
  total: 12,
  byStatus: { open: 5, assigned: 1, in_progress: 3, blocked: 0, resolved: 2, closed: 1 },
  byPriority: { 1: 3, 2: 0, 3: 6, 4: 2, 5: 1 },
  byCategory: {
    plumbing: 4, electrical: 1, hvac: 5, structural: 0, doors_and_locks: 0, elevators: 0,
    furniture: 1, appliances: 0, safety: 1, cleaning: 0, other: 0,
  },
  resolution: { averageSeconds: 7200, resolvedCount: 3 },
}
const byBuilding = { level: 'building', items: [{ id: 2, name: 'HQ', count: 7 }, { id: 3, name: 'Annex', count: 3 }, { id: null, name: 'No location', count: 2 }] }
const byFloor = { level: 'floor', building: { id: 2, name: 'HQ' }, items: [{ floor: 3, count: 4 }, { floor: -1, count: 3 }] }
const byRoom = { level: 'room', building: { id: 2, name: 'HQ' }, floor: -1, items: [{ room: 12, label: 'B112', count: 2 }, { room: null, label: null, count: 1 }] }

// The location drill-down chart (the only bar chart on the page)
function bars() {
  return document.querySelector('.location-chart .bars svg')
}

function categoryLegend() {
  return document.querySelector('.category-chart .chart-legend')
}

function engineerLegend() {
  return document.querySelector('.engineer-chart .chart-legend')
}

// A stand-in Tickets page that shows the URL it was opened with
function TicketsProbe() {
  return <div data-testid="tickets-url">{useLocation().search}</div>
}

// Every number links to the Tickets page, so render with a router
function renderPage() {
  render(
    <MemoryRouter initialEntries={['/stats']}>
      <Routes>
        <Route path="/stats" element={<StatsPage />} />
        <Route path="/tickets" element={<TicketsProbe />} />
      </Routes>
    </MemoryRouter>,
  )
}

// The query string the Tickets page was opened with
function openedTicketsWith() {
  return screen.findByTestId('tickets-url').then((probe) => probe.textContent)
}

beforeEach(() => {
  resetApi(api)
  api.stats.overview.mockResolvedValue(overview)
  api.stats.engineers.mockResolvedValue([{ id: 7, name: 'Bob Stone', role: 'engineer', assigned: 4, resolved: 2, averageSeconds: 3600 }])
  api.stats.locations.mockImplementation((days, buildingId, floor) => Promise.resolve(
    buildingId === undefined ? byBuilding : floor === undefined ? byFloor : byRoom,
  ))
})

describe('StatsPage', () => {
  it('shows the totals by status for the default range (14 days)', async () => {
    renderPage()
    expect(await screen.findByText('12', { selector: '.tile-value' })).toBeInTheDocument()
    expect(screen.getByText('tickets opened in the last 14 days')).toBeInTheDocument()
    expect(api.stats.overview).toHaveBeenCalledWith(14)
    const legend = document.querySelector('.chart-legend')
    expect(within(legend).getByText('Open').closest('tr')).toHaveTextContent('542%')
    expect(within(legend).getByText('Blocked').closest('tr')).toHaveTextContent('00%')
  })

  it('shows the priorities beside the statuses, most urgent first', async () => {
    renderPage()
    expect(await screen.findByText('By priority')).toBeInTheDocument()
    const legends = document.querySelectorAll('.chart-legend')
    expect(legends).toHaveLength(4) // status, priority, engineers, category
    const rows = within(legends[1]).getAllByRole('row').map((row) => row.textContent)
    expect(rows[0]).toContain('Priority 1 · most urgent')
    expect(rows[0]).toContain('325%')
    expect(rows[1]).toContain('Priority 200%')
    expect(rows[4]).toContain('Priority 5 · least urgent')
    // the ring has one arc per non-empty priority
    expect(document.querySelectorAll('.donut')[1].querySelectorAll('path')).toHaveLength(4)
  })

  it('shows every category as a ring, always in the same order', async () => {
    renderPage()
    expect(await screen.findByText('By category')).toBeInTheDocument()
    const rows = within(categoryLegend()).getAllByRole('row').map((row) => row.textContent)
    expect(rows).toHaveLength(11)
    expect(rows[0]).toContain('Plumbing')
    expect(rows[0]).toContain('433%') // 4 of 12
    expect(rows[2]).toContain('AC / heating')
    expect(rows[2]).toContain('542%')
    expect(rows[4]).toContain('Doors & locks00%') // a category with no tickets is still listed
    expect(rows[10]).toContain('Other')
    // the ring has one arc per non-empty category
    expect(document.querySelector('.category-chart .donut').querySelectorAll('path')).toHaveLength(5)
  })

  it('drills down from buildings to floors to rooms and back up', async () => {
    renderPage()
    expect(await screen.findByText('Tickets per building')).toBeInTheDocument()
    await waitFor(() => expect(within(bars()).getByText('HQ')).toBeInTheDocument())
    expect(api.stats.locations).toHaveBeenCalledWith(14, undefined, undefined)
    expect(within(bars()).getByText('No location')).toBeInTheDocument()

    // "No location" cannot be opened
    fireEvent.click(within(bars()).getByText('No location'))
    expect(api.stats.locations).toHaveBeenCalledTimes(1)

    fireEvent.click(within(bars()).getByText('HQ'))
    expect(await screen.findByText('Tickets per floor in HQ')).toBeInTheDocument()
    expect(api.stats.locations).toHaveBeenLastCalledWith(14, 2, undefined)
    await waitFor(() => expect(within(bars()).getByText('Floor B1')).toBeInTheDocument())
    expect(screen.getByText('Click a floor to see its rooms.')).toBeInTheDocument()

    fireEvent.click(within(bars()).getByText('Floor B1'))
    expect(await screen.findByText('Tickets per room on floor B1, HQ')).toBeInTheDocument()
    expect(api.stats.locations).toHaveBeenLastCalledWith(14, 2, -1)
    await waitFor(() => expect(within(bars()).getByText('Room B112')).toBeInTheDocument())
    expect(within(bars()).getByText('No room')).toBeInTheDocument()

    // the trail goes back up one level, then to the top
    const trail = document.querySelector('.ant-breadcrumb')
    fireEvent.click(within(trail).getByText('HQ'))
    expect(await screen.findByText('Tickets per floor in HQ')).toBeInTheDocument()
    fireEvent.click(within(trail).getByText('All buildings'))
    expect(await screen.findByText('Tickets per building')).toBeInTheDocument()
  })

  it('reloads everything when the range changes', async () => {
    renderPage()
    await screen.findByText('12', { selector: '.tile-value' })
    fireEvent.click(screen.getByText('Last 7 days'))
    await waitFor(() => expect(api.stats.overview).toHaveBeenLastCalledWith(7))
    await waitFor(() => expect(api.stats.locations).toHaveBeenLastCalledWith(7, undefined, undefined))
    expect(await screen.findByText('tickets opened in the last 7 days')).toBeInTheDocument()
  })

  it('shows a location load error', async () => {
    api.stats.locations.mockRejectedValue(new Error('Building not found'))
    renderPage()
    expect(await screen.findByRole('alert')).toHaveTextContent('Building not found')
    expect(screen.getByText('Tickets per building')).toBeInTheDocument() // the rest of the page still renders
  })

  it('shows an empty range and a load error', async () => {
    api.stats.locations.mockResolvedValue({ level: 'building', items: [] })
    api.stats.overview.mockRejectedValue(new Error('Access denied'))
    renderPage()
    expect(await screen.findByText('No tickets in this range.')).toBeInTheDocument()
    expect(await screen.findByRole('alert')).toHaveTextContent('Access denied')
  })

  // Each statistic opens the Tickets page filtered to what it counts
  it.each([
    ['a status', async () => {
      await screen.findByText('By status')
      fireEvent.click(within(document.querySelector('.chart-legend')).getByRole('button', { name: 'Open' }))
    }, '?scope=all&days=14&status=open'],
    ['a priority', async () => {
      fireEvent.click(await screen.findByRole('button', { name: 'Priority 1 · most urgent' }))
    }, '?scope=all&days=14&priority=1'],
    ['a category', async () => {
      await screen.findByText('By category')
      fireEvent.click(within(categoryLegend()).getByRole('button', { name: 'Plumbing' }))
    }, '?scope=all&days=14&category=plumbing'],
    ['the total, in the chosen range', async () => {
      await screen.findByText('12', { selector: '.tile-value' })
      fireEvent.click(screen.getByText('Last 30 days'))
      fireEvent.click(await screen.findByText('tickets opened in the last 30 days'))
    }, '?scope=all&days=30'],
    ['the resolution time', async () => {
      fireEvent.click(await screen.findByText('average time to resolve (3 resolved)'))
    }, '?scope=all&days=14&status=resolved'],
    ["the selected engineer's average time", async () => {
      fireEvent.click(await screen.findByRole('button', { name: 'Bob Stone' }))
      fireEvent.click(await screen.findByText('average time for Bob Stone to resolve'))
    }, '?scope=all&days=14&status=resolved&q=Bob+Stone'],
    ['the resolved tickets of the selected engineer', async () => {
      fireEvent.click(await screen.findByRole('button', { name: 'Bob Stone' }))
      fireEvent.click(await screen.findByText('tickets resolved by Bob Stone'))
    }, '?scope=all&days=14&status=resolved&q=Bob+Stone'],
  ])('opens the tickets behind %s', async (_what, click, expected) => {
    renderPage()
    await click()
    expect(await openedTicketsWith()).toBe(expected)
  })

  it('shows the tickets assigned per engineer as a ring', async () => {
    api.stats.engineers.mockResolvedValue([
      { id: 7, name: 'Bob Stone', role: 'engineer', assigned: 4, resolved: 2, averageSeconds: 3600 },
      { id: 8, name: 'Cy Park', role: 'engineer', assigned: 1, resolved: 0, averageSeconds: null },
    ])
    renderPage()
    expect(await screen.findByRole('img', { name: 'Assigned per engineer: 5 assigned' })).toBeInTheDocument()
    const rows = within(engineerLegend()).getAllByRole('row').map((row) => row.textContent)
    expect(rows).toEqual(['Bob Stone480%', 'Cy Park120%'])
    expect(document.querySelector('.engineer-chart .donut').querySelectorAll('path')).toHaveLength(2)
  })

  it('shows the selected engineer\'s resolved count and average beside the overall average', async () => {
    renderPage()
    // nothing selected: the branch's average (7200 s) and a hint
    expect(await screen.findByText('2h 0m', { selector: '.tile-value' })).toBeInTheDocument()
    expect(screen.getByText('average time to resolve (3 resolved)')).toBeInTheDocument()
    expect(screen.getByText(/Click an engineer to see/)).toBeInTheDocument()

    fireEvent.click(await screen.findByRole('button', { name: 'Bob Stone' }))
    expect(await screen.findByText('tickets resolved by Bob Stone')).toBeInTheDocument()
    expect(screen.getByText('2', { selector: '.tile-value' })).toBeInTheDocument()
    expect(screen.getByText('average time for Bob Stone to resolve')).toBeInTheDocument()
    expect(screen.getByText('1h 0m', { selector: '.tile-value' })).toBeInTheDocument()
    // the overall figure stays
    expect(screen.getByText('average time to resolve (3 resolved)')).toBeInTheDocument()
    expect(screen.getByText('2h 0m', { selector: '.tile-value' })).toBeInTheDocument()

    // "Clear selection" clears it, and so does clicking the engineer again
    fireEvent.click(screen.getByRole('button', { name: 'Clear selection' }))
    expect(await screen.findByText(/Click an engineer to see/)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Bob Stone' }))
    await screen.findByText('tickets resolved by Bob Stone')
    fireEvent.click(screen.getByRole('button', { name: 'Bob Stone' }))
    expect(await screen.findByText(/Click an engineer to see/)).toBeInTheDocument()
  })

  it('filters the tickets by the building and floor being looked at', async () => {
    renderPage()
    const button = await screen.findByRole('button', { name: /Filter by selection/ })
    expect(button).toBeDisabled() // nothing chosen yet

    await waitFor(() => expect(within(bars()).getByText('HQ')).toBeInTheDocument())
    fireEvent.click(within(bars()).getByText('HQ'))
    await screen.findByText('Tickets per floor in HQ')
    expect(button).toBeEnabled()
    await waitFor(() => expect(within(bars()).getByText('Floor B1')).toBeInTheDocument())
    fireEvent.click(within(bars()).getByText('Floor B1'))
    await screen.findByText('Tickets per room on floor B1, HQ')

    fireEvent.click(button)
    expect(await openedTicketsWith()).toBe('?scope=all&days=14&buildingId=2&floor=-1')
  })
})
