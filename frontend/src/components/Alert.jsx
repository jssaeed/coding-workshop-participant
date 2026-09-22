// A red box for errors or a green box for success messages. Shows nothing
// when both are empty.
export default function Alert({ error, success }) {
  if (error) return <p className="alert alert-error">{error}</p>
  if (success) return <p className="alert alert-success">{success}</p>
  return null
}
