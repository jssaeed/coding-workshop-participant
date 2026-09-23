/**
 * All calls to the backend go through this file.
 *
 * request() adds the login token, sends and receives JSON, and turns error
 * responses into thrown errors with the backend's message, so pages can
 * show it with a plain try/catch.
 */

// In the cloud this is empty: the frontend and /api share the same domain.
const BASE_URL = import.meta.env.VITE_API_URL || ''

// --- the login session (kept in localStorage so a refresh keeps you signed in)

export function getToken() {
  return localStorage.getItem('token')
}

export function getStoredUser() {
  const user = localStorage.getItem('user')
  return user ? JSON.parse(user) : null
}

export function getRefreshToken() {
  return localStorage.getItem('refreshToken')
}

export function saveSession(user, token, refreshToken) {
  localStorage.setItem('token', token)
  localStorage.setItem('user', JSON.stringify(user))
  if (refreshToken) localStorage.setItem('refreshToken', refreshToken)
}

export function clearSession() {
  localStorage.removeItem('token')
  localStorage.removeItem('user')
  localStorage.removeItem('refreshToken')
}

// --- getting a new access token when the old one expires
//
// The access token only lasts 15 minutes. When a request comes back 401
// because it expired, we send the refresh token to /users/refresh, save the
// new pair of tokens, and retry the original request once.

// Shared between concurrent requests, so several 401s at once cause only one
// refresh call instead of one each.
let refreshInProgress = null

async function refreshSession() {
  if (!refreshInProgress) {
    refreshInProgress = (async () => {
      const refreshToken = getRefreshToken()
      if (!refreshToken) throw new Error('Not signed in')

      const response = await fetch(BASE_URL + '/api/users/refresh', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ refreshToken }),
      })
      if (!response.ok) throw new Error('Session expired')

      const data = await response.json()
      saveSession(data.user, data.token, data.refreshToken)
      return data.token
    })().finally(() => {
      refreshInProgress = null
    })
  }
  return refreshInProgress
}

// --- sending requests

async function request(method, path, body, query, isRetry = false) {
  let url = BASE_URL + '/api' + path
  if (query) {
    // Turn {status: "open", priority: ""} into "?status=open" (empty values skipped)
    const params = new URLSearchParams()
    for (const [key, value] of Object.entries(query)) {
      if (value !== undefined && value !== null && value !== '') {
        params.set(key, value)
      }
    }
    const queryString = params.toString()
    if (queryString) url += '?' + queryString
  }

  const headers = { 'Content-Type': 'application/json' }
  const token = getToken()
  if (token) {
    headers.Authorization = 'Bearer ' + token
  }

  const response = await fetch(url, {
    method,
    headers,
    body: body ? JSON.stringify(body) : undefined,
  })

  // 204 means success with no body (used after deleting)
  if (response.status === 204) return null

  const data = await response.json()

  if (!response.ok) {
    if (response.status === 401 && token && !isRetry) {
      // The access token was rejected. Try once to get a new one with the
      // refresh token and repeat the request. If that fails too, the session
      // is really over: sign out and start again.
      try {
        await refreshSession()
        return request(method, path, body, query, true)
      } catch {
        clearSession()
        window.location.reload()
      }
    }
    const error = new Error(data.error || 'Request failed')
    error.status = response.status
    throw error
  }

  return data
}

// --- the endpoints, grouped by service

export const users = {
  signup: (email, password, name) => request('POST', '/users', { email, password, name }),
  login: (email, password) => request('POST', '/users/login', { email, password }),
  me: () => request('GET', '/users/me'),
  logout: () => request('POST', '/users/logout', { refreshToken: getRefreshToken() }),
  list: () => request('GET', '/users'),
  updateRole: (id, role) => request('PUT', `/users/${id}/role`, { role }),
  remove: (id) => request('DELETE', `/users/${id}`),
}

export const buildings = {
  list: () => request('GET', '/buildings'),
  create: (name, floors) => request('POST', '/buildings', { name, floors }),
  update: (id, changes) => request('PUT', `/buildings/${id}`, changes),
  remove: (id) => request('DELETE', `/buildings/${id}`),
}

export const incidents = {
  create: (ticket) => request('POST', '/incidents', ticket),
  list: (filters) => request('GET', '/incidents', null, filters),
  get: (id) => request('GET', `/incidents/${id}`),
  assign: (id, assigneeId) => request('PUT', `/incidents/${id}/assign`, { assigneeId }),
  updateStatus: (id, status) => request('PUT', `/incidents/${id}/status`, { status }),
}

export const messages = {
  list: (incidentId) => request('GET', '/messages', null, { incidentId }),
  create: (incidentId, message) => request('POST', '/messages', { incidentId, message }),
}

export const inbox = {
  list: () => request('GET', '/inbox'),
  count: () => request('GET', '/inbox/count'),
  markRead: (incidentId) => request('PUT', `/inbox/${incidentId}/read`),
  markAllRead: () => request('PUT', '/inbox/read-all'),
}
