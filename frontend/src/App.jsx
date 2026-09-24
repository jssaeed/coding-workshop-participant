import { useEffect, useState } from 'react'
import { Layout } from 'antd'
import { clearSession, getStoredUser, getToken, inbox, incidents, saveSession, users } from './services/api'
import { canManageUsers, isAdmin } from './services/format'
import AppHeader from './components/AppHeader'
import AppFooter from './components/AppFooter'
import LoginPage from './pages/LoginPage'
import HomePage from './pages/HomePage'
import TicketsPage from './pages/TicketsPage'
import TicketPage from './pages/TicketPage'
import InboxPage from './pages/InboxPage'
import UsersPage from './pages/UsersPage'
import BuildingsPage from './pages/BuildingsPage'
import StatsPage from './pages/StatsPage'
import ApprovalsPage from './pages/ApprovalsPage'
import './App.css'

const { Content } = Layout

// How often to ask the server for the unread count (for the inbox bell)
// and for the signed-in user's current role (so a promotion shows up
// without signing out and back in).
const POLL_EVERY_MS = 30000

function App() {
  // Who is signed in. Read from localStorage so a page refresh keeps you in.
  const [user, setUser] = useState(getToken() ? getStoredUser() : null)

  // Which page is showing. For the ticket page, ticketId says which ticket.
  const [page, setPage] = useState('home')
  const [ticketId, setTicketId] = useState(null)

  // Number shown on the inbox bell
  const [unread, setUnread] = useState(0)
  // Number of requests waiting for a facility admin (shown on the Approvals tab)
  const [pendingCount, setPendingCount] = useState(0)

  function handleLogin(loggedInUser, token, refreshToken) {
    saveSession(loggedInUser, token, refreshToken)
    setUser(loggedInUser)
    setPage('home')
  }

  function handleLogout() {
    // Tell the server to revoke the refresh token so it cannot be reused,
    // then forget the session locally either way.
    users.logout().catch(() => {})
    clearSession()
    setUser(null)
    setUnread(0)
    setPage('home')
  }

  function openTicket(id) {
    setTicketId(id)
    setPage('ticket')
  }

  // While signed in, every 30 seconds: refresh the unread count, and check
  // whether the user's role has changed (an admin may have promoted them).
  useEffect(() => {
    if (!user) return

    function poll() {
      inbox.count().then((data) => setUnread(data.unread)).catch(() => {})
      if (isAdmin(user)) {
        incidents.list({ scope: 'pending' }).then((list) => setPendingCount(list.length)).catch(() => {})
      }

      users.me().then((current) => {
        if (current.role !== user.role || current.name !== user.name) {
          saveSession(current, getToken())
          setUser(current)
        }
      }).catch(() => {})
    }

    poll()
    const timer = setInterval(poll, POLL_EVERY_MS)
    return () => clearInterval(timer) // stop polling on sign out
  }, [user])

  // The page currently showing. Admin pages fall back to home for other roles.
  function renderPage() {
    if (!user) return <LoginPage onLogin={handleLogin} />

    switch (page) {
      case 'tickets':
        return <TicketsPage user={user} onOpen={openTicket} />
      case 'inbox':
        return <InboxPage onOpen={openTicket} setUnread={setUnread} />
      case 'ticket':
        return (
          <TicketPage
            key={ticketId}
            id={ticketId}
            user={user}
            onBack={() => setPage('tickets')}
            setUnread={setUnread}
          />
        )
      case 'stats':
        return isAdmin(user) ? <StatsPage /> : <HomePage user={user} onNavigate={setPage} />
      case 'approvals':
        return isAdmin(user) ? <ApprovalsPage onOpen={openTicket} /> : <HomePage user={user} onNavigate={setPage} />
      case 'users':
        return canManageUsers(user) ? <UsersPage user={user} /> : <HomePage user={user} onNavigate={setPage} />
      case 'buildings':
        return isAdmin(user) ? <BuildingsPage user={user} /> : <HomePage user={user} onNavigate={setPage} />
      default:
        return <HomePage user={user} onNavigate={setPage} />
    }
  }

  return (
    <Layout className="app">
      <AppHeader
        user={user}
        page={page}
        unread={unread}
        pendingCount={pendingCount}
        onNavigate={setPage}
        onLogout={handleLogout}
      />
      <Content className="content">
        <div className="content-inner">{renderPage()}</div>
      </Content>
      <AppFooter />
    </Layout>
  )
}

export default App
