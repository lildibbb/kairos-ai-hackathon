import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { AuthProvider } from '../features/auth/AuthProvider'
import { ProtectedRoute, SignInRoute } from '../features/auth/ProtectedRoute'
import type { AuthSession } from '../lib/auth/session'
import App from './App'

function WorkPage() {
  return <h1>Assigned work area</h1>
}

function OperationsPage() {
  return <h1>Operations queue area</h1>
}

function AuthTestRoutes({ initialPath = '/sign-in' }: { initialPath?: string }) {
  return (
    <AuthProvider>
      <MemoryRouter initialEntries={[initialPath]}>
        <Routes>
          <Route path="/sign-in" element={<SignInRoute />} />
          <Route element={<ProtectedRoute allowedRoles={['technician']} />}>
            <Route path="/work" element={<WorkPage />} />
          </Route>
          <Route element={<ProtectedRoute allowedRoles={['operator', 'supervisor']} />}>
            <Route path="/operations" element={<OperationsPage />} />
          </Route>
          <Route path="/invalid" element={<h1>Invalid session destination</h1>} />
        </Routes>
      </MemoryRouter>
    </AuthProvider>
  )
}

function SignedInRouteFixture({ role, path }: { role: string; path: string }) {
  const session: AuthSession = {
    accessToken: 'signed-token',
    userId: `${role}-1`,
    role,
    expiresAt: Date.now() + 60_000,
  }
  window.sessionStorage.setItem('field-force-auth-session', JSON.stringify(session))
  return (
    <AuthProvider>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path="/sign-in" element={<SignInRoute />} />
          <Route element={<ProtectedRoute allowedRoles={['technician']} />}>
            <Route path="/work" element={<WorkPage />} />
          </Route>
          <Route element={<ProtectedRoute allowedRoles={['operator', 'supervisor']} />}>
            <Route path="/operations" element={<OperationsPage />} />
          </Route>
        </Routes>
      </MemoryRouter>
    </AuthProvider>
  )
}

describe('authentication routes', () => {
  beforeEach(() => {
    window.sessionStorage.clear()
    vi.stubGlobal('fetch', vi.fn())
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    window.sessionStorage.clear()
  })

  it('shows sign-in field validation before sending credentials', async () => {
    const user = userEvent.setup()
    render(<AuthTestRoutes />)

    await user.click(screen.getByRole('button', { name: 'Sign in' }))

    expect(await screen.findByText('Enter a valid email address.')).toBeInTheDocument()
    expect(await screen.findByText('Enter your password.')).toBeInTheDocument()
    expect(screen.getByLabelText('Work email')).toHaveAttribute('aria-invalid', 'true')
    expect(vi.mocked(fetch)).not.toHaveBeenCalled()
  })

  it('shows an accessible login error from the server', async () => {
    vi.mocked(fetch).mockResolvedValue(new Response('', { status: 401 }))
    const user = userEvent.setup()
    render(<AuthTestRoutes />)

    await user.type(screen.getByLabelText('Work email'), 'field@example.test')
    await user.type(screen.getByLabelText('Password'), 'bad-password')
    await user.click(screen.getByRole('button', { name: 'Sign in' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('Email or password is incorrect.')
  })

  it('redirects an unauthenticated direct route to sign in', async () => {
    render(<AuthTestRoutes initialPath="/work" />)

    expect(await screen.findByRole('heading', { name: 'Welcome back.' })).toBeInTheDocument()
  })

  it('redirects a technician away from operations to assigned work', async () => {
    render(<SignedInRouteFixture role="technician" path="/operations" />)

    expect(await screen.findByRole('heading', { name: 'Assigned work area' })).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: 'Operations queue area' })).not.toBeInTheDocument()
  })

  it('redirects an operator away from technician-only work to operations', async () => {
    render(<SignedInRouteFixture role="operator" path="/work" />)

    expect(await screen.findByRole('heading', { name: 'Operations queue area' })).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: 'Assigned work area' })).not.toBeInTheDocument()
  })

  it.each([
    { role: 'technician', label: 'TECHNICIAN', workspace: 'Assigned work', route: '/work' },
    { role: 'operator', label: 'OPERATOR', workspace: 'Event intake', route: '/operations' },
    { role: 'supervisor', label: 'SUPERVISOR', workspace: 'Event intake', route: '/operations' },
  ])('shows $label context with its active existing workspace destination', async ({ role, label, workspace, route }) => {
    window.sessionStorage.setItem('field-force-auth-session', JSON.stringify({
      accessToken: 'signed-token', userId: `${role}-1`, role, expiresAt: Date.now() + 60_000,
    }))
    render(<App />)

    expect(await screen.findByRole('navigation', { name: 'Workspace' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: workspace })).toHaveAttribute('href', route)
    expect(screen.getByRole('link', { name: workspace })).toHaveAttribute('aria-current', 'page')
    expect(screen.getByText(label)).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Incident operations' })).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: workspace === 'Assigned work' ? 'Event intake' : 'Assigned work' })).not.toBeInTheDocument()

    await userEvent.setup().click(screen.getByRole('link', { name: workspace }))
    expect(screen.getByRole('link', { name: workspace })).toHaveAttribute('aria-current', 'page')
    const sectionHeading = workspace === 'Assigned work' ? 'Assigned tickets' : 'Event intake'
    expect(await screen.findByRole('heading', { name: sectionHeading })).toBeInTheDocument()
  })

  it('signs out and returns to sign-in from the workspace shell', async () => {
    window.sessionStorage.setItem('field-force-auth-session', JSON.stringify({
      accessToken: 'signed-token', userId: 'tech-1', role: 'technician', expiresAt: Date.now() + 60_000,
    }))
    const user = userEvent.setup()
    render(<App />)

    await user.click(await screen.findByRole('button', { name: 'Sign out' }))

    expect(await screen.findByRole('heading', { name: 'Welcome back.' })).toBeInTheDocument()
    expect(window.sessionStorage.getItem('field-force-auth-session')).toBeNull()
  })
})
