// src/services/api.js with fetch mocked: URLs, headers, errors, and the
// refresh-and-retry dance when an access token expires.

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import * as api from '../../src/services/api'

function jsonResponse(status, body) {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: () => Promise.resolve(body),
  }
}

let fetchMock

beforeEach(() => {
  fetchMock = vi.fn()
  vi.stubGlobal('fetch', fetchMock)
})

afterEach(() => {
  vi.unstubAllGlobals()
})

function lastCall(index = -1) {
  const calls = fetchMock.mock.calls
  const [url, options] = calls.at(index)
  return { url, options, body: options.body ? JSON.parse(options.body) : undefined }
}

describe('the session', () => {
  it('is kept in localStorage', () => {
    api.saveSession({ id: 1, name: 'Ana' }, 'tok', 'ref')
    expect(api.getToken()).toBe('tok')
    expect(api.getRefreshToken()).toBe('ref')
    expect(api.getStoredUser()).toEqual({ id: 1, name: 'Ana' })
  })

  it('keeps the refresh token when a save does not carry one', () => {
    api.saveSession({ id: 1 }, 'tok', 'ref')
    api.saveSession({ id: 1, role: 'engineer' }, 'tok2')
    expect(api.getRefreshToken()).toBe('ref')
    expect(api.getToken()).toBe('tok2')
  })

  it('is forgotten on clearSession', () => {
    api.saveSession({ id: 1 }, 'tok', 'ref')
    api.clearSession()
    expect(api.getToken()).toBeNull()
    expect(api.getStoredUser()).toBeNull()
    expect(api.getRefreshToken()).toBeNull()
  })
})

describe('request()', () => {
  it('sends JSON and reads JSON', async () => {
    fetchMock.mockResolvedValue(jsonResponse(201, { id: 5 }))
    const result = await api.incidents.create({ title: 'Leak' })
    expect(result).toEqual({ id: 5 })
    const { url, options, body } = lastCall()
    expect(url).toBe('/api/incidents')
    expect(options.method).toBe('POST')
    expect(options.headers['Content-Type']).toBe('application/json')
    expect(body).toEqual({ title: 'Leak' })
  })

  it('adds the bearer token when signed in, and nothing when not', async () => {
    fetchMock.mockResolvedValue(jsonResponse(200, []))
    await api.buildings.list()
    expect(lastCall().options.headers.Authorization).toBeUndefined()

    api.saveSession({ id: 1 }, 'tok', 'ref')
    await api.buildings.list()
    expect(lastCall().options.headers.Authorization).toBe('Bearer tok')
  })

  it('builds the query string and drops empty filters', async () => {
    fetchMock.mockResolvedValue(jsonResponse(200, []))
    await api.incidents.list({ scope: 'mine', status: '', priority: null, days: undefined })
    expect(lastCall().url).toBe('/api/incidents?scope=mine')
    await api.incidents.list({ scope: 'all', status: 'open', priority: '2' })
    expect(lastCall().url).toBe('/api/incidents?scope=all&status=open&priority=2')
    await api.stats.locations(30, 2, 3)
    expect(lastCall().url).toBe('/api/incidents/stats/locations?days=30&buildingId=2&floor=3')
  })

  it('returns null for 204', async () => {
    fetchMock.mockResolvedValue({ ok: true, status: 204, json: () => { throw new Error('no body') } })
    expect(await api.users.remove(9)).toBeNull()
    expect(lastCall().options.method).toBe('DELETE')
    expect(lastCall().url).toBe('/api/users/9')
  })

  it('throws the backend message with the status on errors', async () => {
    fetchMock.mockResolvedValue(jsonResponse(400, { error: "'title' is required" }))
    await expect(api.incidents.create({})).rejects.toMatchObject({ message: "'title' is required", status: 400 })
  })

  it('falls back to a generic message when the error body has none', async () => {
    fetchMock.mockResolvedValue(jsonResponse(500, {}))
    await expect(api.buildings.list()).rejects.toThrow('Request failed')
  })

  it('does not try to refresh a 401 when nobody is signed in', async () => {
    fetchMock.mockResolvedValue(jsonResponse(401, { error: 'Email or password is incorrect' }))
    await expect(api.users.login('a@acme.inc', 'x')).rejects.toThrow('Email or password is incorrect')
    expect(fetchMock).toHaveBeenCalledTimes(1)
  })
})

describe('expired access tokens', () => {
  beforeEach(() => {
    api.saveSession({ id: 1, role: 'employee' }, 'old-token', 'old-refresh')
  })

  it('refreshes once and retries the request with the new token', async () => {
    fetchMock
      .mockResolvedValueOnce(jsonResponse(401, { error: 'Token has expired' }))
      .mockResolvedValueOnce(jsonResponse(200, { user: { id: 1, role: 'engineer' }, token: 'new-token', refreshToken: 'new-refresh' }))
      .mockResolvedValueOnce(jsonResponse(200, { unread: 3 }))

    expect(await api.inbox.count()).toEqual({ unread: 3 })
    expect(fetchMock).toHaveBeenCalledTimes(3)

    const refresh = lastCall(1)
    expect(refresh.url).toBe('/api/users/refresh')
    expect(refresh.body).toEqual({ refreshToken: 'old-refresh' })
    expect(refresh.options.headers.Authorization).toBeUndefined()

    expect(lastCall().options.headers.Authorization).toBe('Bearer new-token')
    expect(api.getToken()).toBe('new-token')
    expect(api.getRefreshToken()).toBe('new-refresh')
    expect(api.getStoredUser()).toEqual({ id: 1, role: 'engineer' })
  })

  it('shares one refresh between requests that fail at the same time', async () => {
    fetchMock.mockImplementation((url, options) => {
      if (url === '/api/users/refresh') {
        return Promise.resolve(jsonResponse(200, { user: { id: 1 }, token: 'new-token', refreshToken: 'new-refresh' }))
      }
      if (options.headers.Authorization === 'Bearer old-token') {
        return Promise.resolve(jsonResponse(401, { error: 'Token has expired' }))
      }
      return Promise.resolve(jsonResponse(200, { ok: url }))
    })

    const results = await Promise.all([api.inbox.count(), api.buildings.list(), api.users.me()])
    expect(results.map((r) => r.ok)).toEqual(['/api/inbox/count', '/api/buildings', '/api/users/me'])
    const refreshCalls = fetchMock.mock.calls.filter(([url]) => url === '/api/users/refresh')
    expect(refreshCalls).toHaveLength(1)
  })

  it('gives up after one retry', async () => {
    fetchMock.mockImplementation((url) => {
      if (url === '/api/users/refresh') {
        return Promise.resolve(jsonResponse(200, { user: { id: 1 }, token: 'new-token', refreshToken: 'new-refresh' }))
      }
      return Promise.resolve(jsonResponse(401, { error: 'Account no longer exists' }))
    })
    await expect(api.users.me()).rejects.toThrow('Account no longer exists')
    expect(fetchMock.mock.calls.filter(([url]) => url === '/api/users/refresh')).toHaveLength(1)
  })

  it('signs out and reloads when the refresh itself fails', async () => {
    const reload = vi.fn()
    vi.stubGlobal('location', { ...window.location, reload })
    fetchMock
      .mockResolvedValueOnce(jsonResponse(401, { error: 'Token has expired' }))
      .mockResolvedValueOnce(jsonResponse(401, { error: 'Refresh token is invalid or expired' }))

    await expect(api.users.me()).rejects.toThrow('Token has expired')
    expect(api.getToken()).toBeNull()
    expect(api.getRefreshToken()).toBeNull()
    expect(reload).toHaveBeenCalledTimes(1)
  })
})

describe('endpoints', () => {
  beforeEach(() => {
    fetchMock.mockResolvedValue(jsonResponse(200, {}))
    api.saveSession({ id: 1 }, 'tok', 'ref')
  })

  it.each([
    [() => api.users.branches(), 'GET', '/users/branches', undefined],
    [() => api.users.signup('a@acme.inc', 'pw', 'Ana', 1), 'POST', '/users', { email: 'a@acme.inc', password: 'pw', name: 'Ana', branchId: 1 }],
    [() => api.users.login('a@acme.inc', 'pw'), 'POST', '/users/login', { email: 'a@acme.inc', password: 'pw' }],
    [() => api.users.logout(), 'POST', '/users/logout', { refreshToken: 'ref' }],
    [() => api.users.me(), 'GET', '/users/me', undefined],
    [() => api.users.list(), 'GET', '/users', undefined],
    [() => api.users.list({ role: 'engineer', q: '', page: 2 }), 'GET', '/users?role=engineer&page=2', undefined],
    [() => api.users.updateRole(7, 'engineer'), 'PUT', '/users/7/role', { role: 'engineer' }],
    [() => api.buildings.create({ name: 'HQ', floors: 2 }), 'POST', '/buildings', { name: 'HQ', floors: 2 }],
    [() => api.buildings.update(3, { name: 'Annex' }), 'PUT', '/buildings/3', { name: 'Annex' }],
    [() => api.incidents.get(12), 'GET', '/incidents/12', undefined],
    [() => api.incidents.assign(12, 7), 'PUT', '/incidents/12/assign', { assigneeId: 7 }],
    [() => api.incidents.assign(12, null), 'PUT', '/incidents/12/assign', { assigneeId: null }],
    [() => api.incidents.updateStatus(12, 'resolved', 'Done'), 'PUT', '/incidents/12/status', { status: 'resolved', note: 'Done' }],
    [() => api.incidents.decideApproval(12, 'approve'), 'PUT', '/incidents/12/approval', { decision: 'approve' }],
    [() => api.incidents.updatePriority(12, 1), 'PUT', '/incidents/12/priority', { priority: 1 }],
    [() => api.incidents.updateLocation(12, null), 'PUT', '/incidents/12/location', { location: null }],
    [() => api.stats.overview(7), 'GET', '/incidents/stats/overview?days=7', undefined],
    [() => api.stats.mine(30), 'GET', '/incidents/stats/mine?days=30', undefined],
    [() => api.messages.list(12), 'GET', '/messages?incidentId=12', undefined],
    [() => api.messages.list(12, { before: 31, limit: 50 }), 'GET', '/messages?incidentId=12&before=31&limit=50', undefined],
    [() => api.messages.create(12, 'Hi'), 'POST', '/messages', { incidentId: 12, message: 'Hi' }],
    [() => api.inbox.list(), 'GET', '/inbox', undefined],
    [() => api.inbox.markRead(12), 'PUT', '/inbox/12/read', undefined],
    [() => api.inbox.markAllRead(), 'PUT', '/inbox/read-all', undefined],
  ])('%s', async (send, method, path, body) => {
    await send()
    const call = lastCall()
    expect(call.options.method).toBe(method)
    expect(call.url).toBe('/api' + path)
    expect(call.body).toEqual(body)
  })
})
