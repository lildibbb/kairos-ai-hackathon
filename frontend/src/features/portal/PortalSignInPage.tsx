import { useState } from 'react'
import { Scene3D } from '../../components/illustration/Scene3D'
import { Navigate } from 'react-router-dom'
import { Headset, ShieldCheck, WifiHigh } from '@phosphor-icons/react'
import { Button } from '../../components/ui/button'
import { useAuth } from '../auth/AuthProvider'
import { landingPath } from '../auth/ProtectedRoute'
import { SignInForm } from '../auth/SignInForm'
import { Separator } from '../../components/ui/separator'

function MockCustomerSignIn() {
  const { signInAsMockCustomer } = useAuth()
  const [requestError, setRequestError] = useState('')
  const [submitting, setSubmitting] = useState(false)

  const enter = async () => {
    setRequestError('')
    setSubmitting(true)
    try {
      await signInAsMockCustomer()
    } catch (error) {
      setRequestError(error instanceof Error ? error.message : 'Sign-in failed. Try again.')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="grid gap-4">
      <p className="portal-login-form__note">
        Open your workspace to chat with support, track tickets and manage visits.
      </p>
      {requestError && <p className="form-error" role="alert">{requestError}</p>}
      <Button className="sign-in-button" type="button" onClick={enter} disabled={submitting}>
        {submitting ? 'Opening your portal…' : 'Enter customer portal'}
      </Button>
    </div>
  )
}

export function PortalSignInPage({ checker = false }: { checker?: boolean }) {
  const { session } = useAuth()
  if (session) {
    return (
      <Navigate
        to={checker && ['operator', 'supervisor'].includes(session.role) ? '/admin/check' : landingPath(session.role)}
        replace
      />
    )
  }
  const Icon = checker ? ShieldCheck : Headset

  return (
    <main className="portal-login">
      <section className="portal-login-hero" aria-hidden="true">
        <div className="portal-login-hero__backdrop" />
        <div className="portal-login-hero__content">
          <div className="portal-login-hero__brand">
            <img src="/unifi.svg" alt="" width="104" height="41" />
            <span>Customer support</span>
          </div>
          <Scene3D className="portal-login-hero__orb" variant="devices" size={320} />
          <div className="portal-login-hero__copy">
            <p className="portal-login-hero__eyebrow"><WifiHigh size={16} weight="bold" /> Connection support</p>
            <h2>Let’s get your connection working again.</h2>
            <p>Track tickets, confirm appointments and get guided troubleshooting in one calm, connected place.</p>
          </div>
        </div>
      </section>

      <section className="portal-login-form">
        <header className="portal-login-form__brand">
          <img src="/unifi.svg" alt="Unifi" width="100" height="39" />
          <span className="portal-brand-divider" />
          <span>Customer support</span>
        </header>
        <div className="portal-welcome-icon"><Icon size={28} weight="duotone" /></div>
        <h1>{checker ? 'Report Checker' : 'Welcome Back'}</h1>
        <p>{checker ? 'Operator and supervisor access' : 'Continue to your customer account'}</p>
        {checker ? <SignInForm emailLabel="Work email" /> : <MockCustomerSignIn />}
        <Separator className="portal-login-form__divider" />
        <a href={checker ? '/portal/sign-in' : '/admin/sign-in'}>{checker ? 'Customer support' : 'Staff sign-in'}</a>
      </section>
    </main>
  )
}
