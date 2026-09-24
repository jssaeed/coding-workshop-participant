import { useEffect, useState } from 'react'
import { Button, Checkbox, Form, Input, InputNumber, Modal, Popconfirm, Space, Table, Typography } from 'antd'
import { DeleteOutlined, EditOutlined, PlusOutlined, SearchOutlined } from '@ant-design/icons'
import { buildings } from '../services/api'
import { floorLabel, matchesSearch } from '../services/format'
import Alert from '../components/Alert'

const MAX_FLOORS = 200
const MAX_BASEMENT_FLOORS = 20
const MAX_ROOMS = 500

// Every floor of a building in display order: top floor down to 1, then B1..Bm
function floorNumbers(floors, basementFloors) {
  const list = []
  for (let f = floors; f >= 1; f--) list.push(f)
  for (let b = 1; b <= basementFloors; b++) list.push(-b)
  return list
}

// "10 on every floor", "varies (0–12)" or "not set", plus how they are numbered
function roomsSummary(building) {
  const counts = building.rooms.map((f) => f.rooms)
  let text
  if (counts.length === 0 || counts.every((c) => c === 0)) text = 'not set'
  else {
    const min = Math.min(...counts)
    const max = Math.max(...counts)
    text = min === max ? `${min} on every floor` : `varies (${min}–${max})`
  }
  if (building.roomNumbersIncludeFloor) text += ' · numbered by floor'
  return text
}

// Admin only: the branch's buildings, with a dialog to add or edit one.
export default function BuildingsPage({ user }) {
  const [list, setList] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')
  const [refreshCount, setRefreshCount] = useState(0)
  const [search, setSearch] = useState('')

  // The add/edit dialog. editing is the building being edited, or null for "add".
  const [dialogOpen, setDialogOpen] = useState(false)
  const [editing, setEditing] = useState(null)
  const [form] = Form.useForm()
  const [saving, setSaving] = useState(false)
  const [dialogError, setDialogError] = useState('')

  // Rooms per floor. perFloor is {floor: rooms} once the admin has opened
  // the per-floor dialog and chosen to set floors individually; otherwise
  // the single "rooms on each floor" number applies to every floor.
  const [perFloor, setPerFloor] = useState(null)
  const [perFloorOpen, setPerFloorOpen] = useState(false)

  // Hooks must run on every render, so watch every field unconditionally
  // and only then work out the values.
  const hasBasement = Form.useWatch('hasBasement', form)
  const watchedFloors = Form.useWatch('floors', form)
  const watchedBasementFloors = Form.useWatch('basementFloors', form)
  const roomsPerFloor = Form.useWatch('roomsPerFloor', form)
  const floors = watchedFloors || 1
  const basementFloors = hasBasement ? watchedBasementFloors || 1 : 0

  useEffect(() => {
    async function load() {
      setLoading(true)
      try {
        setList(await buildings.list())
      } catch (err) {
        setError(err.message)
      } finally {
        setLoading(false)
      }
    }
    load()
  }, [refreshCount])

  function openAdd() {
    setEditing(null)
    setPerFloor(null)
    setDialogError('')
    form.setFieldsValue({ name: '', floors: 1, hasBasement: false, basementFloors: 1, roomsPerFloor: undefined, roomNumbersIncludeFloor: false })
    setDialogOpen(true)
  }

  function openEdit(building) {
    setEditing(building)
    setDialogError('')
    const counts = building.rooms.map((f) => f.rooms)
    const uniform = counts.length > 0 && counts.every((c) => c === counts[0])
    // A building whose floors differ starts in per-floor mode
    setPerFloor(uniform ? null : Object.fromEntries(building.rooms.map((f) => [f.floor, f.rooms])))
    form.setFieldsValue({
      name: building.name,
      floors: building.floors,
      hasBasement: building.basementFloors > 0,
      basementFloors: building.basementFloors || 1,
      roomsPerFloor: uniform ? counts[0] : undefined,
      roomNumbersIncludeFloor: building.roomNumbersIncludeFloor,
    })
    setDialogOpen(true)
  }

  // Open the per-floor dialog, starting from the single number if set
  function openPerFloor() {
    const start = {}
    for (const f of floorNumbers(floors, basementFloors)) {
      start[f] = perFloor?.[f] ?? roomsPerFloor ?? 0
    }
    setPerFloor(start)
    setPerFloorOpen(true)
  }

  async function handleSave(values) {
    setDialogError('')
    setSaving(true)
    const payload = {
      name: values.name,
      floors: values.floors,
      basementFloors: values.hasBasement ? values.basementFloors : 0,
      roomNumbersIncludeFloor: !!values.roomNumbersIncludeFloor,
    }
    if (perFloor) {
      payload.rooms = floorNumbers(payload.floors, payload.basementFloors)
        .map((f) => ({ floor: f, rooms: perFloor[f] ?? values.roomsPerFloor ?? 0 }))
    } else if (values.roomsPerFloor !== undefined && values.roomsPerFloor !== null) {
      payload.roomsPerFloor = values.roomsPerFloor
    }
    try {
      if (editing) {
        await buildings.update(editing.id, payload)
        setSuccess(`${values.name} updated.`)
      } else {
        await buildings.create(payload)
        setSuccess(`${values.name} added.`)
      }
      setDialogOpen(false)
      setRefreshCount(refreshCount + 1)
    } catch (err) {
      setDialogError(err.message)
    } finally {
      setSaving(false)
    }
  }

  async function remove(building) {
    setError('')
    setSuccess('')
    try {
      await buildings.remove(building.id)
      setSuccess(`${building.name} deleted.`)
      setRefreshCount(refreshCount + 1)
    } catch (err) {
      setError(err.message)
    }
  }

  const columns = [
    { title: 'Name', dataIndex: 'name', sorter: (a, b) => a.name.localeCompare(b.name) },
    {
      title: 'Floors',
      sorter: (a, b) => a.floors - b.floors,
      key: 'floors',
      render: (_, b) => (b.basementFloors ? `${b.floors} above, ${b.basementFloors} below` : `${b.floors}`),
    },
    { title: 'Rooms', key: 'rooms', render: (_, b) => roomsSummary(b), responsive: ['md'] },
    {
      title: '',
      key: 'actions',
      width: 100,
      render: (_, building) => (
        <Space>
          <Button type="text" icon={<EditOutlined />} onClick={() => openEdit(building)} aria-label="Edit" />
          <Popconfirm
            title={`Delete ${building.name}?`}
            okText="Delete"
            okButtonProps={{ danger: true }}
            onConfirm={() => remove(building)}
          >
            <Button danger type="text" icon={<DeleteOutlined />} aria-label="Delete" />
          </Popconfirm>
        </Space>
      ),
    },
  ]

  return (
    <div>
      <div className="page-title">
        <Typography.Title level={2} style={{ margin: 0 }}>
          Buildings
          {user?.branch && <span className="muted" style={{ fontSize: 16, fontWeight: 400 }}> · {user.branch.name}</span>}
        </Typography.Title>
        <Space wrap>
          <Input
            allowClear
            prefix={<SearchOutlined />}
            placeholder="Search buildings"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            style={{ width: 200 }}
          />
          <Button type="primary" icon={<PlusOutlined />} onClick={openAdd}>Add building</Button>
        </Space>
      </div>

      <Alert error={error} success={success} />

      <Table
        rowKey="id"
        columns={columns}
        dataSource={list.filter((b) => matchesSearch(b.name, search))}
        loading={loading}
        pagination={false}
        locale={{ emptyText: search ? 'No buildings match your search.' : 'No buildings yet.' }}
      />

      <Modal
        title={editing ? `Edit ${editing.name}` : 'Add a building'}
        open={dialogOpen}
        onCancel={() => setDialogOpen(false)}
        onOk={() => form.submit()}
        okText={editing ? 'Save' : 'Add'}
        confirmLoading={saving}
      >
        <Form form={form} layout="vertical" onFinish={handleSave}>
          <Form.Item name="name" label="Name" rules={[{ required: true, message: 'Enter a name' }]}>
            <Input placeholder="HQ" />
          </Form.Item>
          <Space align="start" wrap>
            <Form.Item name="floors" label="Floors above ground" rules={[{ required: true, message: 'How many floors?' }]}>
              <InputNumber min={1} max={MAX_FLOORS} />
            </Form.Item>
            <Form.Item name="hasBasement" valuePropName="checked" label=" ">
              <Checkbox>Has basement floors</Checkbox>
            </Form.Item>
            {hasBasement && (
              <Form.Item name="basementFloors" label="Basement floors">
                <InputNumber min={1} max={MAX_BASEMENT_FLOORS} />
              </Form.Item>
            )}
          </Space>
          <Space align="end" wrap>
            <Form.Item name="roomsPerFloor" label="Rooms on each floor" extra={perFloor ? 'Set per floor below' : 'Leave empty for any room number'}>
              <InputNumber min={0} max={MAX_ROOMS} disabled={!!perFloor} placeholder="—" />
            </Form.Item>
            <Form.Item label=" ">
              <Space>
                <Button onClick={openPerFloor}>Set per floor…</Button>
                {perFloor && <Button type="link" onClick={() => setPerFloor(null)}>Use one number</Button>}
              </Space>
            </Form.Item>
          </Space>
          <Form.Item
            name="roomNumbersIncludeFloor"
            valuePropName="checked"
            extra="Room 1 on floor 5 is shown as 501, or 5001 once any floor has 100 or more rooms"
          >
            <Checkbox>Rooms start with floor number?</Checkbox>
          </Form.Item>
          <Alert error={dialogError} />
        </Form>
      </Modal>

      <Modal
        title="Rooms per floor"
        open={perFloorOpen}
        onCancel={() => setPerFloorOpen(false)}
        onOk={() => setPerFloorOpen(false)}
        okText="Done"
      >
        <p className="muted">0 means the number of rooms is not set for that floor.</p>
        <div className="per-floor">
          {perFloor && floorNumbers(floors, basementFloors).map((f) => (
            <label key={f} className="per-floor-row">
              <span>Floor {floorLabel(f)}</span>
              <InputNumber
                min={0}
                max={MAX_ROOMS}
                value={perFloor[f] ?? 0}
                onChange={(value) => setPerFloor({ ...perFloor, [f]: value ?? 0 })}
              />
            </label>
          ))}
        </div>
      </Modal>
    </div>
  )
}
