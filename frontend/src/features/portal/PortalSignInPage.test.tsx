import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { PortalSignInPage } from './PortalSignInPage'

const signInAsMockCustomer = vi.fn()
vi.mock('../auth/AuthProvider', () => ({
  useAuth: () => ({ session: null, signIn: vi.fn(), signInAsMockCustomer }),
}))

describe('portal sign-in copy', () => {
  it.each([false, true])('uses normal sign-in wording, checker=%s', (checker) => {
    const { container } = render(<PortalSignInPage checker={checker} />)
    expect(screen.getByRole('heading', { name: checker ? 'Report Checker' : 'Welcome Back' })).toBeInTheDocument()
    expect(container.textContent).not.toMatch(/demo|prototype|local testing/i)
    if (!checker) expect(screen.getByRole('link', { name: 'Staff sign-in' })).toBeInTheDocument()
  })

  it('enters the customer portal with the mocked identity, not a password form', async () => {
    render(<PortalSignInPage />)
    expect(screen.queryByLabelText('Password')).not.toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Enter customer portal' }))
    expect(signInAsMockCustomer).toHaveBeenCalledOnce()
  })
})
