import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('../../src/services/api', async () => (await import('../helpers')).mockApiModule())

import * as api from '../../src/services/api'
import BuildingsPage from '../../src/pages/BuildingsPage'
import { admin, building, resetApi, rowContaining } from '../helpers'

const annex = { id: 3, branchId: 1, name: 'Annex', floors: 2, basementFloors: 0, roomNumbersIncludeFloor: false, rooms: [{ floor: 2, rooms: 0 }, { floor: 1, rooms: 0 }] }
const lab = { id: 4, branchId: 1, name: 'Lab', floors: 1, basementFloors: 0, roomNumbersIncludeFloor: false, rooms: [{ floor: 1, rooms: 5 }] }

async function renderPage(list = [building, annex, lab]) {
  api.buildings.list.mockResolvedValue(list)
  render(<BuildingsPage user={admin} />)
  await screen.findByText('Annex')
}

// The add/edit dialog (the per-floor dialog is a second one, so do not use getByRole)
function dialog() {
  return screen.getByPlaceholderText('HQ').closest('[role="dialog"]')
}

function spinbutton(label) {
  return within(dialog()).getByLabelText(label)
}

function confirmDelete() {
  const buttons = document.querySelector('.ant-popconfirm-buttons')
  fireEvent.click(within(buttons).getByText('Delete'))
}

beforeEach(() => resetApi(api))

describe('the list', () => {
  it('summarises floors and rooms', async () => {
    await renderPage()
    expect(screen.getByText('· Princeton-Plainsboro')).toBeInTheDocument()
    expect(rowContaining('HQ')).toHaveTextContent('3 above, 1 below')
    expect(rowContaining('HQ')).toHaveTextContent('varies (0–10) · numbered by floor')
    expect(rowContaining('Annex')).toHaveTextContent('not set')
    expect(within(rowContaining('Annex')).getByText('2')).toBeInTheDocument()
    expect(rowContaining('Lab')).toHaveTextContent('5 on every floor')
  })

  it('shows an empty state and a load error', async () => {
    api.buildings.list.mockResolvedValue([])
    render(<BuildingsPage user={admin} />)
    expect(await screen.findByText('No buildings yet.')).toBeInTheDocument()
    api.buildings.list.mockRejectedValue(new Error('Token has expired'))
    render(<BuildingsPage user={admin} />)
    expect(await screen.findByRole('alert')).toHaveTextContent('Token has expired')
  })
})

describe('adding a building', () => {
  async function openAdd() {
    await renderPage()
    fireEvent.click(screen.getByRole('button', { name: /Add building/ }))
    await screen.findByText('Add a building')
  }

  it('requires a name', async () => {
    await openAdd()
    fireEvent.click(screen.getByRole('button', { name: 'Add' }))
    expect(await screen.findByText('Enter a name')).toBeInTheDocument()
    expect(api.buildings.create).not.toHaveBeenCalled()
  })

  it('sends the same number of rooms for every floor', async () => {
    api.buildings.create.mockResolvedValue({ ...annex, id: 9, name: 'Tower' })
    await openAdd()
    await userEvent.type(within(dialog()).getByPlaceholderText('HQ'), 'Tower')
    fireEvent.change(spinbutton('Floors above ground'), { target: { value: '4' } })
    fireEvent.click(within(dialog()).getByLabelText('Has basement floors'))
    fireEvent.change(await within(dialog()).findByLabelText('Basement floors'), { target: { value: '2' } })
    fireEvent.change(spinbutton('Rooms on each floor'), { target: { value: '8' } })
    fireEvent.click(within(dialog()).getByLabelText('Rooms start with floor number?'))
    fireEvent.click(screen.getByRole('button', { name: 'Add' }))

    await waitFor(() => expect(api.buildings.create).toHaveBeenCalledWith({
      name: 'Tower', floors: 4, basementFloors: 2, roomNumbersIncludeFloor: true, roomsPerFloor: 8,
    }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Tower added.')
    expect(api.buildings.list).toHaveBeenCalledTimes(2)
  })

  it('leaves rooms unspecified when no number is given', async () => {
    api.buildings.create.mockResolvedValue(annex)
    await openAdd()
    await userEvent.type(within(dialog()).getByPlaceholderText('HQ'), 'Shed')
    fireEvent.click(screen.getByRole('button', { name: 'Add' }))
    await waitFor(() => expect(api.buildings.create).toHaveBeenCalledWith({
      name: 'Shed', floors: 1, basementFloors: 0, roomNumbersIncludeFloor: false,
    }))
  })

  it('can set rooms per floor', async () => {
    api.buildings.create.mockResolvedValue(annex)
    await openAdd()
    await userEvent.type(within(dialog()).getByPlaceholderText('HQ'), 'Tower')
    fireEvent.change(spinbutton('Floors above ground'), { target: { value: '2' } })
    fireEvent.change(spinbutton('Rooms on each floor'), { target: { value: '6' } })
    fireEvent.click(screen.getByRole('button', { name: /Set per floor/ }))

    const perFloor = await screen.findByText('Rooms per floor')
    const rows = perFloor.closest('.ant-modal').querySelectorAll('.per-floor-row')
    expect([...rows].map((row) => row.textContent)).toEqual(['Floor 2', 'Floor 1'])
    fireEvent.change(within(rows[0]).getByRole('spinbutton'), { target: { value: '12' } })
    fireEvent.change(within(rows[1]).getByRole('spinbutton'), { target: { value: '6' } })
    fireEvent.click(screen.getByRole('button', { name: 'Done' }))

    expect(spinbutton('Rooms on each floor')).toBeDisabled()
    expect(screen.getByText('Set per floor below')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Add' }))
    await waitFor(() => expect(api.buildings.create).toHaveBeenCalledWith({
      name: 'Tower', floors: 2, basementFloors: 0, roomNumbersIncludeFloor: false,
      rooms: [{ floor: 2, rooms: 12 }, { floor: 1, rooms: 6 }],
    }))
  })

  it('shows the backend error inside the dialog', async () => {
    api.buildings.create.mockRejectedValue(new Error('A building with that name already exists at your branch'))
    await openAdd()
    await userEvent.type(within(dialog()).getByPlaceholderText('HQ'), 'HQ')
    fireEvent.click(screen.getByRole('button', { name: 'Add' }))
    expect(await within(dialog()).findByRole('alert')).toHaveTextContent('A building with that name already exists at your branch')
    expect(screen.getByText('Add a building')).toBeInTheDocument() // still open
  })
})

describe('editing and deleting', () => {
  it('edits a building whose floors differ, keeping its per-floor rooms', async () => {
    api.buildings.update.mockResolvedValue({ ...building, name: 'Head Office' })
    await renderPage()
    fireEvent.click(within(rowContaining('HQ')).getByLabelText('Edit'))
    await screen.findByText('Edit HQ')
    expect(within(dialog()).getByPlaceholderText('HQ')).toHaveValue('HQ')
    expect(spinbutton('Floors above ground')).toHaveValue('3')
    expect(within(dialog()).getByLabelText('Has basement floors')).toBeChecked()
    expect(within(dialog()).getByLabelText('Rooms start with floor number?')).toBeChecked()
    expect(screen.getByText('Set per floor below')).toBeInTheDocument()

    await userEvent.clear(within(dialog()).getByPlaceholderText('HQ'))
    await userEvent.type(within(dialog()).getByPlaceholderText('HQ'), 'Head Office')
    fireEvent.click(screen.getByRole('button', { name: 'Save' }))

    await waitFor(() => expect(api.buildings.update).toHaveBeenCalledWith(2, {
      name: 'Head Office', floors: 3, basementFloors: 1, roomNumbersIncludeFloor: true,
      rooms: [{ floor: 3, rooms: 10 }, { floor: 2, rooms: 0 }, { floor: 1, rooms: 10 }, { floor: -1, rooms: 4 }],
    }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Head Office updated.')
  })

  it('edits a uniform building with one number, and can switch back from per floor', async () => {
    api.buildings.update.mockResolvedValue(lab)
    await renderPage()
    fireEvent.click(within(rowContaining('Lab')).getByLabelText('Edit'))
    await screen.findByText('Edit Lab')
    expect(spinbutton('Rooms on each floor')).toHaveValue('5')
    fireEvent.click(screen.getByRole('button', { name: /Set per floor/ }))
    fireEvent.click(await screen.findByRole('button', { name: 'Done' }))
    fireEvent.click(screen.getByRole('button', { name: 'Use one number' }))
    expect(spinbutton('Rooms on each floor')).toBeEnabled()
    fireEvent.click(screen.getByRole('button', { name: 'Save' }))
    await waitFor(() => expect(api.buildings.update).toHaveBeenCalledWith(4, {
      name: 'Lab', floors: 1, basementFloors: 0, roomNumbersIncludeFloor: false, roomsPerFloor: 5,
    }))
  })

  it('deletes after confirmation', async () => {
    await renderPage()
    fireEvent.click(within(rowContaining('Annex')).getByLabelText('Delete'))
    await screen.findByText('Delete Annex?')
    confirmDelete()
    await waitFor(() => expect(api.buildings.remove).toHaveBeenCalledWith(3))
    expect(await screen.findByRole('alert')).toHaveTextContent('Annex deleted.')
  })

  it('shows why a delete was refused', async () => {
    api.buildings.remove.mockRejectedValue(new Error('Building has tickets located in it and cannot be deleted'))
    await renderPage()
    fireEvent.click(within(rowContaining('HQ')).getByLabelText('Delete'))
    await screen.findByText('Delete HQ?')
    confirmDelete()
    expect(await screen.findByRole('alert')).toHaveTextContent('Building has tickets located in it and cannot be deleted')
  })
})
