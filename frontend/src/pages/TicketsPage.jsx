import { useEffect, useState } from 'react'
import { incidents } from '../services/api'
import { STATUSES, formatDate, formatLocation, isAdmin, isStaff, label } from '../services/format'
import Alert from '../components/Alert'

// The ticket list, with filters and a form to file a new ticket.
export default function TicketsPage({ user, onOpen }) {
  // Filters
  const [scope, setScope] = useState('mine')
  const [status, setStatus] = useState('')
  const [priority, setPriority] = useState('')

  // The list
  const [tickets, setTickets] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  // Bumping this number makes the effect below run again (the Refresh button)
  const [refreshCount, setRefreshCount] = useState(0)

  // The new-ticket form
  const [showForm, setShowForm] = useState(false)
  const [title, setTitle] = useState('')
  const [description, setDescription] = useState('')
  const [newPriority, setNewPriority] = useState(3)
  const [building, setBuilding] = useState('')
  const [floor, setFloor] = useState('')
  const [room, setRoom] = useState('')
  const [formError, setFormError] = useState('')
  const [saving, setSaving] = useState(false)

  // Load the list whenever a filter changes or Refresh is clicked.
  useEffect(() => {
    async function load() {
      setLoading(true)
      setError('')
      try {
        setTickets(await incidents.list({ scope, status, priority }))
      } catch (err) {
        setError(err.message)
      } finally {
        setLoading(false)
      }
    }
    load()
  }, [scope, status, priority, refreshCount])

  async function handleCreate(event) {
    event.preventDefault()
    setFormError('')
    setSaving(true)
    try {
      const ticket = { title, description, priority: Number(newPriority) }
      if (building.trim()) {
        ticket.location = { building, floor, room }
      }
      const created = await incidents.create(ticket)
      onOpen(created.id)
    } catch (err) {
      setFormError(err.message)
    } finally {
      setSaving(false)
    }
  }

  // Which "Show" options this user gets
  const scopeOptions = [['mine', 'My tickets']]
  if (isStaff(user)) scopeOptions.push(['assigned', 'Assigned to me'])
  if (isAdmin(user)) scopeOptions.push(['unassigned', 'Unassigned'], ['all', 'All tickets'])

  return (
    <div>
      <div className="row space-between">
        <h1>Tickets</h1>
        <button type="button" onClick={() => setShowForm(!showForm)}>
          {showForm ? 'Cancel' : 'New ticket'}
        </button>
      </div>

      {showForm && (
        <form onSubmit={handleCreate} className="panel">
          <h2>New ticket</h2>
          <label>
            Title
            <input value={title} onChange={(e) => setTitle(e.target.value)} required />
          </label>
          <label>
            Description
            <textarea value={description} onChange={(e) => setDescription(e.target.value)} rows={3} />
          </label>
          <label>
            Priority (1 = most urgent)
            <select value={newPriority} onChange={(e) => setNewPriority(e.target.value)}>
              <option value="1">1</option>
              <option value="2">2</option>
              <option value="3">3</option>
              <option value="4">4</option>
              <option value="5">5</option>
            </select>
          </label>
          <div className="row">
            <label>
              Building
              <input value={building} onChange={(e) => setBuilding(e.target.value)} />
            </label>
            <label>
              Floor
              <input value={floor} onChange={(e) => setFloor(e.target.value)} required={building !== ''} />
            </label>
            <label>
              Room (optional)
              <input value={room} onChange={(e) => setRoom(e.target.value)} />
            </label>
          </div>
          <Alert error={formError} />
          <button type="submit" disabled={saving}>File ticket</button>
        </form>
      )}

      <div className="row filters">
        <label>
          Show
          <select value={scope} onChange={(e) => setScope(e.target.value)}>
            {scopeOptions.map(([value, text]) => (
              <option key={value} value={value}>{text}</option>
            ))}
          </select>
        </label>
        <label>
          Status
          <select value={status} onChange={(e) => setStatus(e.target.value)}>
            <option value="">Any</option>
            {STATUSES.map((s) => (
              <option key={s} value={s}>{label(s)}</option>
            ))}
          </select>
        </label>
        <label>
          Priority
          <select value={priority} onChange={(e) => setPriority(e.target.value)}>
            <option value="">Any</option>
            <option value="1">1</option>
            <option value="2">2</option>
            <option value="3">3</option>
            <option value="4">4</option>
            <option value="5">5</option>
          </select>
        </label>
        <button type="button" onClick={() => setRefreshCount(refreshCount + 1)}>
          Refresh
        </button>
      </div>

      <Alert error={error} />

      {loading && <p>Loading…</p>}
      {!loading && tickets.length === 0 && <p>No tickets.</p>}
      {!loading && tickets.length > 0 && (
        <table>
          <thead>
            <tr>
              <th>#</th>
              <th>Title</th>
              <th>Status</th>
              <th>Priority</th>
              <th>Location</th>
              <th>Reported by</th>
              <th>Assigned to</th>
              <th>Created</th>
            </tr>
          </thead>
          <tbody>
            {tickets.map((ticket) => (
              <tr key={ticket.id} onClick={() => onOpen(ticket.id)} className="clickable">
                <td>{ticket.id}</td>
                <td>{ticket.title}</td>
                <td>
                  <span className={`badge status-${ticket.status}`}>{label(ticket.status)}</span>
                </td>
                <td>{ticket.priority}</td>
                <td>{formatLocation(ticket.location)}</td>
                <td>{ticket.reportedBy.name}</td>
                <td>{ticket.assignedTo ? ticket.assignedTo.name : '—'}</td>
                <td>{formatDate(ticket.createdAt)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  )
}
