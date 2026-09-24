import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('../../src/services/api', async () => (await import('../helpers')).mockApiModule())

import * as api from '../../src/services/api'
import LoginPage from '../../src/pages/LoginPage'
import { chooseOption, employee, resetApi } from '../helpers'

const session = { user: employee, token: 'tok', refreshToken: 'ref' }

function renderLogin() {
  const onLogin = vi.fn()
  render(<LoginPage onLogin={onLogin} />)
  return onLogin
}

async function fill(email, password) {
  const user = userEvent.setup()
  await user.type(screen.getByPlaceholderText('you@acme.inc'), email)
  await user.type(screen.getByLabelText('Password'), password)
  return user
}

beforeEach(() => resetApi(api))

describe('signing in', () => {
  it('logs in and hands the session to the app', async () => {
    api.users.login.mockResolvedValue(session)
    const onLogin = renderLogin()
    const user = await fill('Ana@acme.inc', 'hunter22!')
    await user.click(screen.getByRole('button', { name: 'Sign in' }))

    await waitFor(() => expect(onLogin).toHaveBeenCalledWith(employee, 'tok', 'ref'))
    expect(api.users.login).toHaveBeenCalledWith('Ana@acme.inc', 'hunter22!')
    expect(api.users.signup).not.toHaveBeenCalled()
  })

  it('shows the backend message when the password is wrong', async () => {
    api.users.login.mockRejectedValue(new Error('Email or password is incorrect'))
    const onLogin = renderLogin()
    const user = await fill('ana@acme.inc', 'wrong')
    await user.click(screen.getByRole('button', { name: 'Sign in' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('Email or password is incorrect')
    expect(onLogin).not.toHaveBeenCalled()
  })

  it('validates before sending anything', async () => {
    const onLogin = renderLogin()
    fireEvent.click(screen.getByRole('button', { name: 'Sign in' }))
    expect(await screen.findByText('Enter your email')).toBeInTheDocument()
    expect(await screen.findByText('Enter your password')).toBeInTheDocument()
    expect(api.users.login).not.toHaveBeenCalled()
    expect(onLogin).not.toHaveBeenCalled()
  })

  it('does not require a company address to sign in', async () => {
    api.users.login.mockResolvedValue(session)
    renderLogin()
    const user = await fill('admin@admin.com', 'admin123')
    await user.click(screen.getByRole('button', { name: 'Sign in' }))
    await waitFor(() => expect(api.users.login).toHaveBeenCalled())
  })
})

describe('creating an account', () => {
  async function switchToSignup() {
    const user = userEvent.setup()
    await user.click(screen.getByText('Create account'))
    await screen.findByLabelText('Name')
    return user
  }

  it('offers the branches and requires a company email', async () => {
    renderLogin()
    const user = await switchToSignup()
    await waitFor(() => expect(api.users.branches).toHaveBeenCalled())

    await user.type(screen.getByLabelText('Name'), 'Ana')
    await user.type(screen.getByPlaceholderText('you@acme.inc'), 'ana@gmail.com')
    await user.type(screen.getByLabelText('Password'), 'hunter22!')
    await user.click(screen.getByRole('button', { name: 'Create account' }))

    expect(await screen.findByText('Use your company email address (ending in @acme.inc)')).toBeInTheDocument()
    expect(await screen.findByText('Choose where you work')).toBeInTheDocument()
    expect(api.users.signup).not.toHaveBeenCalled()
  })

  it('rejects short passwords only when signing up', async () => {
    renderLogin()
    const user = await switchToSignup()
    await user.type(screen.getByLabelText('Password'), 'short')
    await user.click(screen.getByRole('button', { name: 'Create account' }))
    expect(await screen.findByText('At least 8 characters')).toBeInTheDocument()
  })

  it('signs up, then signs in with the new account', async () => {
    api.users.signup.mockResolvedValue(employee)
    api.users.login.mockResolvedValue(session)
    const onLogin = renderLogin()
    const user = await switchToSignup()

    await user.type(screen.getByLabelText('Name'), 'Ana Lopez')
    await chooseOption(screen.getByRole('combobox'), 'Princeton-Plainsboro')
    await user.type(screen.getByPlaceholderText('you@acme.inc'), 'ana@acme.inc')
    await user.type(screen.getByLabelText('Password'), 'hunter22!')
    await user.click(screen.getByRole('button', { name: 'Create account' }))

    await waitFor(() => expect(onLogin).toHaveBeenCalledWith(employee, 'tok', 'ref'))
    expect(api.users.signup).toHaveBeenCalledWith('ana@acme.inc', 'hunter22!', 'Ana Lopez', 1)
    expect(api.users.login).toHaveBeenCalledWith('ana@acme.inc', 'hunter22!')
  })

  it('shows a duplicate-account error and clears it when switching mode', async () => {
    api.users.signup.mockRejectedValue(new Error('An account with that email already exists'))
    renderLogin()
    const user = await switchToSignup()
    await user.type(screen.getByLabelText('Name'), 'Ana')
    await chooseOption(screen.getByRole('combobox'), 'Miami')
    await user.type(screen.getByPlaceholderText('you@acme.inc'), 'ana@acme.inc')
    await user.type(screen.getByLabelText('Password'), 'hunter22!')
    await user.click(screen.getByRole('button', { name: 'Create account' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('An account with that email already exists')

    await user.click(screen.getByText('Sign in'))
    await waitFor(() => expect(screen.queryByRole('alert')).not.toBeInTheDocument())
  })
})
