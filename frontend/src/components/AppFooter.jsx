import { Layout } from 'antd'

const { Footer } = Layout

// The bar at the bottom of every page.
export default function AppFooter() {
  const year = new Date().getFullYear()
  return (
    <Footer className="footer">
      <span>ACME Inc © {year}</span>
      <span className="footer-sep">·</span>
      <span>Facilities Incident Tracker</span>
      <span className="footer-sep">·</span>
      <span>Internal use only</span>
    </Footer>
  )
}
