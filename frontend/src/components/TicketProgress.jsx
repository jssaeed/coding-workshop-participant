import { CheckOutlined, ExclamationOutlined, LockOutlined } from '@ant-design/icons'

// The stages a ticket moves through, in order. "blocked" is not a stage: a
// blocked ticket is stuck at "In progress", so the bar stops there in red.
// A closed ticket has no dot: the whole bar goes grey with a "Closed"
// marker at the end.
const STAGES = ['Open', 'Assigned', 'In progress', 'Resolved']

// Which stage (0-3) the ticket is at
function stageFor(status) {
  if (status === 'open') return 0
  if (status === 'assigned') return 1
  if (status === 'in_progress' || status === 'blocked') return 2
  return 3 // resolved or closed
}

// The colour of the filled part of the bar
function toneFor(status) {
  if (status === 'closed') return 'grey'
  if (status === 'blocked') return 'red'
  if (status === 'resolved') return 'green'
  return 'blue'
}

// A bar across the top of a ticket showing how far along it is.
export default function TicketProgress({ status }) {
  const tone = toneFor(status)
  const currentIndex = stageFor(status)
  const isClosed = status === 'closed'
  const isBlocked = status === 'blocked'

  return (
    <div className={`progress progress-${tone}`} aria-label="Ticket progress">
      <ol className="progress-steps">
        {STAGES.map((title, index) => {
          const isDone = index < currentIndex || isClosed
          const isCurrent = index === currentIndex && !isClosed
          const state = isDone ? 'done' : isCurrent ? 'current' : 'todo'
          return (
            <li key={title} className={`progress-step progress-${state}`}>
              <div className="progress-track">
                <span className="progress-dot">
                  {isDone && <CheckOutlined />}
                  {isCurrent && isBlocked && <ExclamationOutlined />}
                  {isCurrent && !isBlocked && index + 1}
                  {!isDone && !isCurrent && index + 1}
                </span>
              </div>
              <div className="progress-label">
                {title}
                {isCurrent && isBlocked && <span className="progress-note">Blocked</span>}
              </div>
            </li>
          )
        })}
      </ol>
      {isClosed && (
        <div className="progress-closed">
          <LockOutlined /> Closed
        </div>
      )}
    </div>
  )
}
