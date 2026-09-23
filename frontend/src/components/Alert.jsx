import { Alert as AntAlert } from 'antd'

// A red box for errors or a green box for success messages. Shows nothing
// when both are empty.
export default function Alert({ error, success }) {
  if (error) return <AntAlert type="error" message={error} showIcon className="alert" />
  if (success) return <AntAlert type="success" message={success} showIcon className="alert" />
  return null
}
