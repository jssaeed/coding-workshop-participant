import { useEffect, useState } from 'react'
import { Button, Form, Input, InputNumber, Modal, Select, Space, Table, Tag, Typography } from 'antd'
import { PlusOutlined, ReloadOutlined } from '@ant-design/icons'
import { buildings, incidents } from '../services/api'
import {
  PRIORITIES, PRIORITY_COLORS, STATUSES, STATUS_COLORS,
  floorOptions, formatDate, formatLocation, isAdmin, isStaff, label, personName, range, roomLabel, roomsOnFloor,
} from '../services/format'
import Alert from '../components/Alert'
import MyTicketStats from '../components/MyTicketStats'

// The ticket list, with filters and a dialog to file a new ticket.
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

  // The new-ticket dialog
  const [showForm, setShowForm] = useState(false)
  const [form] = Form.useForm()
  const [buildingList, setBuildingList] = useState([]) // for the dropdown
  const [formError, setFormError] = useState('')
  const [saving, setSaving] = useState(false)

  // Load the buildings once, for the location dropdowns.
  useEffect(() => {
    buildings.list().then(setBuildingList).catch(() => {})
  }, [])

  // The building chosen in the form, so we know how many floors to offer.
  const chosenBuildingId = Form.useWatch('buildingId', form)
  const chosenBuilding = buildingList.find((b) => b.id === chosenBuildingId)
  // ...and the floor, so we know whether to offer a list of rooms
  const chosenFloor = Form.useWatch('floor', form)
  const roomCount = roomsOnFloor(chosenBuilding, chosenFloor)

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

  async function handleCreate(values) {
    setFormError('')
    setSaving(true)
    try {
      const ticket = { title: values.title, description: values.description, priority: values.priority }
      if (values.buildingId) {
        ticket.location = { buildingId: values.buildingId, floor: values.floor, room: values.room ?? undefined }
      }
      const created = await incidents.create(ticket)
      form.resetFields()
      setShowForm(false)
      onOpen(created.id)
    } catch (err) {
      setFormError(err.message)
    } finally {
      setSaving(false)
    }
  }

  // Which "Show" options this user gets
  const scopeOptions = [{ value: 'mine', label: 'My tickets' }]
  if (isStaff(user)) scopeOptions.push({ value: 'assigned', label: 'Assigned to me' })
  if (isAdmin(user)) {
    scopeOptions.push({ value: 'unassigned', label: 'Unassigned' }, { value: 'all', label: 'All tickets' })
  }

  const columns = [
    { title: '#', dataIndex: 'id', width: 60 },
    { title: 'Title', dataIndex: 'title', ellipsis: true },
    {
      title: 'Status',
      dataIndex: 'status',
      render: (value) => <Tag color={STATUS_COLORS[value]}>{label(value)}</Tag>,
    },
    {
      title: 'Priority',
      dataIndex: 'priority',
      width: 90,
      render: (value) => <Tag color={PRIORITY_COLORS[value]}>P{value}</Tag>,
    },
    { title: 'Location', dataIndex: 'location', render: formatLocation, responsive: ['md'] },
    { title: 'Reported by', dataIndex: 'reportedBy', render: personName, responsive: ['lg'] },
    { title: 'Assigned to', dataIndex: ['assignedTo', 'name'], render: (v) => v || '—', responsive: ['lg'] },
    { title: 'Created', dataIndex: 'createdAt', render: formatDate, responsive: ['md'] },
  ]

  return (
    <div>
      <div className="page-title">
        <Typography.Title level={2} style={{ margin: 0 }}>Tickets</Typography.Title>
        <Button type="primary" icon={<PlusOutlined />} onClick={() => setShowForm(true)}>
          New ticket
        </Button>
      </div>

      <MyTicketStats user={user} />

      <Space wrap style={{ marginBottom: 16 }}>
        <Select value={scope} onChange={setScope} options={scopeOptions} style={{ width: 160 }} />
        <Select
          value={status}
          onChange={setStatus}
          style={{ width: 150 }}
          options={[{ value: '', label: 'Any status' }, ...STATUSES.map((s) => ({ value: s, label: label(s) }))]}
        />
        <Select
          value={priority}
          onChange={setPriority}
          style={{ width: 140 }}
          options={[{ value: '', label: 'Any priority' }, ...PRIORITIES.map((p) => ({ value: String(p), label: `P${p}` }))]}
        />
        <Button icon={<ReloadOutlined />} onClick={() => setRefreshCount(refreshCount + 1)}>
          Refresh
        </Button>
      </Space>

      <Alert error={error} />

      <Table
        rowKey="id"
        columns={columns}
        dataSource={tickets}
        loading={loading}
        pagination={{ pageSize: 15, hideOnSinglePage: true }}
        locale={{ emptyText: 'No tickets.' }}
        onRow={(ticket) => ({ onClick: () => onOpen(ticket.id) })}
        rowClassName="clickable-row"
      />

      <Modal
        title="New ticket"
        open={showForm}
        onCancel={() => setShowForm(false)}
        onOk={() => form.submit()}
        okText="File ticket"
        confirmLoading={saving}
        destroyOnHidden
      >
        <Form form={form} layout="vertical" onFinish={handleCreate} initialValues={{ priority: 3 }}>
          <Form.Item name="title" label="Title" rules={[{ required: true, message: 'Give the ticket a title' }]}>
            <Input maxLength={255} placeholder="Leaking pipe in the kitchen" />
          </Form.Item>
          <Form.Item name="description" label="Description">
            <Input.TextArea rows={3} maxLength={5000} placeholder="What is wrong, and anything the engineer should know" />
          </Form.Item>
          <Form.Item name="priority" label="Priority (1 = most urgent)">
            <Select options={PRIORITIES.map((p) => ({ value: p, label: `P${p}` }))} />
          </Form.Item>

          <Space align="start" wrap>
            <Form.Item name="buildingId" label="Building">
              <Select
                allowClear
                placeholder="No location"
                style={{ width: 180 }}
                options={buildingList.map((b) => ({ value: b.id, label: b.name }))}
                onChange={() => form.setFieldsValue({ floor: undefined, room: undefined })}
              />
            </Form.Item>
            <Form.Item
              name="floor"
              label="Floor"
              rules={[{ required: !!chosenBuilding, message: 'Choose a floor' }]}
            >
              <Select
                placeholder="Choose…"
                disabled={!chosenBuilding}
                style={{ width: 110 }}
                options={floorOptions(chosenBuilding)}
                onChange={() => form.setFieldsValue({ room: undefined })}
              />
            </Form.Item>
            <Form.Item name="room" label="Room (optional)">
              {roomCount > 0 ? (
                // The admin said how many rooms this floor has: pick one
                <Select allowClear placeholder="Choose…" style={{ width: 130 }}
                        options={range(roomCount).map((n) => ({ value: n, label: roomLabel(chosenBuilding, chosenFloor, n) }))} />
              ) : (
                <InputNumber min={1} disabled={!chosenBuilding} style={{ width: 130 }} />
              )}
            </Form.Item>
          </Space>

          {buildingList.length === 0 && (
            <p className="muted">No buildings defined yet. An admin can add them on the Buildings page.</p>
          )}
          <Alert error={formError} />
        </Form>
      </Modal>
    </div>
  )
}
