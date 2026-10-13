import { SquaresFour, Graph, SignOut } from '@phosphor-icons/react'
import type { ReactNode } from 'react'
import { BrowserRouter, NavLink, Navigate, Route, Routes, useNavigate } from 'react-router-dom'
import { Button } from '../components/ui/button'
import { KairosLogo } from '../components/brand/KairosLogo'
import { AuthProvider, useAuth } from '../features/auth/AuthProvider'
import { ProtectedRoute, SignInRoute } from '../features/auth/ProtectedRoute'
import { EventIntakeQueue } from '../features/intake/EventIntakeQueue'
import { AssignedWorkList } from '../features/work/AssignedWorkList'
import { TicketPage } from '../features/work/TicketPage'
import { AuditPage } from '../features/audit/AuditPage'
import { NetworkDirectory } from '../features/network/NetworkDirectory'
import { CustomerChatPage } from '../features/portal/CustomerChatPage'
import { ReportCheckerPage } from '../features/portal/ReportCheckerPage'
import { PortalSignInPage } from '../features/portal/PortalSignInPage'

function WorkspaceShell({ children }: { children: ReactNode }) {
  const { session, signOut } = useAuth()
  const navigate = useNavigate()
  const isTechnician = session?.role === 'technician'
  const roleLabel = isTechnician ? 'TECHNICIAN' : session?.role === 'supervisor' ? 'SUPERVISOR' : 'OPERATOR'
  const workspaceLabel = isTechnician ? 'Assigned work' : 'Event intake'

  function handleSignOut() {
    signOut()
    navigate('/sign-in', { replace: true })
  }

  return (
    <main className="app-shell">
      <header className="app-header">
        <div className="app-brand">
          <p className="app-context"><KairosLogo /></p>
          <h1>Incident operations</h1>
        </div>
        <nav className="workspace-nav" aria-label="Workspace">
          <NavLink to={isTechnician ? '/work' : '/operations'}><SquaresFour size={18} />{workspaceLabel}</NavLink>
          <NavLink to="/network"><Graph size={18} />Customer network</NavLink>
        </nav>
        <div className="app-account">
          <span className="workspace-role">{roleLabel}</span>
          <Button className="text-button" variant="quiet" type="button" onClick={handleSignOut}><SignOut size={18} />Sign out</Button>
        </div>
      </header>
      {children}
    </main>
  )
}

export default function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Routes>
          <Route path="/sign-in" element={<SignInRoute />} />
          <Route path="/portal/sign-in" element={<PortalSignInPage />} />
          <Route path="/admin/sign-in" element={<PortalSignInPage checker />} />
          <Route element={<ProtectedRoute allowedRoles={['customer']} signInPath="/portal/sign-in" />}>
            <Route path="/portal" element={<CustomerChatPage />} />
          </Route>
          <Route element={<ProtectedRoute allowedRoles={['technician']} />}>
            <Route path="/work" element={<WorkspaceShell><AssignedWorkList /></WorkspaceShell>} />
          </Route>
          <Route element={<ProtectedRoute allowedRoles={['operator', 'supervisor']} />}>
            <Route path="/operations" element={<WorkspaceShell><EventIntakeQueue /></WorkspaceShell>} />
          </Route>
          <Route element={<ProtectedRoute allowedRoles={['operator', 'supervisor']} signInPath="/admin/sign-in" />}>
            <Route path="/admin/check" element={<ReportCheckerPage />} />
          </Route>
          <Route
            element={<ProtectedRoute allowedRoles={['technician', 'operator', 'supervisor']} />}
          >
            <Route path="/network" element={<WorkspaceShell><NetworkDirectory /></WorkspaceShell>} />
            <Route path="/tickets/:ticketId" element={<TicketPage />} />
            <Route path="/tickets/:ticketId/audit" element={<AuditPage />} />
          </Route>
          <Route path="*" element={<Navigate to="/sign-in" replace />} />
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  )
}
