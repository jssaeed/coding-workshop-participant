import { useEffect, useRef, useState } from 'react'
import { Button, Card, Collapse, Empty, Input, Pagination, Space, Spin, Tag, Typography } from 'antd'
import { CheckOutlined, CloseOutlined, ReloadOutlined, SearchOutlined } from '@ant-design/icons'
import { incidents, messages } from '../services/api'
import { STATUS_COLORS, formatDate, formatLocation, label, personName } from '../services/format'
import useDebounce from '../hooks/useDebounce'
import Alert from '../components/Alert'

// Requests per page. Each card carries its thread, so pages are kept short.
const PAGE_SIZE = 10

// Facility admin only: every ticket where an engineer has asked for
// "blocked" or "resolved", with the reason and the whole thread, so the
// admin can approve or reject without opening each ticket.
export default function ApprovalsPage({ onOpen }) {
  const [items, setItems] = useState([]) // [{ticket, thread, threadTotal}]
  const [total, setTotal] = useState(0) // requests waiting in all
  const [page, setPage] = useState(1)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')
  const [refreshCount, setRefreshCount] = useState(0)
  const [notes, setNotes] = useState({}) // ticket id -> the admin's note
  const [busyId, setBusyId] = useState(null)
  const [search, setSearch] = useState('')
  const query = useDebounce(search.trim()) // sent once typing pauses

  // Load the page of pending tickets, then each one's latest messages.
  // A new search starts again from page 1.
  const lastQuery = useRef(query)
  useEffect(() => {
    if (lastQuery.current !== query) {
      lastQuery.current = query
      if (page !== 1) {
        setPage(1) // runs this effect again, on page 1
        return
      }
    }

    async function load() {
      setLoading(true)
      setError('')
      try {
        const pending = await incidents.list({ scope: 'pending', q: query, page, limit: PAGE_SIZE })
        const threads = await Promise.all(pending.items.map((ticket) => messages.list(ticket.id)))
        setItems(pending.items.map((ticket, index) => ({
          ticket, thread: threads[index].items, threadTotal: threads[index].total,
        })))
        setTotal(pending.total)
      } catch (err) {
        setError(err.message)
      } finally {
        setLoading(false)
      }
    }
    load()
  }, [query, page, refreshCount])

  async function decide(ticket, decision) {
    setError('')
    setSuccess('')
    setBusyId(ticket.id)
    try {
      await incidents.decideApproval(ticket.id, decision, notes[ticket.id] || undefined)
      setSuccess(`#${ticket.id}: ${decision === 'approve' ? 'approved' : 'rejected'}.`)
      // Deciding the last request on a page moves us to the one before it
      if (items.length === 1 && page > 1) setPage(page - 1)
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
        <Space wrap>
          <Input
            allowClear
            prefix={<SearchOutlined />}
            placeholder="Search requests"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            style={{ width: 220 }}
          />
          <Button icon={<ReloadOutlined />} onClick={() => setRefreshCount(refreshCount + 1)}>Refresh</Button>
        </Space>
      </div>

      <Alert error={error} success={success} />

      {loading && <Spin />}
      {!loading && items.length === 0 && (
        <Empty description={query ? 'No requests match your search.' : 'Nothing is waiting for approval.'} />
      )}

      {items.map(({ ticket, thread, threadTotal }) => {
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
                label: `Thread (${threadTotal} message${threadTotal === 1 ? '' : 's'})`,
                children: thread.length === 0 ? (
                  <p className="muted">No messages yet.</p>
                ) : (
                  <>
                    {thread.length < threadTotal && (
                      <p className="muted">
                        The latest {thread.length} messages. <a onClick={() => onOpen(ticket.id)}>Open the ticket</a> for the whole thread.
                      </p>
                    )}
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
                  </>
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

      {total > PAGE_SIZE && (
        <Pagination
          current={page}
          pageSize={PAGE_SIZE}
          total={total}
          onChange={setPage}
          showSizeChanger={false}
          showTotal={(count, [from, to]) => `${from}–${to} of ${count}`}
        />
      )}
    </div>
  )
}
