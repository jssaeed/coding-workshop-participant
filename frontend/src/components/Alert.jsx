/**
 * Inline message for errors and confirmations. Renders nothing when empty.
 */
export default function Alert({ error, success }) {
  if (error) return <p className="alert alert-error" role="alert">{error}</p>
  if (success) return <p className="alert alert-success" role="status">{success}</p>
  return null
}
