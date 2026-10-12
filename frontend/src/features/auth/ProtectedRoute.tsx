import { Navigate, Outlet } from 'react-router-dom'
import { Link } from 'react-router-dom'
import { ArrowUpRight } from '@phosphor-icons/react'
import { useAuth } from './AuthProvider'
import { SignInForm } from './SignInForm'

export type WorkspaceRole = 'operator' | 'supervisor' | 'technician' | 'customer'

export function landingPath(role: string): string {
  if (role === 'customer') return '/portal'
  if (role === 'technician') return '/work'
  if (role === 'operator' || role === 'supervisor') return '/operations'
  return '/sign-in'
}

export function ProtectedRoute({ allowedRoles, signInPath = '/sign-in' }: { allowedRoles: readonly WorkspaceRole[]; signInPath?: string }) {
  const { session } = useAuth()
  if (!session) return <Navigate to={signInPath} replace />
  if (!allowedRoles.includes(session.role as WorkspaceRole)) {
    return <Navigate to={landingPath(session.role)} replace />
  }
  return <Outlet />
}

export function SignInRoute() {
  const { session } = useAuth()
  if (session) return <Navigate to={landingPath(session.role)} replace />
  return (
    <main className="login-page">
      <section className="login-story" aria-label="Field Force workspace">
        <Link className="login-brand" to="/sign-in"><span className="brand-mark">F</span> Fieldforce<span className="brand-descriptor">/ Operations</span></Link>
        <div className="login-story-copy">
          <p className="section-label">Built for the people behind the connection</p>
          <h1>Find the fault.<br /><span>Bring it back online.</span></h1>
          <p>Your incidents, connected equipment and investigation tools. One place to get the next fix moving.</p>
        </div>
        <img className="login-illustration" src="/illustrations/network-studio.svg" alt="Isometric router, network cabinet and access point connected by an amber fiber cable" width="960" height="660" />
        <div className="login-story-footer"><span>Fieldforce / Incident operations</span><span>Follow the connection.</span></div>
      </section>
      <section className="login-form-area" aria-labelledby="sign-in-heading">
        <div className="login-form-top"><span>Field operations workspace</span><span className="login-access">Staff access</span></div>
        <div className="login-form-content">
          <span className="login-step">Your workspace awaits</span>
          <h2 id="sign-in-heading">Welcome back.</h2>
          <p className="login-form-description">Sign in to see your assigned work and pick up where you left off.</p>
          <SignInForm />
          <p className="login-help">Use the work account provided by your team.</p>
        </div>
        <Link className="login-customer-link" to="/portal/sign-in"><span>Looking for help with your connection?<strong>Go to customer support</strong></span><ArrowUpRight size={20} /></Link>
      </section>
    </main>
  )
}
