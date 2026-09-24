import { useEffect, useState } from 'react'
import { Breadcrumb, Card, Col, Row, Segmented, Table, Typography } from 'antd'
import { stats } from '../services/api'
import { floorLabel, formatDuration, label } from '../services/format'
import Alert from '../components/Alert'
import Donut from '../components/charts/Donut'
import BarChart from '../components/charts/BarChart'
import { DEFAULT_DAYS, RANGES, Tile, statusItems } from '../components/charts/shared'

// Admin only: every ticket by status, and tickets per building, with a
// click-through to floors and then rooms.
export default function StatsPage() {
  const [days, setDays] = useState(DEFAULT_DAYS)
  const [error, setError] = useState('')
  const [overview, setOverview] = useState(null)
  const [engineers, setEngineers] = useState([])

  // The location drill-down. building/floor say how deep we are.
  const [building, setBuilding] = useState(null) // {id, name} or null
  const [floor, setFloor] = useState(null)
  const [locations, setLocations] = useState(null)
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    setError('')
    stats.overview(days).then(setOverview).catch((err) => setError(err.message))
    stats.engineers(days).then(setEngineers).catch((err) => setError(err.message))
  }, [days])

  // Load the location level currently being looked at
  useEffect(() => {
    setLoading(true)
    stats.locations(days, building ? building.id : undefined, floor ?? undefined)
      .then(setLocations)
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false))
  }, [days, building, floor])

  // Turn the current level's rows into bars, and decide what a click does
  function locationBars() {
    if (!locations) return []
    if (locations.level === 'building') {
      return locations.items.map((item) => ({
        key: item.id ?? 'none', label: item.name, value: item.count,
        selectable: item.id !== null, // "No location" cannot be opened
        onOpen: () => setBuilding({ id: item.id, name: item.name }),
      }))
    }
    if (locations.level === 'floor') {
      return locations.items.map((item) => ({
        key: item.floor, label: `Floor ${floorLabel(item.floor)}`, value: item.count,
        onOpen: () => setFloor(item.floor),
      }))
    }
    return locations.items.map((item) => ({
      key: item.room ?? 'none', label: item.room === null ? 'No room' : `Room ${item.label}`, value: item.count,
      selectable: false,
    }))
  }

  const crumbs = [{ title: <a onClick={() => { setBuilding(null); setFloor(null) }}>All buildings</a> }]
  if (building) crumbs.push({ title: floor === null ? building.name : <a onClick={() => setFloor(null)}>{building.name}</a> })
  if (floor !== null) crumbs.push({ title: `Floor ${floorLabel(floor)}` })

  const levelTitle = !building ? 'Tickets per building'
    : floor === null ? `Tickets per floor in ${building.name}`
    : `Tickets per room on floor ${floorLabel(floor)}, ${building.name}`

  return (
    <div>
      <div className="page-title">
        <Typography.Title level={2} style={{ margin: 0 }}>Statistics</Typography.Title>
        <Segmented value={days} onChange={setDays} options={RANGES} />
      </div>

      <Alert error={error} />

      {overview && (
        <Card title="All tickets" style={{ marginBottom: 16 }}>
          <Row gutter={[24, 24]} align="middle">
            <Col xs={24} md={5}>
              <Tile value={overview.total} caption={`tickets opened in the last ${days} days`} />
            </Col>
            <Col xs={24} md={5}>
              <Tile
                value={formatDuration(overview.resolution.averageSeconds)}
                caption={`average time to resolve (${overview.resolution.resolvedCount} resolved)`}
              />
            </Col>
            <Col xs={24} md={14}>
              <Donut items={statusItems(overview.byStatus)} title="By status" />
            </Col>
          </Row>
        </Card>
      )}

      <Card title="Engineers" style={{ marginBottom: 16 }}>
        <Table
          rowKey="id"
          size="small"
          dataSource={engineers}
          pagination={false}
          locale={{ emptyText: 'No tickets were assigned in this range.' }}
          columns={[
            { title: 'Engineer', dataIndex: 'name', render: (name, e) => <span>{name} <span className="muted">({label(e.role)})</span></span> },
            { title: 'Tickets assigned', dataIndex: 'assigned', sorter: (a, b) => a.assigned - b.assigned, defaultSortOrder: 'descend' },
            { title: 'Resolved', dataIndex: 'resolved', sorter: (a, b) => a.resolved - b.resolved },
            {
              title: 'Average time to resolve',
              dataIndex: 'averageSeconds',
              render: formatDuration,
              sorter: (a, b) => (a.averageSeconds ?? Infinity) - (b.averageSeconds ?? Infinity),
            },
          ]}
        />
      </Card>

      <Card title={levelTitle} extra={<Breadcrumb items={crumbs} />} className={loading ? 'chart-loading' : ''}>
        <p className="muted" style={{ marginTop: 0 }}>
          {!building && 'Click a building to see its floors.'}
          {building && floor === null && 'Click a floor to see its rooms.'}
          {floor !== null && 'Rooms on this floor. Use the trail above to go back up.'}
        </p>
        <BarChart items={locationBars()} onSelect={(item) => item.onOpen && item.onOpen()} />
      </Card>
    </div>
  )
}
