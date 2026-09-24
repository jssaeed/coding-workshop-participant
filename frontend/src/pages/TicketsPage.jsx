import { useEffect, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { Button, Form, Input, InputNumber, Modal, Select, Space, Table, Tag, Typography } from 'antd'
import { PlusOutlined, ReloadOutlined, SearchOutlined } from '@ant-design/icons'
import { buildings, incidents } from '../services/api'
import {
  CATEGORIES, DEFAULT_CATEGORY, PRIORITIES, PRIORITY_COLORS, STATUSES, STATUS_COLORS,
  categoryLabel, defaultTicketScopeFor, floorOptions, formatDate, formatLocation, isAdmin, isStaff, label, personName, range, roomLabel, roomsOnFloor,
} from '../services/format'
import { DEFAULT_DAYS, RANGES } from '../components/charts/shared'
import useDebounce from '../hooks/useDebounce'
import Alert from '../components/Alert'
import MyTicketStats from '../components/MyTicketStats'

// The ticket list, with filters and a dialog to file a new ticket.
//
// The server does the filtering, searching, sorting and paging (see
// GET /api/incidents in backend/API.md): the page only ever holds the rows
// it shows, so the list stays fast however many tickets there are.

const PAGE_SIZES = [10, 25, 50, 100]
const DEFAULT_PAGE_SIZE = 25
// Table column key -> the API's ?sort= value
const SORT_KEYS = { id: 'id', title: 'title', priority: 'priority', location: 'location', createdAt: 'created' }
const DEFAULT_SORTING = { sort: 'priority', order: 'asc' } // most urgent first, then newest

export default function TicketsPage({ user, onOpen }) {
  // Which "Show" options this user gets
  const scopeOptions = [{ value: 'mine', label: 'My tickets' }]
  if (isStaff(user)) scopeOptions.push({ value: 'assigned', label: 'Assigned to me' })
  if (isAdmin(user)) {
    scopeOptions.push({ value: 'unassigned', label: 'Unassigned' }, { value: 'pending', label: 'Awaiting approval' }, { value: 'all', label: 'All tickets' })
  }

  // Filters. The Statistics page links here with filters in the URL
  // (/tickets?scope=all&status=open), so each one starts from the URL when
  // it is given there and from its default otherwise.
  const [params] = useSearchParams()
  const urlScope = params.get('scope')
  const [scope, setScope] = useState(
    scopeOptions.some((option) => option.value === urlScope) ? urlScope : defaultTicketScopeFor(user), // 'mine', 'assigned' or 'all' by role
  )
  // Several statuses may be chosen; a ticket in any of them is shown
  const [statuses, setStatuses] = useState(params.get('status') ? params.get('status').split(',') : [])
  const [priority, setPriority] = useState(params.get('priority') || '')
  const [category, setCategory] = useState(params.get('category') || '') // plumbing, electrical, ... ('' = any)
  const [days, setDays] = useState(Number(params.get('days')) || DEFAULT_DAYS) // only tickets created in the last N days
  const [buildingId, setBuildingId] = useState(Number(params.get('buildingId')) || '') // only tickets in this building ('' = any)
  const [floor, setFloor] = useState(params.has('floor') ? Number(params.get('floor')) : '') // ...and on this floor of it ('' = any)
  const [search, setSearch] = useState(params.get('q') || '') // matched against id, title, description, people, building
  const query = useDebounce(search.trim()) // sent once typing pauses

  // Which page, how big, and in what order
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(DEFAULT_PAGE_SIZE)
  const [sorting, setSorting] = useState(DEFAULT_SORTING)

  // The page of tickets, and how many match in all
  const [tickets, setTickets] = useState([])
  const [total, setTotal] = useState(0)
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

  // Load the page whenever a filter, the order, the page or Refresh changes.
  // A changed filter or search starts again from page 1 (one request, not
  // one for the old page and one for the first).
  const filterKey = JSON.stringify([scope, statuses, priority, category, days, buildingId, floor, query])
  const lastFilterKey = useRef(filterKey)
  useEffect(() => {
    if (lastFilterKey.current !== filterKey) {
      lastFilterKey.current = filterKey
      if (page !== 1) {
        setPage(1) // runs this effect again, on page 1
        return
      }
    }

    async function load() {
      setLoading(true)
      setError('')
      try {
        const data = await incidents.list({
          scope, status: statuses.join(','), priority, category, days, buildingId, floor, q: query, sort: sorting.sort, order: sorting.order, page, limit: pageSize,
        })
        setTickets(data.items)
        setTotal(data.total)
      } catch (err) {
        setError(err.message)
      } finally {
        setLoading(false)
      }
    }
    load()
  }, [filterKey, scope, statuses, priority, category, days, buildingId, floor, query, sorting, page, pageSize, refreshCount])

  // The table tells us about a page turn, a page size or a column sort
  function handleTableChange(pagination, _filters, sorter) {
    setPage(pagination.current)
    setPageSize(pagination.pageSize)
    if (sorter && sorter.order) {
      setSorting({ sort: SORT_KEYS[sorter.columnKey], order: sorter.order === 'ascend' ? 'asc' : 'desc' })
    } else {
      setSorting(DEFAULT_SORTING) // the sort was cleared
    }
  }

  // Which way the arrow on a sortable column points
  function sortOrderFor(key) {
    if (SORT_KEYS[key] !== sorting.sort) return null
    return sorting.order === 'asc' ? 'ascend' : 'descend'
  }

  async function handleCreate(values) {
    setFormError('')
    setSaving(true)
    try {
      const ticket = { title: values.title, description: values.description, priority: values.priority, category: values.category }
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

  // The building picked in the filters, so the floor filter can list its floors.
  // Picking another building drops the floor: its floors are different.
  const filterBuilding = buildingList.find((b) => b.id === buildingId)
  function handleBuildingFilter(value) {
    setBuildingId(value)
    setFloor('')
  }

  const columns = [
    { title: '#', key: 'id', dataIndex: 'id', width: 70, sorter: true, sortOrder: sortOrderFor('id') },
    { title: 'Title', key: 'title', dataIndex: 'title', ellipsis: true, sorter: true, sortOrder: sortOrderFor('title') },
    {
      title: 'Status',
      key: 'status',
      dataIndex: 'status',
      render: (value, ticket) => (
        <>
          <Tag color={STATUS_COLORS[value]}>{label(value)}</Tag>
          {ticket.pendingApproval && <Tag>→ {label(ticket.pendingApproval.status)}?</Tag>}
        </>
      ),
    },
    {
      title: 'Priority',
      key: 'priority',
      dataIndex: 'priority',
      width: 100,
      sorter: true,
      sortOrder: sortOrderFor('priority'),
      render: (value) => <Tag color={PRIORITY_COLORS[value]}>P{value}</Tag>,
    },
    { title: 'Category', key: 'category', dataIndex: 'category', render: categoryLabel, responsive: ['md'] },
    { title: 'Location', key: 'location', dataIndex: 'location', render: formatLocation, responsive: ['md'], sorter: true, sortOrder: sortOrderFor('location') },
    { title: 'Reported by', key: 'reportedBy', dataIndex: 'reportedBy', render: personName, responsive: ['lg'] },
    { title: 'Assigned to', key: 'assignedTo', dataIndex: ['assignedTo', 'name'], render: (v) => v || '—', responsive: ['lg'] },
    { title: 'Created', key: 'createdAt', dataIndex: 'createdAt', render: formatDate, responsive: ['md'], sorter: true, sortOrder: sortOrderFor('createdAt') },
  ]

  return (
    <div>
      <div className="page-title">
        <Typography.Title level={2} style={{ margin: 0 }}>
          Tickets
          {/* An admin's queue is their branch's queue, so say which one */}
          {isAdmin(user) && user.branch && <span className="muted" style={{ fontSize: 16, fontWeight: 400 }}> · {user.branch.name}</span>}
        </Typography.Title>
        <Button type="primary" icon={<PlusOutlined />} onClick={() => setShowForm(true)}>
          New ticket
        </Button>
      </div>

      <MyTicketStats user={user} />

      <Space wrap style={{ marginBottom: 16 }}>
        <Select value={scope} onChange={setScope} options={scopeOptions} style={{ width: 160 }} />
        <Select
          mode="multiple"
          allowClear
          placeholder="Any status"
          maxTagCount={2}
          value={statuses}
          onChange={setStatuses}
          style={{ minWidth: 150, maxWidth: 320 }}
          options={STATUSES.map((s) => ({ value: s, label: label(s) }))}
        />
        <Select
          value={priority}
          onChange={setPriority}
          style={{ width: 140 }}
          options={[{ value: '', label: 'Any priority' }, ...PRIORITIES.map((p) => ({ value: String(p), label: `P${p}` }))]}
        />
        <Select
          value={category}
          onChange={setCategory}
          style={{ width: 150 }}
          options={[{ value: '', label: 'Any category' }, ...CATEGORIES.map((c) => ({ value: c, label: categoryLabel(c) }))]}
        />
        <Select
          value={buildingId}
          onChange={handleBuildingFilter}
          style={{ width: 160 }}
          options={[{ value: '', label: 'Any building' }, ...buildingList.map((b) => ({ value: b.id, label: b.name }))]}
        />
        <Select
          value={floor}
          onChange={setFloor}
          disabled={!filterBuilding}
          style={{ width: 110 }}
          options={[{ value: '', label: 'Any floor' }, ...floorOptions(filterBuilding)]}
        />
        <Select
          value={days}
          onChange={setDays}
          style={{ width: 140 }}
          options={RANGES} // the same ranges as the Statistics page, so its links carry over
        />
        <Input
          allowClear
          prefix={<SearchOutlined />}
          placeholder="Search tickets"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          style={{ width: 220 }}
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
        onChange={handleTableChange}
        pagination={{
          position: ['topRight'], // the page picker sits above the table
          current: page,
          pageSize,
          total,
          showSizeChanger: true,
          pageSizeOptions: PAGE_SIZES,
          hideOnSinglePage: total <= PAGE_SIZES[0],
          showTotal: (count, [from, to]) => `${from}–${to} of ${count}`,
        }}
        locale={{ emptyText: query ? 'No tickets match your search.' : `No tickets in the last ${days} days.` }}
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
        <Form form={form} layout="vertical" onFinish={handleCreate} initialValues={{ priority: 3, category: DEFAULT_CATEGORY }}>
          <Form.Item name="title" label="Title" rules={[{ required: true, message: 'Give the ticket a title' }]}>
            <Input maxLength={255} placeholder="Leaking pipe in the kitchen" />
          </Form.Item>
          <Form.Item name="description" label="Description">
            <Input.TextArea rows={3} maxLength={5000} placeholder="What is wrong, and anything the engineer should know" />
          </Form.Item>
          <Form.Item name="priority" label="Priority (1 = most urgent)">
            <Select options={PRIORITIES.map((p) => ({ value: p, label: `P${p}` }))} />
          </Form.Item>
          <Form.Item name="category" label="Category">
            <Select options={CATEGORIES.map((c) => ({ value: c, label: categoryLabel(c) }))} />
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
