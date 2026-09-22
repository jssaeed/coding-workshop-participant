import { useCallback, useEffect, useState } from 'react'
import { incidents } from '../services/api'
import { STATUSES, formatDate, formatLocation, isAdmin, isStaff, label } from '../services/format'
import Alert from '../components/Alert'

const EMPTY_TICKET = {
  title: '',
  description: '',
  priority: 3,
  building: '',
  floor: '',
  room: '',
}

/**
 * Ticket list with scope/status/priority filters, plus a form to file one.
 */
export default function TicketsPage({ user, onOpen, onApiError }) {
  const [scope, setScope] = useState('mine')
  const [status, setStatus] = useState('')
  const [priority, setPriority] = useState('')
  const [tickets, setTickets] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const [showForm, setShowForm] = useState(false)
  const [draft, setDraft] = useState(EMPTY_TICKET)
  const [formError, setFormError] = useState('')
  const [saving, setSaving] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      setTickets(await incidents.list({ scope, status, priority }))
    } catch (err) {
      setError(err.message)
      onApiError(err)
    } finally {
      setLoading(false)
    }
  }, [scope, status, priority, onApiError])

  useEffect(() => {
    load()
  }, [load])

  function setField(field) {
    return (event) => setDraft({ ...draft, [field]: event.target.value })
  }

  async function handleCreate(event) {
    event.preventDefault()
    setFormError('')
    setSaving(true)
    try {
      const ticket = {
        title: draft.title,
        description: draft.description,
        priority: Number(draft.priority),
      }
      // Location is optional; only send it when a building was given.
      if (draft.building.trim()) {
        ticket.location = {
          building: draft.building,
          floor: draft.floor,
          room: draft.room,
        }
      }
      const created = await incidents.create(ticket)
      setDraft(EMPTY_TICKET)
      setShowForm(false)
      onOpen(created.id)
    } catch (err) {
      setFormError(err.message)
      onApiError(err)
    } finally {
      setSaving(false)
    }
  }

  const scopes = [
    ['mine', 'My tickets'],
    isStaff(user) && ['assigned', 'Assigned to me'],
    isAdmin(user) && ['unassigned', 'Unassigned'],
    isAdmin(user) && ['all', 'All tickets'],
  ].filter(Boolean)

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
            <input value={draft.title} onChange={setField('title')} required />
          </label>
          <label>
            Description
            <textarea value={draft.description} onChange={setField('description')} rows={3} />
          </label>
          <label>
            Priority (1 = most urgent)
            <select value={draft.priority} onChange={setField('priority')}>
              {[1, 2, 3, 4, 5].map((p) => (
                <option key={p} value={p}>{p}</option>
              ))}
            </select>
          </label>
          <div className="row">
            <label>
              Building
              <input value={draft.building} onChange={setField('building')} />
            </label>
            <label>
              Floor
              <input value={draft.floor} onChange={setField('floor')} required={!!draft.building} />
            </label>
            <label>
              Room (optional)
              <input value={draft.room} onChange={setField('room')} />
            </label>
          </div>
          <Alert error={formError} />
          <button type="submit" disabled={saving}>
            {saving ? 'Saving…' : 'File ticket'}
          </button>
        </form>
      )}

      <div className="row filters">
        <label>
          Show
          <select value={scope} onChange={(e) => setScope(e.target.value)}>
            {scopes.map(([value, text]) => (
              <option key={value} value={value}>{text}</option>
            ))}
          </select>
        </label>
        <label>
          Status
          <select value={status} onChange={(e) => setStatus(e.target.value)} disabled={scope === 'unassigned'}>
            <option value="">Any</option>
            {STATUSES.map((s) => (
              <option key={s} value={s}>{label(s)}</option>
            ))}
          </select>
        </label>
        <label>
          Priority
          <select value={priority} onChange={(e) => setPriority(e.target.value)} disabled={scope === 'unassigned'}>
            <option value="">Any</option>
            {[1, 2, 3, 4, 5].map((p) => (
              <option key={p} value={p}>{p}</option>
            ))}
          </select>
        </label>
        <button type="button" onClick={load} disabled={loading}>Refresh</button>
      </div>

      <Alert error={error} />

      {loading ? (
        <p>Loading…</p>
      ) : tickets.length === 0 ? (
        <p>No tickets.</p>
      ) : (
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
            {tickets.map((t) => (
              <tr key={t.id} onClick={() => onOpen(t.id)} className="clickable">
                <td>{t.id}</td>
                <td>{t.title}</td>
                <td><span className={`badge status-${t.status}`}>{label(t.status)}</span></td>
                <td>{t.priority}</td>
                <td>{formatLocation(t.location)}</td>
                <td>{t.reportedBy.name}</td>
                <td>{t.assignedTo ? t.assignedTo.name : '—'}</td>
                <td>{formatDate(t.createdAt)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  )
}
