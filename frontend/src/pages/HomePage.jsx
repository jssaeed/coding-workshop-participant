import { Button, Card, Col, Row, Space, Typography } from 'antd'
import { CheckCircleOutlined, FileTextOutlined, UserSwitchOutlined } from '@ant-design/icons'
import { isAdmin, isDbAdmin, isStaff } from '../services/format'

const { Title, Paragraph, Text } = Typography

// The welcome page: what this service does, how a ticket moves through it,
// and what the signed-in user can do based on their role.
export default function HomePage({ user, onNavigate }) {
  const steps = [
    {
      icon: <FileTextOutlined />,
      title: 'Report',
      text: 'File a ticket for a problem in any ACME building, with the building, floor and room so the facilities team knows exactly where to go.',
    },
    {
      icon: <UserSwitchOutlined />,
      title: 'Assign',
      text: 'A facility admin reviews new tickets, sets the priority and assigns each one to an engineer.',
    },
    {
      icon: <CheckCircleOutlined />,
      title: 'Resolve',
      text: 'The engineer updates the status as work progresses. Every change and comment is recorded on the ticket and surfaced in your inbox.',
    },
  ]

  // What this person can do, worded for their role
  const abilities = [
    'File a ticket for any problem in an ACME building',
    'Follow your tickets and correspond with the assigned engineer on the thread',
  ]
  if (isStaff(user)) abilities.push('Work through the tickets assigned to you, updating status and priority')
  if (isAdmin(user)) abilities.push('See every ticket, assign engineers, manage accounts and define buildings')
  if (isDbAdmin(user)) abilities.push('Manage accounts and roles across every branch, and run the database migration')

  return (
    <div>
      <div className="hero">
        <Row gutter={[40, 32]} align="middle">
          <Col xs={24} md={13}>
            <Text className="eyebrow">Facilities · Incident Tracker</Text>
            <Title level={2} style={{ marginTop: 8, marginBottom: 12 }}>
              Report building issues and track them to resolution
            </Title>
            <Paragraph className="lead">
              The Incident Tracker is the single place where ACME employees report problems
              in our buildings and where the facilities team manages the work. Each ticket
              records where the problem is, who is handling it and what has been done.
            </Paragraph>
            <Space wrap>
              <Button type="primary" onClick={() => onNavigate('tickets')}>File a ticket</Button>
              <Button onClick={() => onNavigate('tickets')}>View my tickets</Button>
            </Space>
          </Col>
          <Col xs={24} md={11}>
            <img src="/images/hero.svg" alt="Line drawing of an ACME building elevation" />
          </Col>
        </Row>
      </div>

      <Row gutter={[16, 16]}>
        {steps.map((step, index) => (
          <Col xs={24} md={8} key={step.title}>
            <Card className="step-card" style={{ height: '100%' }}>
              <div className="step-icon">{step.icon}</div>
              <Text type="secondary" className="step-number">Step {index + 1}</Text>
              <Title level={5} style={{ marginTop: 2 }}>{step.title}</Title>
              <Paragraph style={{ marginBottom: 0 }}>{step.text}</Paragraph>
            </Card>
          </Col>
        ))}
      </Row>

      <Card title={`Signed in as ${user.name}`} style={{ marginTop: 16 }}>
        <Text type="secondary">With your role you can:</Text>
        <ul className="abilities">
          {abilities.map((text) => (
            <li key={text}>{text}</li>
          ))}
        </ul>
      </Card>
    </div>
  )
}
