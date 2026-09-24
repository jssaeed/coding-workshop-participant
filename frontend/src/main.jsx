import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { ConfigProvider } from 'antd'
import { HashRouter } from 'react-router-dom'
import './index.css'
import App from './App.jsx'

// ACME brand colours, applied to every Ant Design component.
const theme = {
  token: {
    colorPrimary: '#1e3a5f',
    colorLink: '#1e3a5f',
    colorText: '#1f2937',
    borderRadius: 4,
    fontFamily: 'Inter, system-ui, -apple-system, "Segoe UI", Helvetica, Arial, sans-serif',
  },
  components: {
    Layout: {
      headerBg: '#ffffff',
      footerBg: '#ffffff',
    },
    Menu: {
      horizontalItemSelectedColor: '#1e3a5f',
    },
    Card: {
      headerFontSize: 15,
    },
  },
}

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <ConfigProvider theme={theme}>
      {/* Hash URLs (/#/tickets/12) so a refresh works on any page without
          server-side routing: the site is static files on CloudFront. */}
      <HashRouter>
        <App />
      </HashRouter>
    </ConfigProvider>
  </StrictMode>,
)
