import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('../../src/services/api', async () => (await import('../helpers')).mockApiModule())

import * as api from '../../src/services/api'
import UsersPage from '../../src/pages/UsersPage'
import { admin, chooseOption, dbAdmin, employee, engineer, openedOptions, resetApi, rowContaining } from '../helpers'

const miami = { id: 2, name: 'Miami' }
const accounts = [
  { ...engineer, createdAt: '2026-09-20T10:00:00Z' },
  { ...admin, createdAt: '2026-09-01T10:00:00Z' },
  { ...employee, createdAt: '2026-09-22T10:00:00Z' },
  { ...dbAdmin, createdAt: '2026-08-01T10:00:00Z' },
  { id: 20, name: 'Zed Far', email: 'zed@acme.inc', role: 'employee', branch: miami, createdAt: '2026-09-10T10:00:00Z' },
]

function names() {
  return screen.getAllByRole('row').slice(1).map((row) => within(row).getAllByRole('cell')[0].textContent.replace('you', '').trim())
}

async function renderPage(user = admin) {
  api.users.list.mockResolvedValue(accounts)
  render(<UsersPage user={user} />)
  await screen.findByText(engineer.email)
}

beforeEach(() => resetApi(api))

describe('UsersPage', () => {
  it('lists accounts by name and marks the caller', async () => {
    await renderPage()
    expect(names()).toEqual(['Ana Lopez', 'Bob Stone', 'Dee Admin', 'Root', 'Zed Far'])
    expect(within(rowContaining('Dee Admin')).getByText('you')).toBeInTheDocument()
    expect(screen.getByText('· Princeton-Plainsboro')).toBeInTheDocument()
  })

  it('can sort by role, newest and oldest', async () => {
    await renderPage()
    await chooseOption(screen.getAllByRole('combobox')[1], 'Role')
    expect(names()).toEqual(['Root', 'Dee Admin', 'Bob Stone', 'Ana Lopez', 'Zed Far'])
    await chooseOption(screen.getAllByRole('combobox')[1], 'Newest accounts first')
    expect(names()[0]).toBe('Ana Lopez')
    await chooseOption(screen.getAllByRole('combobox')[1], 'Oldest accounts first')
    expect(names()[0]).toBe('Root')
  })

  it('filters by role', async () => {
    await renderPage()
    await chooseOption(screen.getAllByRole('combobox')[0], 'Engineer')
    expect(names()).toEqual(['Bob Stone'])
    await chooseOption(screen.getAllByRole('combobox')[0], 'DB admin')
    expect(names()).toEqual(['Root'])
  })

  it('a facility admin cannot touch themselves or a db admin', async () => {
    await renderPage()
    const me = rowContaining('Dee Admin')
    expect(within(me).getByRole('combobox')).toBeDisabled()
    expect(within(me).getByRole('button')).toBeDisabled()
    const root = rowContaining('Root')
    expect(within(root).getByRole('combobox')).toBeDisabled()
    expect(within(root).getByRole('button')).toBeDisabled()
    const bob = rowContaining('Bob Stone')
    expect(within(bob).getByRole('combobox')).toBeEnabled()
    expect(await openedOptions(within(bob).getByRole('combobox'))).toEqual(['Employee', 'Engineer', 'Facility admin'])
  })

  it('a db admin sees branches, can filter by them, and can hand out db admin', async () => {
    await renderPage(dbAdmin)
    expect(screen.getByText('· All branches')).toBeInTheDocument()
    expect(screen.getByRole('columnheader', { name: 'Branch' })).toBeInTheDocument()
    expect(within(rowContaining('Dee Admin')).getByRole('combobox')).toBeEnabled()
    expect(await openedOptions(within(rowContaining('Bob Stone')).getByRole('combobox'))).toContain('DB admin')

    await chooseOption(screen.getAllByRole('combobox')[0], 'Miami')
    expect(names()).toEqual(['Zed Far'])
  })

  it('changes a role and confirms it', async () => {
    await renderPage()
    api.users.updateRole.mockResolvedValue({ ...employee, role: 'engineer' })
    await chooseOption(within(rowContaining('Ana Lopez')).getByRole('combobox'), 'Engineer')

    await waitFor(() => expect(api.users.updateRole).toHaveBeenCalledWith(employee.id, 'engineer'))
    expect(await screen.findByRole('alert')).toHaveTextContent('Ana Lopez is now Engineer.')
    expect(api.users.list).toHaveBeenCalledTimes(2) // reloaded
  })

  it('shows the backend error when a role change is refused', async () => {
    await renderPage()
    api.users.updateRole.mockRejectedValue(new Error('That user belongs to another branch'))
    await chooseOption(within(rowContaining('Zed Far')).getByRole('combobox'), 'Engineer')
    expect(await screen.findByRole('alert')).toHaveTextContent('That user belongs to another branch')
  })

  it('deletes after confirmation', async () => {
    await renderPage()
    fireEvent.click(within(rowContaining('Ana Lopez')).getByRole('button'))
    expect(await screen.findByText('Delete Ana Lopez?')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Delete' }))

    await waitFor(() => expect(api.users.remove).toHaveBeenCalledWith(employee.id))
    expect(await screen.findByRole('alert')).toHaveTextContent('Ana Lopez deleted.')
  })

  it('shows a load error', async () => {
    api.users.list.mockRejectedValue(new Error('Access denied'))
    render(<UsersPage user={admin} />)
    expect(await screen.findByRole('alert')).toHaveTextContent('Access denied')
  })
})
