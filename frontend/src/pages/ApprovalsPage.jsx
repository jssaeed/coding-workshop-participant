import { useEffect, useState } from 'react'
import { Button, Card, Collapse, Empty, Input, Space, Spin, Tag, Typography } from 'antd'
import { CheckOutlined, CloseOutlined, ReloadOutlined } from '@ant-design/icons'
import { incidents, messages } from '../services/api'
import { STATUS_COLORS, formatDate, formatLocation, label, personName } from '../services/format'
import Alert from '../components/Alert'

// Facility admin only: every ticket where an engineer has asked for
// "blocked" or "resolved", with the reason and the whole thread, so the
// admin can approve or reject without opening each ticket.
export default function ApprovalsPage({ onOpen }) {
  const [items, setItems] = useState([]) // [{ticket, thread}]
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')
  const [refreshCount, setRefreshCount] = useState(0)
  const [notes, setNotes] = useState({}) // ticket id -> the admin's note
  const [busyId, setBusyId] = useState(null)

  // Load the pending tickets, then each one's thread
  useEffect(() => {
    async function load() {
      setLoading(true)
      setError('')
      try {
        const pending = await incidents.list({ scope: 'pending' })
        const threads = await Promise.all(pending.map((ticket) => messages.list(ticket.id)))
        setItems(pending.map((ticket, index) => ({ ticket, thread: threads[index] })))
      } catch (err) {
        setError(err.message)
      } finally {
        setLoading(false)
      }
    }
    load()
  }, [refreshCount])

  async function decide(ticket, decision) {
    setError('')
    setSuccess('')
    setBusyId(ticket.id)
    try {
      await incidents.decideApproval(ticket.id, decision, notes[ticket.id] || undefined)
      setSuccess(`#${ticket.id}: ${decision === 'approve' ? 'approved' : 'rejected'}.`)
      setRefreshCount(refreshCount + 1)
    } catch (err) {
      setError(err.message)
    } finally {
      setBusyId(null)
    }
  }

  return (
    <div>
      <div className="page-title">
        <Typography.Title level={2} style={{ margin: 0 }}>Approvals</Typography.Title>
        <Button icon={<ReloadOutlined />} onClick={() => setRefreshCount(refreshCount + 1)}>Refresh</Button>
      </div>

      <Alert error={error} success={success} />

      {loading && <Spin />}
      {!loading && items.length === 0 && <Empty description="Nothing is waiting for approval." />}

      {items.map(({ ticket, thread }) => {
        const request = ticket.pendingApproval
        return (
          <Card
            key={ticket.id}
            style={{ marginBottom: 16 }}
            title={
              <Space wrap>
                <a onClick={() => onOpen(ticket.id)}>#{ticket.id} {ticket.title}</a>
                <Tag color={STATUS_COLORS[ticket.status]}>{label(ticket.status)}</Tag>
                <span className="muted">→</span>
                <Tag color={STATUS_COLORS[request.status]}>{label(request.status)}?</Tag>
              </Space>
            }
            extra={<span className="muted">{formatLocation(ticket.location)}</span>}
          >
            <p style={{ marginTop: 0 }}>
              <strong>{request.requestedBy ? request.requestedBy.name : 'An engineer'}</strong> asked to mark this
              ticket <strong>{label(request.status).toLowerCase()}</strong> on {formatDate(request.requestedAt)}.
            </p>
            {request.note ? (
              <p className="approval-reason">Reason: {request.note}</p>
            ) : (
              <p className="muted">No reason given.</p>
            )}
            <p className="muted" style={{ marginBottom: 8 }}>
              Reported by {personName(ticket.reportedBy)} · priority P{ticket.priority}
              {ticket.description && ` · ${ticket.description}`}
            </p>

            <Collapse
              size="small"
              items={[{
                key: 'thread',
                label: `Thread (${thread.length} message${thread.length === 1 ? '' : 's'})`,
                children: thread.length === 0 ? (
                  <p className="muted">No messages yet.</p>
                ) : (
                  <ul className="thread">
                    {thread.map((message) => (
                      <li key={message.id}>
                        <div>
                          <div>
                            <strong>{personName(message.author)}</strong>
                            {message.author && <Tag style={{ marginLeft: 6 }}>{label(message.author.role)}</Tag>}
                            <span className="muted"> · {formatDate(message.createdAt)}</span>
                          </div>
                          <div className="message-text">{message.message}</div>
                        </div>
                      </li>
                    ))}
                  </ul>
                ),
              }]}
            />

            <Space wrap style={{ marginTop: 12 }}>
              <Input
                placeholder="Note for the thread (optional)"
                value={notes[ticket.id] || ''}
                onChange={(e) => setNotes({ ...notes, [ticket.id]: e.target.value })}
                style={{ width: 300 }}
              />
              <Button type="primary" icon={<CheckOutlined />} loading={busyId === ticket.id}
                      onClick={() => decide(ticket, 'approve')}>
                Approve
              </Button>
              <Button danger icon={<CloseOutlined />} loading={busyId === ticket.id}
                      onClick={() => decide(ticket, 'reject')}>
                Reject
              </Button>
            </Space>
          </Card>
        )
      })}
    </div>
  )
}
