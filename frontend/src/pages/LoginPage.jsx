import { useState } from 'react'
import { users } from '../services/api'
import Alert from '../components/Alert'

// Only company addresses may sign up
const COMPANY_EMAIL_DOMAIN = '@acme.inc'

// Sign in, or create an account and then sign in with it.
export default function LoginPage({ onLogin }) {
  const [mode, setMode] = useState('login') // 'login' or 'signup'
  const [name, setName] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  async function handleSubmit(event) {
    event.preventDefault()
    setError('')

    // Same rule as the backend, checked here so the message shows before
    // the request is sent.
    if (mode === 'signup' && !email.trim().toLowerCase().endsWith(COMPANY_EMAIL_DOMAIN)) {
      setError(`Use your company email address (ending in ${COMPANY_EMAIL_DOMAIN})`)
      return
    }

    setBusy(true)
    try {
      if (mode === 'signup') {
        await users.signup(email, password, name)
      }
      const result = await users.login(email, password)
      onLogin(result.user, result.token, result.refreshToken)
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  function switchMode() {
    setMode(mode === 'login' ? 'signup' : 'login')
    setError('')
  }

  return (
    <div className="narrow">
      <h1>Incident Tracker</h1>
      <h2>{mode === 'login' ? 'Sign in' : 'Create account'}</h2>

      <form onSubmit={handleSubmit}>
        {mode === 'signup' && (
          <label>
            Name
            <input value={name} onChange={(e) => setName(e.target.value)} required />
          </label>
        )}
        <label>
          Email {mode === 'signup' && <span className="muted">(your {COMPANY_EMAIL_DOMAIN} address)</span>}
          <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} required />
        </label>
        <label>
          Password
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            minLength={mode === 'signup' ? 8 : undefined}
            required
          />
        </label>

        <Alert error={error} />

        <button type="submit" disabled={busy}>
          {mode === 'login' ? 'Sign in' : 'Create account'}
        </button>
      </form>

      <p>
        {mode === 'login' ? 'No account yet? ' : 'Already have an account? '}
        <button type="button" className="link" onClick={switchMode}>
          {mode === 'login' ? 'Create one' : 'Sign in'}
        </button>
      </p>
    </div>
  )
}
