/**
 * API client for the backend services.
 *
 * Every call goes through request(), which attaches the stored token, sends
 * JSON, and turns non-2xx responses into ApiError so pages can show the
 * backend's own message ("'priority' must be between 1 and 5").
 */

// Empty in the cloud, where the frontend and /api share a CloudFront origin.
const BASE_URL = (import.meta.env.VITE_API_URL || '').replace(/\/$/, '')

const TOKEN_KEY = 'token'
const USER_KEY = 'user'

export class ApiError extends Error {
  constructor(status, message, details) {
    super(message)
    this.status = status
    this.details = details
  }
}

// --- session ---------------------------------------------------------------
// localStorage can throw in private windows; a failed read just means "not
// signed in".

export function getToken() {
  try {
    return localStorage.getItem(TOKEN_KEY)
  } catch {
    return null
  }
}

export function getStoredUser() {
  try {
    const raw = localStorage.getItem(USER_KEY)
    return raw ? JSON.parse(raw) : null
  } catch {
    return null
  }
}

export function saveSession(user, token) {
  try {
    localStorage.setItem(TOKEN_KEY, token)
    localStorage.setItem(USER_KEY, JSON.stringify(user))
  } catch {
    // Session still works for this page load; it just won't survive a refresh.
  }
}

export function clearSession() {
  try {
    localStorage.removeItem(TOKEN_KEY)
    localStorage.removeItem(USER_KEY)
  } catch {
    // Nothing to clear.
  }
}

// --- transport -------------------------------------------------------------

async function request(method, path, { body, query } = {}) {
  const url = new URL(`${BASE_URL}/api${path}`, window.location.origin)
  for (const [key, value] of Object.entries(query || {})) {
    if (value !== undefined && value !== null && value !== '') {
      url.searchParams.set(key, value)
    }
  }

  const headers = { 'Content-Type': 'application/json' }
  const token = getToken()
  if (token) headers.Authorization = `Bearer ${token}`

  let response
  try {
    response = await fetch(url, {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
    })
  } catch {
    throw new ApiError(0, 'Could not reach the server')
  }

  if (response.status === 204) return null

  let data = null
  try {
    data = await response.json()
  } catch {
    // No JSON body (e.g. a gateway error page).
  }

  if (!response.ok) {
    throw new ApiError(
      response.status,
      data?.error || `Request failed (${response.status})`,
      data?.details,
    )
  }
  return data
}

// --- endpoints -------------------------------------------------------------

export const users = {
  signup: (email, password, name) =>
    request('POST', '/users', { body: { email, password, name } }),
  login: (email, password) =>
    request('POST', '/users/login', { body: { email, password } }),
  me: () => request('GET', '/users/me'),
  list: (role) => request('GET', '/users', { query: { role } }),
  updateRole: (id, role) => request('PUT', `/users/${id}/role`, { body: { role } }),
  remove: (id) => request('DELETE', `/users/${id}`),
}

export const incidents = {
  create: (ticket) => request('POST', '/incidents', { body: ticket }),
  list: ({ scope, status, priority } = {}) =>
    request('GET', '/incidents', { query: { scope, status, priority } }),
  get: (id) => request('GET', `/incidents/${id}`),
  locations: () => request('GET', '/incidents/locations'),
  assign: (id, assigneeId) =>
    request('PUT', `/incidents/${id}/assign`, { body: { assigneeId } }),
  updateStatus: (id, status) =>
    request('PUT', `/incidents/${id}/status`, { body: { status } }),
}

export const messages = {
  list: (incidentId) => request('GET', '/messages', { query: { incidentId } }),
  create: (incidentId, message) =>
    request('POST', '/messages', { body: { incidentId, message } }),
}
