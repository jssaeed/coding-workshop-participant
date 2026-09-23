import { useEffect, useState } from 'react'
import { Button, Popconfirm, Select, Space, Table, Tag, Typography } from 'antd'
import { DeleteOutlined } from '@ant-design/icons'
import { users } from '../services/api'
import { ROLES, ROLE_ORDER, formatDate, label } from '../services/format'
import Alert from '../components/Alert'

// The ways the directory can be ordered. Each one is a compare function
// for Array.sort(): negative means a comes first, positive means b does.
const SORT_OPTIONS = [
  { value: 'name', label: 'Name (A–Z)', compare: (a, b) => a.name.localeCompare(b.name) },
  {
    value: 'role',
    label: 'Role',
    // Admins first, then engineers, then employees; by name within a role
    compare: (a, b) => ROLE_ORDER[a.role] - ROLE_ORDER[b.role] || a.name.localeCompare(b.name),
  },
  { value: 'newest', label: 'Newest accounts first', compare: (a, b) => new Date(b.createdAt) - new Date(a.createdAt) },
  { value: 'oldest', label: 'Oldest accounts first', compare: (a, b) => new Date(a.createdAt) - new Date(b.createdAt) },
]

// Admin only: every account, with a role dropdown and a delete button.
export default function UsersPage({ user }) {
  const [list, setList] = useState([])
  const [sortBy, setSortBy] = useState('name')
  const [roleFilter, setRoleFilter] = useState('') // '' means every role
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')
  const [refreshCount, setRefreshCount] = useState(0)

  useEffect(() => {
    async function load() {
      setLoading(true)
      try {
        setList(await users.list())
      } catch (err) {
        setError(err.message)
      } finally {
        setLoading(false)
      }
    }
    load()
  }, [refreshCount])

  async function changeRole(target, role) {
    setError('')
    setSuccess('')
    try {
      await users.updateRole(target.id, role)
      setSuccess(`${target.name} is now ${label(role)}.`)
    } catch (err) {
      setError(err.message)
    }
    setRefreshCount(refreshCount + 1) // reload either way, so the dropdown shows the real role
  }

  async function deleteUser(target) {
    setError('')
    setSuccess('')
    try {
      await users.remove(target.id)
      setSuccess(`${target.name} deleted.`)
      setRefreshCount(refreshCount + 1)
    } catch (err) {
      setError(err.message)
    }
  }

  // Filter, then sort, into a new list; the original stays as the server sent it
  const sortOption = SORT_OPTIONS.find((option) => option.value === sortBy)
  const shownList = list
    .filter((account) => roleFilter === '' || account.role === roleFilter)
    .sort(sortOption.compare)

  const columns = [
    {
      title: 'Name',
      dataIndex: 'name',
      render: (name, account) => (
        <span>{name} {account.id === user.id && <Tag>you</Tag>}</span>
      ),
    },
    { title: 'Email', dataIndex: 'email', responsive: ['md'] },
    {
      title: 'Role',
      dataIndex: 'role',
      render: (role, account) => (
        // You cannot change your own role
        <Select
          value={role}
          onChange={(value) => changeRole(account, value)}
          disabled={account.id === user.id}
          style={{ width: 160 }}
          options={ROLES.map((r) => ({ value: r, label: label(r) }))}
        />
      ),
    },
    { title: 'Joined', dataIndex: 'createdAt', render: formatDate, responsive: ['lg'] },
    {
      title: '',
      key: 'actions',
      width: 60,
      render: (_, account) => (
        // You cannot delete your own account
        <Popconfirm
          title={`Delete ${account.name}?`}
          description={account.email}
          okText="Delete"
          okButtonProps={{ danger: true }}
          onConfirm={() => deleteUser(account)}
          disabled={account.id === user.id}
        >
          <Button danger type="text" icon={<DeleteOutlined />} disabled={account.id === user.id} />
        </Popconfirm>
      ),
    },
  ]

  return (
    <div>
      <div className="page-title">
        <Typography.Title level={2} style={{ margin: 0 }}>
          Employee directory
          {user.branch && <span className="muted" style={{ fontSize: 16, fontWeight: 400 }}> · {user.branch.name}</span>}
        </Typography.Title>
        <Space wrap>
          <Select
            value={roleFilter}
            onChange={setRoleFilter}
            style={{ width: 160 }}
            options={[{ value: '', label: 'All roles' }, ...ROLES.map((r) => ({ value: r, label: label(r) }))]}
          />
          <span className="muted">Sort by</span>
          <Select
            value={sortBy}
            onChange={setSortBy}
            style={{ width: 200 }}
            options={SORT_OPTIONS.map(({ value, label: text }) => ({ value, label: text }))}
          />
        </Space>
      </div>
      <Alert error={error} success={success} />
      <Table
        rowKey="id"
        columns={columns}
        dataSource={shownList}
        loading={loading}
        pagination={false}
        locale={{ emptyText: roleFilter ? `${label(roleFilter)}: no accounts.` : 'No accounts.' }}
      />
    </div>
  )
}
