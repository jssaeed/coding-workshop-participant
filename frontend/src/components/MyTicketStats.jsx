import { useEffect, useState } from 'react'
import { Card, Col, Row, Segmented } from 'antd'
import { stats } from '../services/api'
import { isStaff } from '../services/format'
import Alert from './Alert'
import Donut from './charts/Donut'
import { DEFAULT_DAYS, RANGES, Tile, statusItems } from './charts/shared'

// The two personal cards at the top of the Tickets page: tickets the user
// reported, and (for engineers and admins) tickets assigned to them.
export default function MyTicketStats({ user }) {
  const [days, setDays] = useState(DEFAULT_DAYS)
  const [mine, setMine] = useState(null)
  const [error, setError] = useState('')

  useEffect(() => {
    setError('')
    stats.mine(days).then(setMine).catch((err) => setError(err.message))
  }, [days])

  const showAssigned = isStaff(user) && mine && mine.assigned

  return (
    <div style={{ marginBottom: 16 }}>
      <div className="stats-toolbar">
        <Segmented value={days} onChange={setDays} options={RANGES} />
      </div>
      <Alert error={error} />
      {mine && (
        <Row gutter={[16, 16]}>
          <Col xs={24} lg={showAssigned ? 12 : 24}>
            <Card title="My Tickets" size="small">
              <Row gutter={[24, 16]} align="middle">
                <Col xs={24} md={8}>
                  <Tile value={mine.reported.total} caption={`opened in the last ${days} days`} />
                </Col>
                <Col xs={24} md={16}>
                  <Donut items={statusItems(mine.reported.byStatus)} title="By status" />
                </Col>
              </Row>
            </Card>
          </Col>
          {showAssigned && (
            <Col xs={24} lg={12}>
              <Card title="Assigned Tickets" size="small">
                <Row gutter={[24, 16]} align="middle">
                  <Col xs={24} md={8}>
                    <Tile value={mine.assigned.total} caption={`opened in the last ${days} days`} />
                  </Col>
                  <Col xs={24} md={16}>
                    <Donut items={statusItems(mine.assigned.byStatus, ['open'])} title="By status" />
                  </Col>
                </Row>
              </Card>
            </Col>
          )}
        </Row>
      )}
    </div>
  )
}
