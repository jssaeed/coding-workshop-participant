import { useEffect, useRef, useState } from 'react'
import { Button, Input, Popconfirm, Select, Space, Table, Tag, Typography } from 'antd'
import { DeleteOutlined, SearchOutlined } from '@ant-design/icons'
import { users } from '../services/api'
import { BRANCH_ROLES, ROLES, formatDate, isDbAdmin, label } from '../services/format'
import useDebounce from '../hooks/useDebounce'
import Alert from '../components/Alert'

// The ways the directory can be ordered. Each maps to the API's
// ?sort= and ?order= (the server sorts, because it only sends one page).
const SORT_OPTIONS = [
  { value: 'name', label: 'Name (A–Z)', sort: 'name', order: 'asc' },
  { value: 'role', label: 'Role', sort: 'role', order: 'asc' }, // most senior first, then by name
  { value: 'newest', label: 'Newest accounts first', sort: 'created', order: 'desc' },
  { value: 'oldest', label: 'Oldest accounts first', sort: 'created', order: 'asc' },
]

const PAGE_SIZES = [10, 25, 50, 100]
const DEFAULT_PAGE_SIZE = 25

// Admin only: every account, with a role dropdown and a delete button.
// Filtering, searching, sorting and paging all happen on the server.
export default function UsersPage({ user }) {
  const [list, setList] = useState([]) // the page of accounts
  const [total, setTotal] = useState(0) // how many match in all
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(DEFAULT_PAGE_SIZE)
  const [sortBy, setSortBy] = useState('name')
  const [roleFilter, setRoleFilter] = useState('') // '' means every role
  const [branchFilter, setBranchFilter] = useState('') // '' means every branch (db admin only)
  const [branches, setBranches] = useState([]) // for the db admin's branch filter
  const [search, setSearch] = useState('') // name or email
  const query = useDebounce(search.trim()) // sent once typing pauses
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')
  const [refreshCount, setRefreshCount] = useState(0)

  // The db admin sees every branch, so they can narrow the list to one
  useEffect(() => {
    if (isDbAdmin(user)) users.branches().then(setBranches).catch(() => {})
  }, [user])

  // Load the page whenever a filter, the order, the page or a change to an
  // account asks for it. A changed filter starts again from page 1.
  const sortOption = SORT_OPTIONS.find((option) => option.value === sortBy)
  const filterKey = JSON.stringify([roleFilter, branchFilter, query, sortBy])
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
      try {
        const data = await users.list({
          role: roleFilter, branchId: branchFilter, q: query,
          sort: sortOption.sort, order: sortOption.order, page, limit: pageSize,
        })
        setList(data.items)
        setTotal(data.total)
      } catch (err) {
        setError(err.message)
      } finally {
        setLoading(false)
      }
    }
    load()
  }, [filterKey, roleFilter, branchFilter, query, sortOption, page, pageSize, refreshCount])

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
      // Deleting the last account on a page moves us to the one before it
      if (list.length === 1 && page > 1) setPage(page - 1)
      setRefreshCount(refreshCount + 1)
    } catch (err) {
      setError(err.message)
    }
  }

  const branchOptions = branches.map((b) => ({ value: b.id, label: b.name }))

  const columns = [
    {
      title: 'Name',
      dataIndex: 'name',
      render: (name, account) => (
        <span>{name} {account.id === user.id && <Tag>you</Tag>}</span>
      ),
    },
    { title: 'Email', dataIndex: 'email', responsive: ['md'] },
    // The db admin sees every branch, so show which one each person is at
    ...(isDbAdmin(user) ? [{ title: 'Branch', dataIndex: ['branch', 'name'], responsive: ['md'] }] : []),
    {
      title: 'Role',
      dataIndex: 'role',
      render: (role, account) => (
        // You cannot change your own role. A facility admin cannot touch a db
        // admin's account or hand out the db admin role.
        <Select
          value={role}
          onChange={(value) => changeRole(account, value)}
          disabled={account.id === user.id || (!isDbAdmin(user) && account.role === 'db_admin')}
          style={{ width: 160 }}
          options={(isDbAdmin(user) ? ROLES : BRANCH_ROLES).map((r) => ({ value: r, label: label(r) }))}
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
          <Button danger type="text" icon={<DeleteOutlined />} disabled={account.id === user.id || (!isDbAdmin(user) && account.role === 'db_admin')} />
        </Popconfirm>
      ),
    },
  ]

  const filtered = roleFilter || branchFilter || query

  return (
    <div>
      <div className="page-title">
        <Typography.Title level={2} style={{ margin: 0 }}>
          Employee directory
          <span className="muted" style={{ fontSize: 16, fontWeight: 400 }}> · {isDbAdmin(user) ? 'All branches' : user.branch?.name}</span>
        </Typography.Title>
        <Space wrap>
          <Input
            allowClear
            prefix={<SearchOutlined />}
            placeholder="Search name or email"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            style={{ width: 220 }}
          />
          {isDbAdmin(user) && (
            <Select
              value={branchFilter}
              onChange={setBranchFilter}
              style={{ width: 200 }}
              options={[{ value: '', label: 'All branches' }, ...branchOptions]}
            />
          )}
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
        dataSource={list}
        loading={loading}
        onChange={(pagination) => {
          setPage(pagination.current)
          setPageSize(pagination.pageSize)
        }}
        pagination={{
          current: page,
          pageSize,
          total,
          showSizeChanger: true,
          pageSizeOptions: PAGE_SIZES,
          hideOnSinglePage: total <= PAGE_SIZES[0],
          showTotal: (count, [from, to]) => `${from}–${to} of ${count}`,
        }}
        locale={{ emptyText: filtered ? 'No accounts match these filters.' : 'No accounts.' }}
      />
    </div>
  )
}
