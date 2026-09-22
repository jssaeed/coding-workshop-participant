import { useEffect, useState } from 'react'
import { clearSession, getStoredUser, getToken, inbox, saveSession } from './services/api'
import { isAdmin, label } from './services/format'
import LoginPage from './pages/LoginPage'
import TicketsPage from './pages/TicketsPage'
import TicketPage from './pages/TicketPage'
import InboxPage from './pages/InboxPage'
import UsersPage from './pages/UsersPage'
import './App.css'

// How often to ask the server for the unread count (for the Inbox badge)
const POLL_EVERY_MS = 30000

function App() {
  // Who is signed in. Read from localStorage so a page refresh keeps you in.
  const [user, setUser] = useState(getToken() ? getStoredUser() : null)

  // Which page is showing. For the ticket page, ticketId says which ticket.
  const [page, setPage] = useState('tickets')
  const [ticketId, setTicketId] = useState(null)

  // Number shown on the Inbox badge
  const [unread, setUnread] = useState(0)

  function handleLogin(loggedInUser, token) {
    saveSession(loggedInUser, token)
    setUser(loggedInUser)
    setPage('tickets')
  }

  function handleLogout() {
    clearSession()
    setUser(null)
    setUnread(0)
    setPage('tickets')
  }

  function openTicket(id) {
    setTicketId(id)
    setPage('ticket')
  }

  // While signed in, refresh the unread count every 30 seconds.
  useEffect(() => {
    if (!user) return

    function refreshUnread() {
      inbox.count().then((data) => setUnread(data.unread)).catch(() => {})
    }

    refreshUnread()
    const timer = setInterval(refreshUnread, POLL_EVERY_MS)
    return () => clearInterval(timer) // stop polling on sign out
  }, [user])

  if (!user) {
    return <LoginPage onLogin={handleLogin} />
  }

  return (
    <div className="app">
      <nav className="row space-between">
        <div className="row">
          <button type="button" className="link" onClick={() => setPage('tickets')}>
            Tickets
          </button>
          <button type="button" className="link" onClick={() => setPage('inbox')}>
            Inbox{unread > 0 && <span className="badge count">{unread}</span>}
          </button>
          {isAdmin(user) && (
            <button type="button" className="link" onClick={() => setPage('users')}>
              Users
            </button>
          )}
        </div>
        <div className="row">
          <span className="muted">{user.name} ({label(user.role)})</span>
          <button type="button" onClick={handleLogout}>Sign out</button>
        </div>
      </nav>

      <main>
        {page === 'tickets' && <TicketsPage user={user} onOpen={openTicket} />}
        {page === 'inbox' && <InboxPage onOpen={openTicket} setUnread={setUnread} />}
        {page === 'ticket' && (
          <TicketPage
            key={ticketId}
            id={ticketId}
            user={user}
            onBack={() => setPage('tickets')}
            setUnread={setUnread}
          />
        )}
        {page === 'users' && isAdmin(user) && <UsersPage user={user} />}
      </main>
    </div>
  )
}

export default App
