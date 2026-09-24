import { useEffect, useState } from 'react'
import {
  Alert as AntAlert, Avatar, Button, Card, Descriptions, Divider, Form, Input, InputNumber, Select, Space, Tag, Typography,
} from 'antd'
import { ArrowLeftOutlined, CheckOutlined, CloseOutlined, SendOutlined } from '@ant-design/icons'
import { buildings, inbox, incidents, messages, users } from '../services/api'
import {
  APPROVAL_STATUSES, PRIORITIES, PRIORITY_COLORS, STATUSES, STATUS_COLORS,
  floorOptions, formatDate, formatLocation, initial, isAdmin, isStaff, label, personName, range, roomLabel, roomsOnFloor,
} from '../services/format'
import Alert from '../components/Alert'
import TicketProgress from '../components/TicketProgress'

// One ticket: its details, the actions the user is allowed to take, and the
// message thread. Opening the page marks the ticket as read.
export default function TicketPage({ id, user, onBack, setUnread }) {
  const [ticket, setTicket] = useState(null)
  const [thread, setThread] = useState([]) // the newest messages, oldest first
  const [threadTotal, setThreadTotal] = useState(0) // how many the ticket has in all
  const [hasEarlier, setHasEarlier] = useState(false) // older messages not shown yet
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  // Bumping this number reloads the ticket after an action
  const [refreshCount, setRefreshCount] = useState(0)

  // Actions
  const [staff, setStaff] = useState([]) // engineers and admins, for the assign dropdown
  const [assignee, setAssignee] = useState('') // '' means unassigned
  const [status, setStatus] = useState('')
  const [statusNote, setStatusNote] = useState('') // optional reason, shown on the thread
  const [decisionNote, setDecisionNote] = useState('') // admin's reason when approving/rejecting
  const [priority, setPriority] = useState(3)
  // Location form (admin only): buildings for the dropdown, plus the chosen place
  const [buildingList, setBuildingList] = useState([])
  const [buildingId, setBuildingId] = useState('') // '' means no location
  const [floor, setFloor] = useState(null)
  const [room, setRoom] = useState(null)
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
        setAssignee(loadedTicket.assignedTo ? loadedTicket.assignedTo.id : '')
        setStatus(loadedTicket.status)
        setPriority(loadedTicket.priority)
        // Start the location form at the ticket's current place
        const place = loadedTicket.location
        setBuildingId(place ? place.building.id : '')
        setFloor(place ? place.floor : null)
        setRoom(place ? place.room : null)
        const latest = await messages.list(id)
        setThread(latest.items)
        setThreadTotal(latest.total)
        setHasEarlier(latest.hasMore)

        const read = await inbox.markRead(id)
        setUnread(read.unread) // update the bell badge in the header
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
    users.list({ role: 'engineer,facility_admin', sort: 'name', limit: 100 })
      .then((data) => setStaff(data.items.filter(isStaff)))
      .catch(() => {})
    buildings.list().then(setBuildingList).catch(() => {})
  }, [user])

  // The building chosen in the location form, so we know how many floors to offer.
  const chosenBuilding = buildingList.find((b) => b.id === buildingId)
  const roomCount = roomsOnFloor(chosenBuilding, floor)

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

  function handleLocation() {
    // No building chosen means "clear the location"
    const location = buildingId !== '' ? { buildingId, floor, room: room ?? undefined } : null
    runAction(() => incidents.updateLocation(id, location))
  }

  // The thread comes in pages, newest first. This fetches the page of
  // messages before the oldest one shown and puts it on top.
  async function loadEarlier() {
    setActionError('')
    setBusy(true)
    try {
      const earlier = await messages.list(id, { before: thread[0].id })
      setThread([...earlier.items, ...thread])
      setHasEarlier(earlier.hasMore)
    } catch (err) {
      setActionError(err.message)
    } finally {
      setBusy(false)
    }
  }

  function handlePost() {
    runAction(async () => {
      await messages.create(id, newMessage)
      setNewMessage('')
    })
  }

  if (loading) return <Card loading />

  if (!ticket) {
    return (
      <div>
        <Button icon={<ArrowLeftOutlined />} onClick={onBack}>Back</Button>
        <Alert error={error || 'Ticket not found'} />
      </div>
    )
  }

  // The backend checks these too; this just hides controls that would fail.
  const canAssign = isAdmin(user)
  const canChangeLocation = isAdmin(user)
  // The assigned engineer, or any admin, can change status and priority
  const canChangeStatus = isAdmin(user) || (ticket.assignedTo && ticket.assignedTo.id === user.id)
  const isClosed = ticket.status === 'closed'
  // An engineer choosing blocked/resolved is asking, not deciding
  const isRequest = !isAdmin(user) && APPROVAL_STATUSES.includes(status)
  const pending = ticket.pendingApproval

  // True when the location form matches what the ticket already has
  const place = ticket.location
  const locationUnchanged =
    buildingId === (place ? place.building.id : '') &&
    floor === (place ? place.floor : null) &&
    (room ?? null) === (place ? place.room : null)

  return (
    <div>
      <Button icon={<ArrowLeftOutlined />} onClick={onBack} style={{ marginBottom: 16 }}>
        Back to tickets
      </Button>

      <TicketProgress status={ticket.status} />

      {pending && (
        <AntAlert
          type="warning"
          showIcon
          style={{ marginBottom: 16 }}
          message={`Awaiting approval: ${pending.requestedBy ? pending.requestedBy.name : 'An engineer'} asked to mark this ticket ${label(pending.status).toLowerCase()}`}
          description={
            <div>
              {pending.note && <div>Reason: {pending.note}</div>}
              <div className="muted">Requested {formatDate(pending.requestedAt)}</div>
              {isAdmin(user) && (
                <Space wrap style={{ marginTop: 8 }}>
                  <Input
                    placeholder="Note for the thread (optional)"
                    value={decisionNote}
                    onChange={(e) => setDecisionNote(e.target.value)}
                    style={{ width: 280 }}
                  />
                  <Button type="primary" icon={<CheckOutlined />} loading={busy}
                          onClick={() => runAction(() => incidents.decideApproval(id, 'approve', decisionNote || undefined))}>
                    Approve
                  </Button>
                  <Button danger icon={<CloseOutlined />} loading={busy}
                          onClick={() => runAction(() => incidents.decideApproval(id, 'reject', decisionNote || undefined))}>
                    Reject
                  </Button>
                </Space>
              )}
            </div>
          }
        />
      )}

      <Card
        title={
          <Space wrap>
            <span>#{ticket.id} {ticket.title}</span>
            <Tag color={STATUS_COLORS[ticket.status]}>{label(ticket.status)}</Tag>
            <Tag color={PRIORITY_COLORS[ticket.priority]}>P{ticket.priority}</Tag>
          </Space>
        }
      >
        <Alert error={error} />
        <Descriptions column={{ xs: 1, sm: 2 }} size="small">
          <Descriptions.Item label="Location">{formatLocation(ticket.location)}</Descriptions.Item>
          <Descriptions.Item label="Reported by">
            {personName(ticket.reportedBy)}
            {ticket.reportedBy && ` (${ticket.reportedBy.email})`}
          </Descriptions.Item>
          <Descriptions.Item label="Assigned to">
            {ticket.assignedTo ? ticket.assignedTo.name : 'Unassigned'}
          </Descriptions.Item>
          <Descriptions.Item label="Created">{formatDate(ticket.createdAt)}</Descriptions.Item>
          <Descriptions.Item label="Updated">{formatDate(ticket.updatedAt)}</Descriptions.Item>
          {ticket.resolvedAt && (
            <Descriptions.Item label="Resolved">{formatDate(ticket.resolvedAt)}</Descriptions.Item>
          )}
        </Descriptions>
        {ticket.description && (
          <>
            <Divider style={{ margin: '12px 0' }} />
            <Typography.Paragraph className="description">{ticket.description}</Typography.Paragraph>
          </>
        )}
      </Card>

      {(canAssign || canChangeStatus) && (
        <Card title="Actions" style={{ marginTop: 16 }}>
          <Space direction="vertical" size="middle" style={{ width: '100%' }}>
            {canAssign && (
              <Form layout="inline">
                <Form.Item label="Assign to">
                  <Select
                    value={assignee}
                    onChange={setAssignee}
                    style={{ width: 220 }}
                    options={[
                      { value: '', label: 'Unassigned' },
                      ...staff.map((p) => ({ value: p.id, label: `${p.name} (${label(p.role)})` })),
                    ]}
                  />
                </Form.Item>
                <Button
                  onClick={() => runAction(() => incidents.assign(id, assignee === '' ? null : assignee))}
                  loading={busy}
                  disabled={assignee === (ticket.assignedTo ? ticket.assignedTo.id : '')}
                >
                  Assign
                </Button>
              </Form>
            )}

            {canChangeStatus && (
              <Form layout="inline">
                <Form.Item label="Status">
                  <Select
                    value={status}
                    onChange={setStatus}
                    style={{ width: 160 }}
                    // "open" and "assigned" follow the assignment (the backend
                    // enforces this too): use the Assign form to change them.
                    options={STATUSES.map((s) => ({
                      value: s,
                      label: label(s),
                      disabled:
                        (s === 'open' && ticket.assignedTo !== null) ||
                        (s === 'assigned' && ticket.assignedTo === null),
                    }))}
                  />
                </Form.Item>
                <Form.Item label="Note (optional)">
                  <Input value={statusNote} onChange={(e) => setStatusNote(e.target.value)} style={{ width: 220 }}
                         placeholder={isRequest ? 'Why? Shown to the admin' : ''} />
                </Form.Item>
                <Button
                  onClick={() => runAction(async () => {
                    await incidents.updateStatus(id, status, statusNote || undefined)
                    setStatusNote('')
                  })}
                  loading={busy}
                  disabled={status === ticket.status || (pending && pending.status === status)}
                >
                  {isRequest ? `Request ${label(status).toLowerCase()}` : 'Update status'}
                </Button>
              </Form>
            )}

            {canChangeStatus && (
              <Form layout="inline">
                <Form.Item label="Priority (1 = most urgent)">
                  <Select
                    value={priority}
                    onChange={setPriority}
                    style={{ width: 100 }}
                    options={PRIORITIES.map((p) => ({ value: p, label: `P${p}` }))}
                  />
                </Form.Item>
                <Button
                  onClick={() => runAction(() => incidents.updatePriority(id, priority))}
                  loading={busy}
                  disabled={priority === ticket.priority}
                >
                  Update priority
                </Button>
              </Form>
            )}

            {canChangeLocation && (
              <Form layout="inline">
                <Form.Item label="Building">
                  <Select
                    value={buildingId}
                    onChange={(value) => {
                      setBuildingId(value)
                      setFloor(null) // the floor list changes with the building
                      setRoom(null)
                    }}
                    style={{ width: 180 }}
                    options={[
                      { value: '', label: 'No location' },
                      ...buildingList.map((b) => ({ value: b.id, label: b.name })),
                    ]}
                  />
                </Form.Item>
                <Form.Item label="Floor">
                  <Select
                    value={floor}
                    onChange={(value) => { setFloor(value); setRoom(null) }}
                    placeholder="Choose…"
                    disabled={!chosenBuilding}
                    style={{ width: 110 }}
                    options={floorOptions(chosenBuilding)}
                  />
                </Form.Item>
                <Form.Item label="Room">
                  {roomCount > 0 ? (
                    <Select allowClear value={room} onChange={(v) => setRoom(v ?? null)} placeholder="Choose…" style={{ width: 110 }}
                            options={range(roomCount).map((n) => ({ value: n, label: roomLabel(chosenBuilding, floor, n) }))} />
                  ) : (
                    <InputNumber min={1} value={room} onChange={setRoom} disabled={!chosenBuilding} style={{ width: 100 }} />
                  )}
                </Form.Item>
                <Button
                  onClick={handleLocation}
                  loading={busy}
                  disabled={locationUnchanged || (chosenBuilding && !floor)}
                >
                  Update location
                </Button>
              </Form>
            )}
          </Space>
          <Alert error={actionError} />
        </Card>
      )}

      <Card title="Messages" style={{ marginTop: 16 }}>
        {thread.length === 0 && <p className="muted">No messages yet.</p>}
        {hasEarlier && (
          <p className="muted">
            Showing the latest {thread.length} of {threadTotal} messages.{' '}
            <Button size="small" onClick={loadEarlier} loading={busy}>Show earlier messages</Button>
          </p>
        )}
        <ul className="thread">
          {thread.map((message) => (
            <li key={message.id}>
              <Avatar size="small" style={{ backgroundColor: message.author ? '#1e3a5f' : '#9ca3af', flexShrink: 0 }}>
                {message.author ? initial(message.author.name) : '?'}
              </Avatar>
              <div>
                <div>
                  <strong>{personName(message.author)}</strong>
                  {message.author && <Tag>{label(message.author.role)}</Tag>}
                  <span className="muted">· {formatDate(message.createdAt)}</span>
                </div>
                <div className="message-text">{message.message}</div>
              </div>
            </li>
          ))}
        </ul>

        {isClosed ? (
          <p className="muted">This ticket is closed. Reopen it to post again.</p>
        ) : (
          <Space.Compact style={{ width: '100%', marginTop: 12 }}>
            <Input.TextArea
              value={newMessage}
              onChange={(e) => setNewMessage(e.target.value)}
              placeholder="Write a message…"
              autoSize={{ minRows: 2, maxRows: 6 }}
              onPressEnter={(e) => {
                if (!e.shiftKey && newMessage.trim()) { e.preventDefault(); handlePost() }
              }}
            />
            <Button
              type="primary"
              icon={<SendOutlined />}
              onClick={handlePost}
              loading={busy}
              disabled={newMessage.trim() === ''}
            >
              Post
            </Button>
          </Space.Compact>
        )}
      </Card>
    </div>
  )
}
