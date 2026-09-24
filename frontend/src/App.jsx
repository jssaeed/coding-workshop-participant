import { useEffect, useState } from 'react'
import { Layout } from 'antd'
import { Navigate, Route, Routes, useLocation, useNavigate, useParams } from 'react-router-dom'
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

// How often to ask the server for the unread count (for the inbox bell),
// the number of approvals waiting (admins), and the signed-in user's
// current role (so a promotion shows up without signing out and back in).
const POLL_EVERY_MS = 30000

// Every page has a URL (after the #), so the browser's back and forward
// buttons work:
//   /            home            /tickets/12   one ticket
//   /tickets     ticket list     /inbox        inbox
//   /approvals   admin           /stats        admin
//   /users       admins          /buildings    admin

// The ticket page reads its id from the URL
function TicketRoute({ user, setUnread }) {
  const { id } = useParams()
  const navigate = useNavigate()
  return (
    <TicketPage
      key={id}
      id={Number(id)}
      user={user}
      onBack={() => navigate(-1)}
      setUnread={setUnread}
    />
  )
}

function App() {
  const navigate = useNavigate()
  const location = useLocation()

  // Who is signed in. Read from localStorage so a page refresh keeps you in.
  const [user, setUser] = useState(getToken() ? getStoredUser() : null)

  // Number shown on the inbox bell
  const [unread, setUnread] = useState(0)
  // Number of requests waiting for a facility admin (shown on the Approvals tab)
  const [pendingCount, setPendingCount] = useState(0)

  function handleLogin(loggedInUser, token, refreshToken) {
    saveSession(loggedInUser, token, refreshToken)
    setUser(loggedInUser)
    navigate('/')
  }

  function handleLogout() {
    // Tell the server to revoke the refresh token so it cannot be reused,
    // then forget the session locally either way.
    users.logout().catch(() => {})
    clearSession()
    setUser(null)
    setUnread(0)
    setPendingCount(0)
    navigate('/')
  }

  // The header highlights the section of the current URL
  const section = location.pathname.split('/')[1] || 'home'

  // Navigation from the header: a section name becomes a URL
  function goTo(key) {
    navigate(key === 'home' ? '/' : `/${key}`)
  }

  const openTicket = (id) => navigate(`/tickets/${id}`)

  // While signed in, every 30 seconds: refresh the counts, and check
  // whether the user's role has changed (an admin may have promoted them).
  useEffect(() => {
    if (!user) return

    function poll() {
      inbox.count().then((data) => setUnread(data.unread)).catch(() => {})
      if (isAdmin(user)) {
        // Only the total is needed, so ask for the smallest possible page
        incidents.list({ scope: 'pending', limit: 1 }).then((data) => setPendingCount(data.total)).catch(() => {})
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

  // Pages only some roles may open send everyone else home
  const adminOnly = (page) => (isAdmin(user) ? page : <Navigate to="/" replace />)

  return (
    <Layout className="app">
      <AppHeader
        user={user}
        page={section}
        unread={unread}
        pendingCount={pendingCount}
        onNavigate={goTo}
        onLogout={handleLogout}
      />
      <Content className="content">
        <div className="content-inner">
          {!user ? (
            <LoginPage onLogin={handleLogin} />
          ) : (
            <Routes>
              <Route path="/" element={<HomePage user={user} onNavigate={goTo} />} />
              <Route path="/tickets" element={<TicketsPage user={user} onOpen={openTicket} />} />
              <Route path="/tickets/:id" element={<TicketRoute user={user} setUnread={setUnread} />} />
              <Route path="/inbox" element={<InboxPage onOpen={openTicket} setUnread={setUnread} />} />
              <Route path="/approvals" element={adminOnly(<ApprovalsPage onOpen={openTicket} />)} />
              <Route path="/stats" element={adminOnly(<StatsPage />)} />
              <Route path="/buildings" element={adminOnly(<BuildingsPage user={user} />)} />
              <Route
                path="/users"
                element={canManageUsers(user) ? <UsersPage user={user} /> : <Navigate to="/" replace />}
              />
              <Route path="*" element={<Navigate to="/" replace />} />
            </Routes>
          )}
        </div>
      </Content>
      <AppFooter />
    </Layout>
  )
}

export default App
