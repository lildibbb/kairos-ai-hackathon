import { Navigate } from 'react-router-dom'
import { Headset, ShieldCheck } from '@phosphor-icons/react'
import { useAuth } from '../auth/AuthProvider'
import { landingPath } from '../auth/ProtectedRoute'
import { SignInForm } from '../auth/SignInForm'

export function PortalSignInPage({ checker = false }: { checker?: boolean }) {
  const { session } = useAuth()
  if (session) return <Navigate to={checker && ['operator', 'supervisor'].includes(session.role) ? '/admin/check' : landingPath(session.role)} replace />
  const Icon = checker ? ShieldCheck : Headset
  return <main className="portal-login"><header className="portal-header"><div className="portal-brand"><img src="/unifi.svg" alt="Unifi" width="100" height="39" /><span className="portal-brand-divider" /><span>Customer support</span></div></header><section className="portal-login-form"><div className="portal-welcome-icon"><Icon size={30} /></div><h1>{checker ? 'Report Checker' : 'Welcome Back'}</h1><p>{checker ? 'Operator and supervisor access' : 'Sign in to your customer account'}</p><SignInForm emailLabel={checker ? 'Work email' : 'Email'} /><a href={checker ? '/portal/sign-in' : '/admin/sign-in'}>{checker ? 'Customer support' : 'Staff sign-in'}</a></section></main>
}
