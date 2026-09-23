import { useEffect, useState } from 'react'
import { Badge, Button, Card, Empty, Spin, Tag, Typography } from 'antd'
import { CheckOutlined } from '@ant-design/icons'
import { inbox } from '../services/api'
import { STATUS_COLORS, formatDate, label, personName } from '../services/format'
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
        setUnread(data.unread) // keep the bell badge in step with the list
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
      <div className="page-title">
        <Typography.Title level={2} style={{ margin: 0 }}>Inbox</Typography.Title>
        <Button icon={<CheckOutlined />} onClick={handleMarkAllRead} disabled={items.length === 0}>
          Mark all read
        </Button>
      </div>

      <Alert error={error} />

      {loading && <Spin />}
      {!loading && items.length === 0 && <Empty description="Nothing new. You are all caught up." />}
      {items.map((item) => (
        <Card
          key={item.incident.id}
          size="small"
          hoverable
          onClick={() => onOpen(item.incident.id)}
          style={{ marginBottom: 12 }}
          title={
            <span>
              #{item.incident.id} {item.incident.title}{' '}
              <Tag color={STATUS_COLORS[item.incident.status]}>{label(item.incident.status)}</Tag>
            </span>
          }
          extra={<Badge count={item.unreadCount} color="#1e3a5f" />}
        >
          <div className="muted">
            <strong>{personName(item.latestMessage.author)}</strong> · {formatDate(item.latestMessage.createdAt)}
          </div>
          <div className="preview">{item.latestMessage.message}</div>
        </Card>
      ))}
    </div>
  )
}
