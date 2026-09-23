import { useEffect, useState } from 'react'
import { users } from '../services/api'
import { ROLES, formatDate, label } from '../services/format'
import Alert from '../components/Alert'

// Admin only: every account, with a role dropdown and a delete button.
export default function UsersPage({ user }) {
  const [list, setList] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')
  const [refreshCount, setRefreshCount] = useState(0)

  useEffect(() => {
    async function load() {
      setLoading(true)
      try {
        setList(await users.list())
      } catch (err) {
        setError(err.message)
      } finally {
        setLoading(false)
      }
    }
    load()
  }, [refreshCount])

  async function changeRole(target, role) {
    setError('')
    setSuccess('')
    try {
      await users.updateRole(target.id, role)
      setSuccess(`${target.name} is now ${label(role)}.`)
      setRefreshCount(refreshCount + 1)
    } catch (err) {
      setError(err.message)
    }
  }

  async function deleteUser(target) {
    if (!window.confirm(`Delete ${target.name} (${target.email})?`)) return
    setError('')
    setSuccess('')
    try {
      await users.remove(target.id)
      setSuccess(`${target.name} deleted.`)
      setRefreshCount(refreshCount + 1)
    } catch (err) {
      setError(err.message)
    }
  }

  return (
    <div>
      <h1>Users</h1>
      <Alert error={error} success={success} />

      {loading && <p>Loading…</p>}
      {!loading && (
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
            {list.map((account) => {
              // You cannot change or delete your own account
              const isMe = account.id === user.id
              return (
                <tr key={account.id}>
                  <td>{account.name}{isMe && ' (you)'}</td>
                  <td>{account.email}</td>
                  <td>
                    <select
                      value={account.role}
                      onChange={(e) => changeRole(account, e.target.value)}
                      disabled={isMe}
                    >
                      {ROLES.map((role) => (
                        <option key={role} value={role}>{label(role)}</option>
                      ))}
                    </select>
                  </td>
                  <td>{formatDate(account.createdAt)}</td>
                  <td>
                    <button type="button" onClick={() => deleteUser(account)} disabled={isMe}>
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
