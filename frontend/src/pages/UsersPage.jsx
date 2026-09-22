import { useCallback, useEffect, useState } from 'react'
import { users } from '../services/api'
import { ROLES, formatDate, label } from '../services/format'
import Alert from '../components/Alert'

/**
 * Admin-only: every account, with role changes and deletion.
 */
export default function UsersPage({ user, onApiError }) {
  const [list, setList] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')
  const [busyId, setBusyId] = useState(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      setList(await users.list())
    } catch (err) {
      setError(err.message)
      onApiError(err)
    } finally {
      setLoading(false)
    }
  }, [onApiError])

  useEffect(() => {
    load()
  }, [load])

  async function changeRole(target, role) {
    if (role === target.role) return
    setError('')
    setSuccess('')
    setBusyId(target.id)
    try {
      await users.updateRole(target.id, role)
      setSuccess(`${target.name} is now ${label(role)}. They will see the change after signing in again.`)
      await load()
    } catch (err) {
      setError(err.message)
      onApiError(err)
    } finally {
      setBusyId(null)
    }
  }

  async function remove(target) {
    if (!window.confirm(`Delete ${target.name} (${target.email})?`)) return
    setError('')
    setSuccess('')
    setBusyId(target.id)
    try {
      await users.remove(target.id)
      setSuccess(`${target.name} deleted.`)
      await load()
    } catch (err) {
      setError(err.message)
      onApiError(err)
    } finally {
      setBusyId(null)
    }
  }

  return (
    <div>
      <h1>Users</h1>
      <Alert error={error} success={success} />

      {loading ? (
        <p>Loading…</p>
      ) : (
        <table>
          <thead>
            <tr>
              <th>Name</th>
              <th>Email</th>
              <th>Role</th>
              <th>Joined</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {list.map((u) => {
              const self = u.id === user.id
              return (
                <tr key={u.id}>
                  <td>{u.name}{self && ' (you)'}</td>
                  <td>{u.email}</td>
                  <td>
                    <select
                      value={u.role}
                      onChange={(e) => changeRole(u, e.target.value)}
                      disabled={self || busyId === u.id}
                    >
                      {ROLES.map((r) => (
                        <option key={r} value={r}>{label(r)}</option>
                      ))}
                    </select>
                  </td>
                  <td>{formatDate(u.createdAt)}</td>
                  <td>
                    <button
                      type="button"
                      onClick={() => remove(u)}
                      disabled={self || busyId === u.id}
                    >
                      Delete
                    </button>
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      )}
    </div>
  )
}
