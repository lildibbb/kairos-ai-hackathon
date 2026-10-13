import { useCallback, useEffect, useState } from 'react'
import { Scene3D } from '../../components/illustration/Scene3D'
import { Button } from '../../components/ui/button'
import { Link, useParams } from 'react-router-dom'
import { useAuth } from '../auth/AuthProvider'
import { fetchTicketAudit, type AuditEvent } from '../../lib/api/audit'
import { TicketsApiError } from '../../lib/api/tickets'
import { AuditTimeline } from './AuditTimeline'

type PageState = 'loading' | 'ready' | 'error' | 'denied'

export function AuditPage() {
  const { ticketId } = useParams()
  const { session } = useAuth()
  const token = session?.accessToken ?? ''
  const backTo = session?.role === 'technician' ? '/work' : '/operations'

  const [events, setEvents] = useState<AuditEvent[]>([])
  const [state, setState] = useState<PageState>('loading')
  const [error, setError] = useState('')

  const load = useCallback(
    async (signal?: AbortSignal) => {
      if (!ticketId) {
        setState('error')
        setError('No ticket was specified.')
        return
      }
      setState('loading')
      setError('')
      try {
        const loaded = await fetchTicketAudit(ticketId, token, signal)
        setEvents(loaded)
        setState('ready')
      } catch (caught) {
        if (caught instanceof DOMException && caught.name === 'AbortError') return
        if (caught instanceof TicketsApiError && (caught.status === 403 || caught.status === 404)) {
          setState('denied')
          return
        }
        setState('error')
        setError(caught instanceof TicketsApiError ? caught.message : 'The audit history could not be loaded.')
      }
    },
    [ticketId, token],
  )

  useEffect(() => {
    const controller = new AbortController()
    void load(controller.signal)
    return () => controller.abort()
  }, [load])

  return (
    <main className="app-shell">
      <header className="app-header">
        <p className="app-context">FIELD OPERATIONS</p>
        <h1>Ticket audit history</h1>
        <Scene3D className="heading-scene" variant="stack" size={96} />
        {ticketId && (
          <Link className="inline-link" to={`/tickets/${ticketId}`}>
            Back to ticket
          </Link>
        )}
      </header>

      {state === 'loading' && (
        <p className="state-panel" role="status">
          Loading audit history.
        </p>
      )}

      {state === 'error' && (
        <div className="state-panel">
          <p className="form-error" role="alert">
            {error}
          </p>
          <Button className="process-button" type="button" onClick={() => void load()}>
            Retry loading audit
          </Button>
        </div>
      )}

      {state === 'denied' && (
        <section className="state-panel" aria-labelledby="audit-denied-heading">
          <h3 id="audit-denied-heading">Audit history not available</h3>
          <p>This ticket is not part of your scope, so its history cannot be shown.</p>
          <Link className="inline-link" to={backTo}>
            {session?.role === 'technician' ? 'Back to my work' : 'Back to event intake'}
          </Link>
        </section>
      )}

      {state === 'ready' && (
        <section className="panel audit-panel" aria-labelledby="audit-heading">
          <h3 id="audit-heading">Recorded activity</h3>
          <AuditTimeline events={events} />
        </section>
      )}
    </main>
  )
}
