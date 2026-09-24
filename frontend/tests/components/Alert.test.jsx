import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import Alert from '../../src/components/Alert'

describe('Alert', () => {
  it('shows nothing when there is nothing to say', () => {
    const { container } = render(<Alert error="" success="" />)
    expect(container).toBeEmptyDOMElement()
  })

  it('shows an error in red', () => {
    render(<Alert error="'title' is required" />)
    const alert = screen.getByRole('alert')
    expect(alert).toHaveTextContent("'title' is required")
    expect(alert).toHaveClass('ant-alert-error')
  })

  it('shows a success message in green, but an error wins', () => {
    render(<Alert success="Saved." />)
    expect(screen.getByRole('alert')).toHaveClass('ant-alert-success')
    render(<Alert error="Nope" success="Saved." />)
    expect(screen.getAllByRole('alert')[1]).toHaveClass('ant-alert-error')
  })
})
