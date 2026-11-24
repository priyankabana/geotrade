import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { Empty } from './Panels'

describe('<Empty>', () => {
  it('renders its title and body', () => {
    render(<Empty title="Could not load this company" body="Check your connection." />)
    expect(screen.getByRole('heading', { name: 'Could not load this company' })).toBeInTheDocument()
    expect(screen.getByText('Check your connection.')).toBeInTheDocument()
  })
})
