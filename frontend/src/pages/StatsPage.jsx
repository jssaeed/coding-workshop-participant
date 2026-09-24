import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Breadcrumb, Button, Card, Col, Row, Segmented, Space, Typography } from 'antd'
import { FilterOutlined } from '@ant-design/icons'
import { stats } from '../services/api'
import { floorLabel, formatDuration, ticketListUrl } from '../services/format'
import Alert from '../components/Alert'
import Donut from '../components/charts/Donut'
import BarChart from '../components/charts/BarChart'
import { DEFAULT_DAYS, RANGES, Tile, categoryItems, engineerItems, priorityItems, statusItems } from '../components/charts/shared'

// Admin only: every ticket by status, by priority and by category, the
// tickets assigned per engineer, and tickets per building, with a
// click-through to floors and then rooms. Every number is a link: clicking
// it opens the Tickets page filtered to the tickets it counts. (The bars are
// the exception, since a click on them drills down; they have a "Filter by
// selection" button instead.) Clicking an engineer in their ring selects
// them: two tiles beside the ring then show how many tickets they resolved
// and their average time to resolve, next to (not instead of) the branch's
// overall figure. A second click clears the selection.
export default function StatsPage() {
  const navigate = useNavigate()
  const [days, setDays] = useState(DEFAULT_DAYS)
  const [error, setError] = useState('')
  const [overview, setOverview] = useState(null)
  const [engineers, setEngineers] = useState([])
  const [selectedEngineerId, setSelectedEngineerId] = useState(null)
  // Looked up from the current list, so if the range changes and the
  // engineer has no tickets in it any more, the tile falls back to the
  // overall average on its own.
  const selectedEngineer = engineers.find((engineer) => engineer.id === selectedEngineerId) || null

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

  // Open the Tickets page showing the tickets behind a number: every ticket
  // at the branch, in this range, narrowed by the given filters
  function showTickets(filters) {
    navigate(ticketListUrl({ scope: 'all', days, ...filters }))
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
          {/* Two rows of the same shape: numbers on the left of a wide screen,
              two rings sharing the rest. The card grows downwards. */}
          <Row gutter={[24, 24]} align="middle">
            <Col xs={24} xl={4}>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 24 }}>
                <Tile value={overview.total} caption={`tickets opened in the last ${days} days`} onClick={() => showTickets({})} />
                <Tile
                  value={formatDuration(overview.resolution.averageSeconds)}
                  caption={`average time to resolve (${overview.resolution.resolvedCount} resolved)`}
                  onClick={() => showTickets({ status: 'resolved' })}
                />
              </div>
            </Col>
            <Col xs={24} md={12} xl={10}>
              <Donut items={statusItems(overview.byStatus)} title="By status" onSelect={(item) => showTickets({ status: item.key })} />
            </Col>
            <Col xs={24} md={12} xl={10}>
              <Donut items={priorityItems(overview.byPriority)} title="By priority" onSelect={(item) => showTickets({ priority: item.key })} />
            </Col>
          </Row>

          <Row gutter={[24, 24]} align="middle" style={{ marginTop: 24 }}>
            <Col xs={24} xl={4}>
              {/* The selected engineer's own numbers. The list has no "assigned
                  to" filter, so the click searches for their name */}
              {selectedEngineer ? (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 24 }}>
                  <Tile
                    value={selectedEngineer.resolved}
                    caption={`tickets resolved by ${selectedEngineer.name}`}
                    onClick={() => showTickets({ status: 'resolved', q: selectedEngineer.name })}
                  />
                  <Tile
                    value={formatDuration(selectedEngineer.averageSeconds)}
                    caption={`average time for ${selectedEngineer.name} to resolve`}
                    onClick={() => showTickets({ status: 'resolved', q: selectedEngineer.name })}
                  />
                  <Button size="small" onClick={() => setSelectedEngineerId(null)}>Clear selection</Button>
                </div>
              ) : (
                <p className="muted" style={{ margin: 0 }}>
                  Click an engineer to see how many tickets they resolved and their average time to resolve.
                </p>
              )}
            </Col>
            <Col xs={24} md={12} xl={10} className="engineer-chart">
              <Donut
                items={engineerItems(engineers)}
                title="Assigned per engineer"
                centreLabel="assigned"
                onSelect={(item) => setSelectedEngineerId(item.key === selectedEngineerId ? null : item.key)}
              />
            </Col>
            <Col xs={24} md={12} xl={10} className="category-chart">
              <Donut items={categoryItems(overview.byCategory)} title="By category" onSelect={(item) => showTickets({ category: item.key })} />
            </Col>
          </Row>
        </Card>
      )}

      <Card
        title={levelTitle}
        className={loading ? 'location-chart chart-loading' : 'location-chart'}
        extra={(
          <Space>
            <Breadcrumb items={crumbs} />
            {/* Clicking a bar drills down, so filtering is a separate button:
                it opens the tickets in the building (and floor) being looked at */}
            <Button
              icon={<FilterOutlined />}
              disabled={!building}
              onClick={() => showTickets({ buildingId: building.id, floor: floor ?? undefined })}
            >
              Filter by selection
            </Button>
          </Space>
        )}
      >
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
