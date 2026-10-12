import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { PortalSignInPage } from './PortalSignInPage'

vi.mock('../auth/AuthProvider', () => ({ useAuth: () => ({ session: null, signIn: vi.fn() }) }))

describe('portal sign-in copy', () => {
  it.each([false, true])('uses normal sign-in wording, checker=%s', (checker) => {
    const { container } = render(<PortalSignInPage checker={checker} />)
    expect(screen.getByRole('heading', { name: checker ? 'Report Checker' : 'Welcome Back' })).toBeInTheDocument()
    expect(container.textContent).not.toMatch(/demo|prototype|local testing/i)
    if (!checker) expect(screen.getByRole('link', { name: 'Staff sign-in' })).toBeInTheDocument()
  })
})
