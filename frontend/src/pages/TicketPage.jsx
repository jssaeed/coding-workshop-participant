import { useEffect, useState } from 'react'
import { buildings, inbox, incidents, messages, users } from '../services/api'
import { STATUSES, formatDate, formatLocation, isAdmin, isStaff, label, range } from '../services/format'
import Alert from '../components/Alert'

// One ticket: its details, the actions the user is allowed to take, and the
// message thread. Opening the page marks the ticket as read.
export default function TicketPage({ id, user, onBack, setUnread }) {
  const [ticket, setTicket] = useState(null)
  const [thread, setThread] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  // Bumping this number reloads the ticket after an action
  const [refreshCount, setRefreshCount] = useState(0)

  // Actions
  const [staff, setStaff] = useState([]) // engineers and admins, for the assign dropdown
  const [assignee, setAssignee] = useState('')
  const [status, setStatus] = useState('')
  const [priority, setPriority] = useState('')
  // Location form (admin only): buildings for the dropdown, plus the chosen place
  const [buildingList, setBuildingList] = useState([])
  const [buildingId, setBuildingId] = useState('')
  const [floor, setFloor] = useState('')
  const [room, setRoom] = useState('')
  const [newMessage, setNewMessage] = useState('')
  const [actionError, setActionError] = useState('')
  const [busy, setBusy] = useState(false)

  // Load the ticket and its thread, then mark the ticket as read.
  useEffect(() => {
    async function load() {
      setError('')
      try {
        const loadedTicket = await incidents.get(id)
        setTicket(loadedTicket)
        setAssignee(loadedTicket.assignedTo ? String(loadedTicket.assignedTo.id) : '')
        setStatus(loadedTicket.status)
        setPriority(String(loadedTicket.priority))
        // Start the location form at the ticket's current place
        const place = loadedTicket.location
        setBuildingId(place ? String(place.building.id) : '')
        setFloor(place ? String(place.floor) : '')
        setRoom(place && place.room !== null ? String(place.room) : '')
        setThread(await messages.list(id))

        const read = await inbox.markRead(id)
        setUnread(read.unread) // update the badge in the nav
      } catch (err) {
        setError(err.message)
      } finally {
        setLoading(false)
      }
    }
    load()
  }, [id, refreshCount, setUnread])

  // Admins need the list of engineers to assign tickets to, and the list of
  // buildings to move tickets to.
  useEffect(() => {
    if (!isAdmin(user)) return
    users.list().then((all) => setStaff(all.filter(isStaff)))
    buildings.list().then(setBuildingList).catch(() => {})
  }, [user])

  // The building chosen in the location form, so we know how many floors to offer.
  const chosenBuilding = buildingList.find((b) => String(b.id) === buildingId)

  // Run an action, then reload the ticket so the page shows the result.
  async function runAction(action) {
    setActionError('')
    setBusy(true)
    try {
      await action()
      setRefreshCount(refreshCount + 1)
    } catch (err) {
      setActionError(err.message)
    } finally {
      setBusy(false)
    }
  }

  function handleAssign(event) {
    event.preventDefault()
    runAction(() => incidents.assign(id, assignee ? Number(assignee) : null))
  }

  function handleStatus(event) {
    event.preventDefault()
    runAction(() => incidents.updateStatus(id, status))
  }

  function handlePriority(event) {
    event.preventDefault()
    runAction(() => incidents.updatePriority(id, Number(priority)))
  }

  function handleLocation(event) {
    event.preventDefault()
    // No building chosen means "clear the location"
    const location = buildingId
      ? {
          buildingId: Number(buildingId),
          floor: Number(floor),
          room: room === '' ? undefined : Number(room),
        }
      : null
    runAction(() => incidents.updateLocation(id, location))
  }

  function handlePost(event) {
    event.preventDefault()
    runAction(async () => {
      await messages.create(id, newMessage)
      setNewMessage('')
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

  // The backend checks these too; this just hides buttons that would fail.
  const canAssign = isAdmin(user)
  const canChangeLocation = isAdmin(user)
  // The assigned engineer, or any admin, can change status and priority
  const canChangeStatus = isAdmin(user) || (ticket.assignedTo && ticket.assignedTo.id === user.id)
  const isClosed = ticket.status === 'closed'

  // True when the location form matches what the ticket already has
  const place = ticket.location
  const locationUnchanged =
    buildingId === (place ? String(place.building.id) : '') &&
    floor === (place ? String(place.floor) : '') &&
    room === (place && place.room !== null ? String(place.room) : '')

  return (
    <div>
      <button type="button" onClick={onBack}>← Back to tickets</button>

      <h1>
        #{ticket.id} {ticket.title}{' '}
        <span className={`badge status-${ticket.status}`}>{label(ticket.status)}</span>
      </h1>

      <Alert error={error} />

      <dl className="details">
        <dt>Priority</dt>
        <dd>{ticket.priority}</dd>
        <dt>Location</dt>
        <dd>{formatLocation(ticket.location)}</dd>
        <dt>Reported by</dt>
        <dd>{ticket.reportedBy.name} ({ticket.reportedBy.email})</dd>
        <dt>Assigned to</dt>
        <dd>{ticket.assignedTo ? ticket.assignedTo.name : 'Unassigned'}</dd>
        <dt>Created</dt>
        <dd>{formatDate(ticket.createdAt)}</dd>
        <dt>Updated</dt>
        <dd>{formatDate(ticket.updatedAt)}</dd>
        {ticket.resolvedAt && (
          <>
            <dt>Resolved</dt>
            <dd>{formatDate(ticket.resolvedAt)}</dd>
          </>
        )}
      </dl>

      {ticket.description && <p className="description">{ticket.description}</p>}

      {(canAssign || canChangeStatus) && (
        <div className="panel">
          <h2>Actions</h2>

          {canAssign && (
            <form onSubmit={handleAssign} className="row">
              <label>
                Assign to
                <select value={assignee} onChange={(e) => setAssignee(e.target.value)}>
                  <option value="">Unassigned</option>
                  {staff.map((person) => (
                    <option key={person.id} value={person.id}>
                      {person.name} ({label(person.role)})
                    </option>
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
              <button type="submit" disabled={busy || status === ticket.status}>
                Update status
              </button>
            </form>
          )}

          {canChangeStatus && (
            <form onSubmit={handlePriority} className="row">
              <label>
                Priority (1 = most urgent)
                <select value={priority} onChange={(e) => setPriority(e.target.value)}>
                  {range(5).map((n) => (
                    <option key={n} value={n}>{n}</option>
                  ))}
                </select>
              </label>
              <button type="submit" disabled={busy || Number(priority) === ticket.priority}>
                Update priority
              </button>
            </form>
          )}

          {canChangeLocation && (
            <form onSubmit={handleLocation} className="row">
              <label>
                Building
                <select
                  value={buildingId}
                  onChange={(e) => {
                    setBuildingId(e.target.value)
                    setFloor('') // the floor list changes with the building
                    setRoom('')
                  }}
                >
                  <option value="">No location</option>
                  {buildingList.map((b) => (
                    <option key={b.id} value={b.id}>{b.name}</option>
                  ))}
                </select>
              </label>
              <label>
                Floor
                <select
                  value={floor}
                  onChange={(e) => setFloor(e.target.value)}
                  disabled={!chosenBuilding}
                  required={!!chosenBuilding}
                >
                  <option value="">Choose…</option>
                  {chosenBuilding && range(chosenBuilding.floors).map((n) => (
                    <option key={n} value={n}>{n}</option>
                  ))}
                </select>
              </label>
              <label>
                Room (optional)
                <input
                  type="number"
                  min="1"
                  value={room}
                  onChange={(e) => setRoom(e.target.value)}
                  disabled={!chosenBuilding}
                />
              </label>
              <button type="submit" disabled={busy || locationUnchanged}>
                Update location
              </button>
            </form>
          )}
        </div>
      )}

      <h2>Messages</h2>
      {thread.length === 0 && <p>No messages yet.</p>}
      {thread.length > 0 && (
        <ul className="thread">
          {thread.map((message) => (
            <li key={message.id}>
              <div className="meta">
                <strong>{message.author.name}</strong> ({label(message.author.role)}) ·{' '}
                {formatDate(message.createdAt)}
              </div>
              <div>{message.message}</div>
            </li>
          ))}
        </ul>
      )}

      {isClosed ? (
        <p className="muted">This ticket is closed. Reopen it to post again.</p>
      ) : (
        <form onSubmit={handlePost}>
          <label>
            New message
            <textarea
              value={newMessage}
              onChange={(e) => setNewMessage(e.target.value)}
              rows={3}
              required
            />
          </label>
          <button type="submit" disabled={busy || newMessage.trim() === ''}>Post</button>
        </form>
      )}

      <Alert error={actionError} />
    </div>
  )
}
