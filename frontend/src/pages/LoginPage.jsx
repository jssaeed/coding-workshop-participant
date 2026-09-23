import { useEffect, useState } from 'react'
import { Button, Card, Form, Input, Segmented, Select, Typography } from 'antd'
import { EnvironmentOutlined, LockOutlined, MailOutlined, UserOutlined } from '@ant-design/icons'
import { users } from '../services/api'
import Alert from '../components/Alert'

// Only company addresses may sign up
const COMPANY_EMAIL_DOMAIN = '@acme.inc'

// Sign in, or create an account and then sign in with it.
export default function LoginPage({ onLogin }) {
  const [mode, setMode] = useState('login') // 'login' or 'signup'
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [branches, setBranches] = useState([]) // for the signup dropdown

  // The branch list is public, so it can load before anyone signs in
  useEffect(() => {
    users.branches().then(setBranches).catch(() => {})
  }, [])

  async function handleSubmit(values) {
    setError('')
    setBusy(true)
    try {
      if (mode === 'signup') {
        await users.signup(values.email, values.password, values.name, values.branchId)
      }
      const result = await users.login(values.email, values.password)
      onLogin(result.user, result.token, result.refreshToken)
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  // Same rule as the backend, checked here so the message shows before
  // the request is sent.
  function checkCompanyEmail(_, value) {
    if (mode === 'login' || !value || value.trim().toLowerCase().endsWith(COMPANY_EMAIL_DOMAIN)) {
      return Promise.resolve()
    }
    return Promise.reject(new Error(`Use your company email address (ending in ${COMPANY_EMAIL_DOMAIN})`))
  }

  return (
    <div className="login-wrap">
      <Card className="login-card">
        <img src="/acme.svg" alt="" width="40" height="40" className="login-logo" />
        <Typography.Title level={4} style={{ textAlign: 'center', marginTop: 0 }}>
          ACME Inc · Incident Tracker
        </Typography.Title>
        <Typography.Paragraph type="secondary" style={{ textAlign: 'center' }}>
          Report facilities problems and follow them to resolution.
        </Typography.Paragraph>

        <Segmented
          block
          value={mode}
          onChange={(value) => { setMode(value); setError('') }}
          options={[
            { label: 'Sign in', value: 'login' },
            { label: 'Create account', value: 'signup' },
          ]}
          style={{ marginBottom: 20 }}
        />

        <Form layout="vertical" onFinish={handleSubmit} requiredMark={false}>
          {mode === 'signup' && (
            <Form.Item name="name" label="Name" rules={[{ required: true, message: 'Enter your name' }]}>
              <Input prefix={<UserOutlined />} placeholder="Ana Lopez" />
            </Form.Item>
          )}
          {mode === 'signup' && (
            <Form.Item name="branchId" label="Branch" rules={[{ required: true, message: 'Choose where you work' }]}>
              <Select
                placeholder="Where do you work?"
                suffixIcon={<EnvironmentOutlined />}
                options={branches.map((b) => ({ value: b.id, label: b.name }))}
              />
            </Form.Item>
          )}
          <Form.Item
            name="email"
            label={mode === 'signup' ? `Email (your ${COMPANY_EMAIL_DOMAIN} address)` : 'Email'}
            rules={[
              { required: true, message: 'Enter your email' },
              { type: 'email', message: 'Enter a valid email address' },
              { validator: checkCompanyEmail },
            ]}
          >
            <Input prefix={<MailOutlined />} placeholder="you@acme.inc" />
          </Form.Item>
          <Form.Item
            name="password"
            label="Password"
            rules={[
              { required: true, message: 'Enter your password' },
              ...(mode === 'signup' ? [{ min: 8, message: 'At least 8 characters' }] : []),
            ]}
          >
            <Input.Password prefix={<LockOutlined />} />
          </Form.Item>

          <Alert error={error} />

          <Button type="primary" htmlType="submit" block size="large" loading={busy}>
            {mode === 'login' ? 'Sign in' : 'Create account'}
          </Button>
        </Form>
      </Card>
    </div>
  )
}
