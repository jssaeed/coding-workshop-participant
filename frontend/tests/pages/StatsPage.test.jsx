import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('../../src/services/api', async () => (await import('../helpers')).mockApiModule())

import * as api from '../../src/services/api'
import StatsPage from '../../src/pages/StatsPage'
import { resetApi } from '../helpers'

const overview = { total: 12, byStatus: { open: 5, assigned: 1, in_progress: 3, blocked: 0, resolved: 2, closed: 1 } }
const byBuilding = { level: 'building', items: [{ id: 2, name: 'HQ', count: 7 }, { id: 3, name: 'Annex', count: 3 }, { id: null, name: 'No location', count: 2 }] }
const byFloor = { level: 'floor', building: { id: 2, name: 'HQ' }, items: [{ floor: 3, count: 4 }, { floor: -1, count: 3 }] }
const byRoom = { level: 'room', building: { id: 2, name: 'HQ' }, floor: -1, items: [{ room: 12, label: 'B112', count: 2 }, { room: null, label: null, count: 1 }] }

function bars() {
  return document.querySelector('.bars svg')
}

beforeEach(() => {
  resetApi(api)
  api.stats.overview.mockResolvedValue(overview)
  api.stats.locations.mockImplementation((days, buildingId, floor) => Promise.resolve(
    buildingId === undefined ? byBuilding : floor === undefined ? byFloor : byRoom,
  ))
})

describe('StatsPage', () => {
  it('shows the totals by status for the last 30 days', async () => {
    render(<StatsPage />)
    expect(await screen.findByText('12', { selector: '.tile-value' })).toBeInTheDocument()
    expect(screen.getByText('tickets opened in the last 30 days')).toBeInTheDocument()
    expect(api.stats.overview).toHaveBeenCalledWith(30)
    const legend = document.querySelector('.chart-legend')
    expect(within(legend).getByText('Open').closest('tr')).toHaveTextContent('542%')
    expect(within(legend).getByText('Blocked').closest('tr')).toHaveTextContent('00%')
  })

  it('drills down from buildings to floors to rooms and back up', async () => {
    render(<StatsPage />)
    expect(await screen.findByText('Tickets per building')).toBeInTheDocument()
    await waitFor(() => expect(within(bars()).getByText('HQ')).toBeInTheDocument())
    expect(api.stats.locations).toHaveBeenCalledWith(30, undefined, undefined)
    expect(within(bars()).getByText('No location')).toBeInTheDocument()

    // "No location" cannot be opened
    fireEvent.click(within(bars()).getByText('No location'))
    expect(api.stats.locations).toHaveBeenCalledTimes(1)

    fireEvent.click(within(bars()).getByText('HQ'))
    expect(await screen.findByText('Tickets per floor in HQ')).toBeInTheDocument()
    expect(api.stats.locations).toHaveBeenLastCalledWith(30, 2, undefined)
    await waitFor(() => expect(within(bars()).getByText('Floor B1')).toBeInTheDocument())
    expect(screen.getByText('Click a floor to see its rooms.')).toBeInTheDocument()

    fireEvent.click(within(bars()).getByText('Floor B1'))
    expect(await screen.findByText('Tickets per room on floor B1, HQ')).toBeInTheDocument()
    expect(api.stats.locations).toHaveBeenLastCalledWith(30, 2, -1)
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
    render(<StatsPage />)
    await screen.findByText('12', { selector: '.tile-value' })
    fireEvent.click(screen.getByText('Last 7 days'))
    await waitFor(() => expect(api.stats.overview).toHaveBeenLastCalledWith(7))
    await waitFor(() => expect(api.stats.locations).toHaveBeenLastCalledWith(7, undefined, undefined))
    expect(await screen.findByText('tickets opened in the last 7 days')).toBeInTheDocument()
  })

  it('shows an empty range and a load error', async () => {
    api.stats.locations.mockResolvedValue({ level: 'building', items: [] })
    api.stats.overview.mockRejectedValue(new Error('Access denied'))
    render(<StatsPage />)
    expect(await screen.findByText('No tickets in this range.')).toBeInTheDocument()
    expect(await screen.findByRole('alert')).toHaveTextContent('Access denied')
  })
})
