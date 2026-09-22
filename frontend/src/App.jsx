import { useCallback, useEffect, useState } from 'react'
import { clearSession, getStoredUser, getToken, inbox, saveSession } from './services/api'
import { isAdmin, label } from './services/format'
import LoginPage from './pages/LoginPage'
import TicketsPage from './pages/TicketsPage'
import TicketPage from './pages/TicketPage'
import UsersPage from './pages/UsersPage'
import InboxPage from './pages/InboxPage'
import './App.css'

// How often the nav badge asks the server for the unread total.
const INBOX_POLL_MS = 30_000

/**
 * Holds the session and switches between pages. Navigation is plain state
 * for now; a router can replace it when the UI is built out.
 */
function App() {
  const [session, setSession] = useState(() => {
    const token = getToken()
    const user = getStoredUser()
    return token && user ? { user, token } : null
  })
  const [route, setRoute] = useState({ page: 'tickets' })
  const [unread, setUnread] = useState(0)

  function handleLogin(user, token) {
    saveSession(user, token)
    setSession({ user, token })
    setRoute({ page: 'tickets' })
  }

  const handleLogout = useCallback(() => {
    clearSession()
    setSession(null)
    setUnread(0)
    setRoute({ page: 'tickets' })
  }, [])

  // An expired or invalid token means the session is over: sign out rather
  // than leaving every page showing the same 401.
  const handleApiError = useCallback(
    (err) => {
      if (err?.status === 401) handleLogout()
    },
    [handleLogout],
  )

  // Poll the unread count while signed in. Pages that learn the count as a
  // side effect (opening a ticket, loading the inbox) update it directly.
  useEffect(() => {
    if (!session) return undefined
    let cancelled = false
    const refresh = () =>
      inbox
        .count()
        .then((data) => {
          if (!cancelled) setUnread(data.unread)
        })
        .catch(handleApiError)
    refresh()
    const timer = setInterval(refresh, INBOX_POLL_MS)
    return () => {
      cancelled = true
      clearInterval(timer)
    }
  }, [session, handleApiError])

  if (!session) return <LoginPage onLogin={handleLogin} />

  const { user } = session
  const openTicket = (id) => setRoute({ page: 'ticket', id })

  return (
    <div className="app">
      <nav className="row space-between">
        <div className="row">
          <button type="button" className="link" onClick={() => setRoute({ page: 'tickets' })}>
            Tickets
          </button>
          <button type="button" className="link" onClick={() => setRoute({ page: 'inbox' })}>
            Inbox{unread > 0 && <span className="badge count">{unread}</span>}
          </button>
          {isAdmin(user) && (
            <button type="button" className="link" onClick={() => setRoute({ page: 'users' })}>
              Users
            </button>
          )}
        </div>
        <div className="row">
          <span className="muted">
            {user.name} ({label(user.role)})
          </span>
          <button type="button" onClick={handleLogout}>Sign out</button>
        </div>
      </nav>

      <main>
        {route.page === 'tickets' && (
          <TicketsPage user={user} onOpen={openTicket} onApiError={handleApiError} />
        )}
        {route.page === 'inbox' && (
          <InboxPage onOpen={openTicket} onCountChange={setUnread} onApiError={handleApiError} />
        )}
        {route.page === 'ticket' && (
          <TicketPage
            key={route.id}
            id={route.id}
            user={user}
            onBack={() => setRoute({ page: 'tickets' })}
            onApiError={handleApiError}
            onCountChange={setUnread}
          />
        )}
        {route.page === 'users' && isAdmin(user) && (
          <UsersPage user={user} onApiError={handleApiError} />
        )}
      </main>
    </div>
  )
}

export default App
