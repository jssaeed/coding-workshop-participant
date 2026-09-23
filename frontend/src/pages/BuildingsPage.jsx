import { useEffect, useState } from 'react'
import { buildings } from '../services/api'
import Alert from '../components/Alert'

// Admin only: the list of buildings, with a form to add one and controls to
// change a building's floor count or delete it.
export default function BuildingsPage() {
  const [list, setList] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')
  const [refreshCount, setRefreshCount] = useState(0)

  // The add form
  const [name, setName] = useState('')
  const [floors, setFloors] = useState(1)
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    async function load() {
      setLoading(true)
      try {
        setList(await buildings.list())
      } catch (err) {
        setError(err.message)
      } finally {
        setLoading(false)
      }
    }
    load()
  }, [refreshCount])

  async function handleAdd(event) {
    event.preventDefault()
    setError('')
    setSuccess('')
    setSaving(true)
    try {
      await buildings.create(name, Number(floors))
      setSuccess(`${name} added.`)
      setName('')
      setFloors(1)
      setRefreshCount(refreshCount + 1)
    } catch (err) {
      setError(err.message)
    } finally {
      setSaving(false)
    }
  }

  async function changeFloors(building, newFloors) {
    setError('')
    setSuccess('')
    try {
      await buildings.update(building.id, { floors: Number(newFloors) })
      setSuccess(`${building.name} now has ${newFloors} floors.`)
      setRefreshCount(refreshCount + 1)
    } catch (err) {
      setError(err.message)
      setRefreshCount(refreshCount + 1) // put the old value back in the input
    }
  }

  async function remove(building) {
    if (!window.confirm(`Delete ${building.name}?`)) return
    setError('')
    setSuccess('')
    try {
      await buildings.remove(building.id)
      setSuccess(`${building.name} deleted.`)
      setRefreshCount(refreshCount + 1)
    } catch (err) {
      setError(err.message)
    }
  }

  return (
    <div>
      <h1>Buildings</h1>

      <form onSubmit={handleAdd} className="panel">
        <h2>Add a building</h2>
        <div className="row">
          <label>
            Name
            <input value={name} onChange={(e) => setName(e.target.value)} required />
          </label>
          <label>
            Number of floors
            <input
              type="number"
              min="1"
              max="200"
              value={floors}
              onChange={(e) => setFloors(e.target.value)}
              required
            />
          </label>
          <button type="submit" disabled={saving}>Add</button>
        </div>
      </form>

      <Alert error={error} success={success} />

      {loading && <p>Loading…</p>}
      {!loading && list.length === 0 && <p>No buildings yet.</p>}
      {!loading && list.length > 0 && (
        <table>
          <thead>
            <tr>
              <th>Name</th>
              <th>Floors</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {list.map((building) => (
              <tr key={building.id}>
                <td>{building.name}</td>
                <td>
                  <input
                    type="number"
                    min="1"
                    max="200"
                    defaultValue={building.floors}
                    // Save when the user leaves the field, not on every keystroke
                    onBlur={(e) => {
                      if (Number(e.target.value) !== building.floors) changeFloors(building, e.target.value)
                    }}
                    style={{ width: '5em' }}
                  />
                </td>
                <td>
                  <button type="button" onClick={() => remove(building)}>Delete</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  )
}
