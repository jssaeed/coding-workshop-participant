import { useCallback, useEffect, useState } from 'react'
import { inbox } from '../services/api'
import { formatDate, label } from '../services/format'
import Alert from '../components/Alert'

/**
 * Tickets with activity the user has not seen: new messages, status changes,
 * assignments. Opening a ticket marks it read.
 */
export default function InboxPage({ onOpen, onCountChange, onApiError }) {
  const [items, setItems] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const data = await inbox.list()
      setItems(data.items)
      onCountChange(data.unread)
    } catch (err) {
      setError(err.message)
      onApiError(err)
    } finally {
      setLoading(false)
    }
  }, [onCountChange, onApiError])

  useEffect(() => {
    load()
  }, [load])

  async function markAllRead() {
    setBusy(true)
    setError('')
    try {
      await inbox.markAllRead()
      await load()
    } catch (err) {
      setError(err.message)
      onApiError(err)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div>
      <div className="row space-between">
        <h1>Inbox</h1>
        <button type="button" onClick={markAllRead} disabled={busy || items.length === 0}>
          Mark all read
        </button>
      </div>

      <Alert error={error} />

      {loading ? (
        <p>Loading…</p>
      ) : items.length === 0 ? (
        <p>Nothing new.</p>
      ) : (
        <ul className="inbox">
          {items.map(({ incident, unreadCount, latestMessage }) => (
            <li key={incident.id} onClick={() => onOpen(incident.id)} className="clickable">
              <div className="row space-between">
                <strong>
                  #{incident.id} {incident.title}{' '}
                  <span className={`badge status-${incident.status}`}>{label(incident.status)}</span>
                </strong>
                <span className="badge">{unreadCount} new</span>
              </div>
              <div className="meta">
                {latestMessage.author.name} · {formatDate(latestMessage.createdAt)}
              </div>
              <div className="preview">{latestMessage.message}</div>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
