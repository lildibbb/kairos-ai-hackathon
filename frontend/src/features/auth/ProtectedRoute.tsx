import { Navigate, Outlet } from 'react-router-dom'
import { useLayoutEffect, useRef } from 'react'
import { gsap } from 'gsap'
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
  const pageRef = useRef<HTMLElement>(null)
  useLayoutEffect(() => {
    if (!pageRef.current) return
    const context = gsap.context(() => {
      gsap.fromTo('.sign-in-story', { opacity: 0, y: 18 }, { opacity: 1, y: 0, duration: .45, ease: 'power3.out' })
      gsap.fromTo('.sign-in-panel', { opacity: 0, y: 12 }, { opacity: 1, y: 0, duration: .4, delay: .1, ease: 'power3.out' })
      gsap.fromTo('.orbit-node', { opacity: 0, scale: .7 }, { opacity: 1, scale: 1, duration: .25, delay: .2, stagger: .07, ease: 'back.out(1.7)' })
    }, pageRef)
    return () => context.revert()
  }, [])
  if (session) return <Navigate to={landingPath(session.role)} replace />
  return (
    <main ref={pageRef} className="app-shell sign-in-shell">
      <header className="app-header">
        <p className="app-context">FIELD OPERATIONS</p>
        <h1>Field Force Incident Assistant</h1>
      </header>
      <div className="sign-in-layout">
        <div className="sign-in-story">
          <div className="signal-orbit" aria-hidden="true">
            <span className="orbit-core" /><span className="orbit-ring orbit-ring-one" /><span className="orbit-ring orbit-ring-two" />
            <i className="orbit-node orbit-node-one" /><i className="orbit-node orbit-node-two" /><i className="orbit-node orbit-node-three" />
          </div>
          <p className="section-label">Field operations / incident signal path</p>
          <p className="sign-in-statement">See the signal.<br /><em>Move with certainty.</em></p>
          <p>Ticket context, network evidence, and safe next actions in one focused workspace.</p>
          <div className="sign-in-footnote"><strong>FIELD FORCE</strong><span>Built for the work in front of you.</span></div>
        </div>
      <section className="sign-in-panel" aria-labelledby="sign-in-heading">
        <div className="sign-in-intro">
          <h2 id="sign-in-heading">Sign in to your field workspace</h2>
          <p>Use your work account to enter assigned operations.</p>
        </div>
        <SignInForm />
      </section>
      </div>
    </main>
  )
}
