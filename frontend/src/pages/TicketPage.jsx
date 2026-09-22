import { useCallback, useEffect, useState } from 'react'
import { inbox, incidents, messages, users } from '../services/api'
import { STATUSES, formatDate, formatLocation, isAdmin, isStaff, label } from '../services/format'
import Alert from '../components/Alert'

/**
 * One ticket: details, assignment (admin), status (assigned engineer or
 * admin), and the message thread.
 */
export default function TicketPage({ id, user, onBack, onApiError, onCountChange }) {
  const [ticket, setTicket] = useState(null)
  const [thread, setThread] = useState([])
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)

  const [staff, setStaff] = useState([])
  const [assignee, setAssignee] = useState('')
  const [status, setStatus] = useState('')
  const [draft, setDraft] = useState('')
  const [actionError, setActionError] = useState('')
  const [busy, setBusy] = useState(false)

  const load = useCallback(async () => {
    setError('')
    try {
      const [t, m] = await Promise.all([incidents.get(id), messages.list(id)])
      setTicket(t)
      setThread(m)
      setAssignee(t.assignedTo ? String(t.assignedTo.id) : '')
      setStatus(t.status)
      // Seeing the thread is what "read" means; the response carries the
      // caller's remaining unread total so the nav badge updates at once.
      const read = await inbox.markRead(id)
      onCountChange(read.unread)
    } catch (err) {
      setError(err.message)
      onApiError(err)
    } finally {
      setLoading(false)
    }
  }, [id, onApiError, onCountChange])

  useEffect(() => {
    load()
  }, [load])

  // Only admins can assign, and only they may list users.
  useEffect(() => {
    if (!isAdmin(user)) return
    users
      .list()
      .then((all) => setStaff(all.filter(isStaff)))
      .catch(onApiError)
  }, [user, onApiError])

  async function run(action) {
    setActionError('')
    setBusy(true)
    try {
      await action()
      await load()
    } catch (err) {
      setActionError(err.message)
      onApiError(err)
    } finally {
      setBusy(false)
    }
  }

  function handleAssign(event) {
    event.preventDefault()
    run(() => incidents.assign(id, assignee ? Number(assignee) : null))
  }

  function handleStatus(event) {
    event.preventDefault()
    run(() => incidents.updateStatus(id, status))
  }

  function handlePost(event) {
    event.preventDefault()
    run(async () => {
      await messages.create(id, draft)
      setDraft('')
    })
  }

  if (loading) return <p>Loading…</p>
  if (!ticket) {
    return (
      <div>
        <button type="button" onClick={onBack}>← Back</button>
        <Alert error={error || 'Ticket not found'} />
      </div>
    )
  }

  // The backend enforces this too; mirroring it here hides controls the
  // caller cannot use.
  const canChangeStatus = isAdmin(user) || ticket.assignedTo?.id === user.id
  const closed = ticket.status === 'closed'

  return (
    <div>
      <button type="button" onClick={onBack}>← Back to tickets</button>

      <h1>
        #{ticket.id} {ticket.title}{' '}
        <span className={`badge status-${ticket.status}`}>{label(ticket.status)}</span>
      </h1>

      <Alert error={error} />

      <dl className="details">
        <dt>Priority</dt><dd>{ticket.priority}</dd>
        <dt>Location</dt><dd>{formatLocation(ticket.location)}</dd>
        <dt>Reported by</dt><dd>{ticket.reportedBy.name} ({ticket.reportedBy.email})</dd>
        <dt>Assigned to</dt><dd>{ticket.assignedTo ? ticket.assignedTo.name : 'Unassigned'}</dd>
        <dt>Created</dt><dd>{formatDate(ticket.createdAt)}</dd>
        <dt>Updated</dt><dd>{formatDate(ticket.updatedAt)}</dd>
        {ticket.resolvedAt && (<><dt>Resolved</dt><dd>{formatDate(ticket.resolvedAt)}</dd></>)}
      </dl>

      {ticket.description && <p className="description">{ticket.description}</p>}

      {(isAdmin(user) || canChangeStatus) && (
        <div className="panel">
          <h2>Actions</h2>
          {isAdmin(user) && (
            <form onSubmit={handleAssign} className="row">
              <label>
                Assign to
                <select value={assignee} onChange={(e) => setAssignee(e.target.value)}>
                  <option value="">Unassigned</option>
                  {staff.map((s) => (
                    <option key={s.id} value={s.id}>{s.name} ({label(s.role)})</option>
                  ))}
                </select>
              </label>
              <button type="submit" disabled={busy}>Assign</button>
            </form>
          )}
          {canChangeStatus && (
            <form onSubmit={handleStatus} className="row">
              <label>
                Status
                <select value={status} onChange={(e) => setStatus(e.target.value)}>
                  {STATUSES.map((s) => (
                    <option key={s} value={s}>{label(s)}</option>
                  ))}
                </select>
              </label>
              <button type="submit" disabled={busy || status === ticket.status}>Update status</button>
            </form>
          )}
          <Alert error={actionError} />
        </div>
      )}

      <h2>Messages</h2>
      {thread.length === 0 ? (
        <p>No messages yet.</p>
      ) : (
        <ul className="thread">
          {thread.map((m) => (
            <li key={m.id}>
              <div className="meta">
                <strong>{m.author.name}</strong> ({label(m.author.role)}) · {formatDate(m.createdAt)}
              </div>
              <div>{m.message}</div>
            </li>
          ))}
        </ul>
      )}

      {closed ? (
        <p className="muted">This ticket is closed. Reopen it to post again.</p>
      ) : (
        <form onSubmit={handlePost}>
          <label>
            New message
            <textarea value={draft} onChange={(e) => setDraft(e.target.value)} rows={3} required />
          </label>
          {!isAdmin(user) && !canChangeStatus && <Alert error={actionError} />}
          <button type="submit" disabled={busy || !draft.trim()}>Post</button>
        </form>
      )}
    </div>
  )
}
