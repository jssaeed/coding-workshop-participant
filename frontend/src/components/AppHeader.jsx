import { Avatar, Badge, Button, Dropdown, Layout, Menu, Space, Typography } from 'antd'
import { BellOutlined, LogoutOutlined, UserOutlined } from '@ant-design/icons'
import { initial, isAdmin, label } from '../services/format'

const { Header } = Layout

// The bar at the top of every page: the ACME Inc brand on the left, the
// page menu in the middle, and the inbox bell + account avatar on the right.
// When nobody is signed in only the brand shows.
export default function AppHeader({ user, page, unread, onNavigate, onLogout }) {
  const menuItems = [
    { key: 'home', label: 'Home' },
    { key: 'tickets', label: 'Tickets' },
  ]
  if (user && isAdmin(user)) {
    menuItems.push({ key: 'stats', label: 'Statistics' })
    menuItems.push({ key: 'users', label: 'Employee directory' })
    menuItems.push({ key: 'buildings', label: 'Buildings' })
  }

  // The dropdown under the avatar: who you are, and Sign out.
  const accountMenu = {
    items: [
      {
        key: 'who',
        disabled: true,
        label: (
          <div>
            <strong>{user?.name}</strong>
            <br />
            <span className="muted">{user?.email}</span>
            <br />
            <span className="muted">{label(user?.role)}{user?.branch && ` · ${user.branch.name}`}</span>
          </div>
        ),
      },
      { type: 'divider' },
      { key: 'logout', icon: <LogoutOutlined />, label: 'Sign out', onClick: onLogout },
    ],
  }

  return (
    <Header className="header">
      <div className="header-inner">
        <button type="button" className="brand" onClick={() => onNavigate('home')}>
          <img src="/acme.svg" alt="" width="28" height="28" />
          <span>
            <Typography.Text strong className="brand-name">ACME Inc</Typography.Text>
            <Typography.Text className="brand-sub">Facilities Incident Tracker</Typography.Text>
          </span>
        </button>

        {user && (
          <>
            <Menu
              mode="horizontal"
              selectedKeys={[page === 'ticket' ? 'tickets' : page]}
              items={menuItems}
              onClick={(item) => onNavigate(item.key)}
              className="header-menu"
            />

            <Space size="middle" className="header-right">
              <Badge count={unread} size="small" offset={[-2, 4]}>
                <Button
                  type="text"
                  shape="circle"
                  icon={<BellOutlined />}
                  aria-label="Inbox"
                  title="Inbox"
                  className="header-icon"
                  onClick={() => onNavigate('inbox')}
                />
              </Badge>
              <Dropdown menu={accountMenu} placement="bottomRight" trigger={['click']}>
                <button type="button" className="avatar-button" aria-label="Account">
                  <Avatar size="small" style={{ backgroundColor: '#1e3a5f', fontWeight: 500 }}>
                    {initial(user.name) || <UserOutlined />}
                  </Avatar>
                  <span className="avatar-name">{user.name}</span>
                </button>
              </Dropdown>
            </Space>
          </>
        )}
      </div>
    </Header>
  )
}
