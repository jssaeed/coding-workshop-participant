import { useEffect, useState } from 'react'
import { inbox } from '../services/api'
import { formatDate, label } from '../services/format'
import Alert from '../components/Alert'

// Tickets with changes the user has not seen yet. Opening one marks it read.
export default function InboxPage({ onOpen, setUnread }) {
  const [items, setItems] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [refreshCount, setRefreshCount] = useState(0)

  useEffect(() => {
    async function load() {
      setLoading(true)
      setError('')
      try {
        const data = await inbox.list()
        setItems(data.items)
        setUnread(data.unread) // keep the nav badge in step with the list
      } catch (err) {
        setError(err.message)
      } finally {
        setLoading(false)
      }
    }
    load()
  }, [refreshCount, setUnread])

  async function handleMarkAllRead() {
    try {
      await inbox.markAllRead()
      setRefreshCount(refreshCount + 1)
    } catch (err) {
      setError(err.message)
    }
  }

  return (
    <div>
      <div className="row space-between">
        <h1>Inbox</h1>
        <button type="button" onClick={handleMarkAllRead} disabled={items.length === 0}>
          Mark all read
        </button>
      </div>

      <Alert error={error} />

      {loading && <p>Loading…</p>}
      {!loading && items.length === 0 && <p>Nothing new.</p>}
      {!loading && items.length > 0 && (
        <ul className="inbox">
          {items.map((item) => (
            <li key={item.incident.id} onClick={() => onOpen(item.incident.id)} className="clickable">
              <div className="row space-between">
                <strong>
                  #{item.incident.id} {item.incident.title}{' '}
                  <span className={`badge status-${item.incident.status}`}>
                    {label(item.incident.status)}
                  </span>
                </strong>
                <span className="badge">{item.unreadCount} new</span>
              </div>
              <div className="meta">
                {item.latestMessage.author.name} · {formatDate(item.latestMessage.createdAt)}
              </div>
              <div className="preview">{item.latestMessage.message}</div>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
