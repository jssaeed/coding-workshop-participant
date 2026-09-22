import { useCallback, useState } from 'react'
import { clearSession, getStoredUser, getToken, saveSession } from './services/api'
import { isAdmin, label } from './services/format'
import LoginPage from './pages/LoginPage'
import TicketsPage from './pages/TicketsPage'
import TicketPage from './pages/TicketPage'
import UsersPage from './pages/UsersPage'
import './App.css'

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

  function handleLogin(user, token) {
    saveSession(user, token)
    setSession({ user, token })
    setRoute({ page: 'tickets' })
  }

  const handleLogout = useCallback(() => {
    clearSession()
    setSession(null)
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

  if (!session) return <LoginPage onLogin={handleLogin} />

  const { user } = session

  return (
    <div className="app">
      <nav className="row space-between">
        <div className="row">
          <button type="button" className="link" onClick={() => setRoute({ page: 'tickets' })}>
            Tickets
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
          <TicketsPage
            user={user}
            onOpen={(id) => setRoute({ page: 'ticket', id })}
            onApiError={handleApiError}
          />
        )}
        {route.page === 'ticket' && (
          <TicketPage
            key={route.id}
            id={route.id}
            user={user}
            onBack={() => setRoute({ page: 'tickets' })}
            onApiError={handleApiError}
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
