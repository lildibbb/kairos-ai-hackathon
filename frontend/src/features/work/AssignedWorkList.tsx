import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Button } from '../../components/ui/button'
import { Card } from '../../components/ui/card'
import { Badge } from '../../components/ui/badge'
import { Skeleton } from '../../components/ui/skeleton'
import { Link } from 'react-router-dom'
import { useAuth } from '../auth/AuthProvider'
import { TicketsApiError, fetchMyTickets, type AssignedTicket } from '../../lib/api/tickets'
import { severityLabel, statusLabel } from './TicketHeader'
import { Funnel, MagnifyingGlass, ArrowUpRight, ArrowClockwise } from '@phosphor-icons/react'

function appointmentLabel(value: NonNullable<AssignedTicket['appointment']>): string {
  const date = new Date(value.starts_at).toLocaleDateString('en-MY', { timeZone: 'Asia/Kuala_Lumpur', day: 'numeric', month: 'short' })
  const start = new Date(value.starts_at).toLocaleTimeString('en-MY', { timeZone: 'Asia/Kuala_Lumpur', hour: '2-digit', minute: '2-digit', hour12: false })
  const end = new Date(value.ends_at).toLocaleTimeString('en-MY', { timeZone: 'Asia/Kuala_Lumpur', hour: '2-digit', minute: '2-digit', hour12: false })
  return `${date}, ${start}-${end}`
}

type LoadState = 'loading' | 'ready' | 'error'
type TicketFilter = 'all' | 'high' | 'open' | 'in-progress'

function modifier(value: string): string {
  return value.toLowerCase().replace(/[^a-z0-9]+/g, '-')
}

export function AssignedWorkList() {
  const { session } = useAuth()
  const token = session?.accessToken ?? ''
  const [tickets, setTickets] = useState<AssignedTicket[]>([])
  const [loadState, setLoadState] = useState<LoadState>('loading')
  const [loadError, setLoadError] = useState('')
  const [refreshError, setRefreshError] = useState('')
  const [refreshing, setRefreshing] = useState(false)
  const request = useRef<AbortController | null>(null)
  const [filter, setFilter] = useState<TicketFilter>('all')
  const [query, setQuery] = useState('')
  const [page, setPage] = useState(1)
  const pageSize = 8

  const load = useCallback(async (background = false) => {
    if (request.current) return
    const controller = new AbortController()
    request.current = controller
    setRefreshing(true)
    if (!background) setLoadState('loading')
    setLoadError('')
    setRefreshError('')
    try {
      const assigned = await fetchMyTickets(token, controller.signal)
      if (controller.signal.aborted) return
      setTickets(assigned)
      setLoadState('ready')
    } catch (error) {
      if (controller.signal.aborted || (error instanceof DOMException && error.name === 'AbortError')) return
      const message = error instanceof TicketsApiError ? error.message : 'Assigned work could not be loaded.'
      if (background) setRefreshError(message)
      else {
        setLoadState('error')
        setLoadError(message)
      }
    } finally {
      if (request.current === controller) request.current = null
      if (!controller.signal.aborted) setRefreshing(false)
    }
  }, [token])

  useEffect(() => {
    void load()
    const refresh = () => {
      if (document.visibilityState === 'visible') void load(true)
    }
    const timer = window.setInterval(refresh, 30_000)
    window.addEventListener('focus', refresh)
    document.addEventListener('visibilitychange', refresh)
    return () => {
      window.clearInterval(timer)
      window.removeEventListener('focus', refresh)
      document.removeEventListener('visibilitychange', refresh)
      request.current?.abort()
      request.current = null
    }
  }, [load])

  const counts = useMemo(() => ({
    all: tickets.length,
    high: tickets.filter((ticket) => ticket.severity.toLowerCase() === 'high').length,
    open: tickets.filter((ticket) => ticket.status.toLowerCase() === 'open').length,
    inProgress: tickets.filter((ticket) => ['in_progress', 'in progress'].includes(ticket.status.toLowerCase())).length,
  }), [tickets])

  const visibleTickets = useMemo(() => {
    const normalizedQuery = query.trim().toLowerCase()
    return tickets.filter((ticket) => {
      const status = ticket.status.toLowerCase()
      const matchesFilter = filter === 'all'
        || (filter === 'high' && ticket.severity.toLowerCase() === 'high')
        || (filter === 'open' && status === 'open')
        || (filter === 'in-progress' && ['in_progress', 'in progress'].includes(status))
      const matchesQuery = !normalizedQuery || [ticket.summary, ticket.customer_name, ticket.customer_ref, ticket.service_type ?? '', ticket.tm_ticket_no ?? '', ticket.customer_report_reference ?? '', ticket.login_id ?? '', ticket.id]
        .some((value) => value.toLowerCase().includes(normalizedQuery))
      return matchesFilter && matchesQuery
    })
  }, [filter, query, tickets])
  const pageCount = Math.max(1, Math.ceil(visibleTickets.length / pageSize))
  const currentPage = Math.min(page, pageCount)
  const pagedTickets = visibleTickets.slice((currentPage - 1) * pageSize, currentPage * pageSize)

  const filterOptions: Array<{ id: TicketFilter; label: string; count: number }> = [
    { id: 'all', label: 'All tickets', count: counts.all },
    { id: 'high', label: 'High severity', count: counts.high },
    { id: 'open', label: 'Open', count: counts.open },
    { id: 'in-progress', label: 'In progress', count: counts.inProgress },
  ]

  useEffect(() => { setPage(1) }, [filter, query])

  return (
    <section className="work-section assigned-work-dashboard" aria-labelledby="assigned-work-heading">
      <div className="work-dashboard-heading">
        <div className="queue-hero-copy">
          <p className="section-label">Field operations / My queue</p>
          <h2 id="assigned-work-heading">Assigned tickets</h2>
          <p className="work-intro">Your next fix starts here. Pick an incident to investigate.</p>
        </div>
        <div className="flex shrink-0 items-center gap-4">
          <div className="queue-heading-note"><img src="/illustrations/network-device.svg" width="200" height="160" alt="" /><p>Follow the signal.<br /><strong>Find the next fix.</strong></p></div>
          <Button variant="quiet" className="h-10 w-10 shrink-0 p-0" type="button" aria-label="Refresh assigned tickets" title="Refresh assigned tickets" disabled={refreshing} onClick={() => void load(loadState === 'ready')}><ArrowClockwise size={20} /></Button>
        </div>
      </div>
      {refreshError && <p className="form-error" role="alert">{refreshError}</p>}

      {loadState === 'loading' && (
        <div className="state-panel queue-loading" role="status">
          <p className="sr-only">Loading your assigned tickets.</p>
          <Skeleton className="h-6 w-1/3" />
          <Skeleton className="h-20 w-full" />
          <Skeleton className="h-20 w-full" />
          <Skeleton className="h-20 w-full" />
        </div>
      )}

      {loadState === 'error' && (
        <div className="state-panel">
          <p className="form-error" role="alert">{loadError}</p>
          <Button className="process-button" type="button" onClick={() => void load()}>Retry loading assigned work</Button>
        </div>
      )}

      {loadState === 'ready' && tickets.length === 0 && (
        <div className="state-panel queue-empty-state">
          <h3>No assigned tickets</h3>
          <p>You have no assigned tickets right now.</p>
        </div>
      )}

      {loadState === 'ready' && tickets.length > 0 && (
        <div className="queue-layout">
          <div className="queue-metrics" aria-label="Ticket queue summary">
            <div className="queue-metric queue-metric--primary"><strong>{counts.all}</strong><span className="queue-metric-label">Assigned now</span></div>
            <div className="queue-metric"><strong>{counts.high}</strong><span className="queue-metric-label">High severity</span></div>
            <div className="queue-metric"><strong>{counts.inProgress}</strong><span className="queue-metric-label">In progress</span></div>
          </div>

          <div className="queue-toolbar">
            <div className="queue-filters" role="group" aria-label="Filter assigned tickets">
              <Funnel size={17} aria-hidden="true" />
              {filterOptions.map((option) => (
                <button key={option.id} type="button" className={`queue-filter ${filter === option.id ? 'is-active' : ''}`} onClick={() => setFilter(option.id)} aria-pressed={filter === option.id}>
                  {option.label}<Badge variant={filter === option.id ? 'default' : 'secondary'} className="queue-filter-count">{option.count}</Badge>
                </button>
              ))}
            </div>
            <label className="queue-search">
              <span className="sr-only">Search assigned tickets</span>
              <MagnifyingGlass size={18} aria-hidden="true" />
              <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search tickets" type="search" />
            </label>
          </div>

          <Card className="ticket-table-shell">
            <div className="ticket-table-heading">
              <div><p className="section-label">WORK ITEMS</p><h3>Your incidents <span>{visibleTickets.length} shown</span></h3></div>
              {(filter !== 'all' || query) && <button className="text-button" type="button" onClick={() => { setFilter('all'); setQuery('') }}>Reset ticket view</button>}
            </div>
            {visibleTickets.length > 0 ? (
              <div className="ticket-table">
                <div className="ticket-table-cols" aria-hidden="true">
                  <span />
                  <span className="ticket-col-label">Incident / ticket</span>
                  <span className="ticket-col-label">Customer / login</span>
                  <span className="ticket-col-label">Visit</span>
                  <span className="ticket-col-label">Status</span>
                  <span className="ticket-col-label">Severity</span>
                  <span />
                </div>
                <ul className="ticket-list" aria-label="Assigned tickets">
                  {pagedTickets.map((ticket) => (
                    <li key={ticket.id} style={{ opacity: 1, transform: 'none' }}>
                      <Link className="ticket-row" to={`/tickets/${ticket.id}`} aria-label={`Open ticket: ${ticket.summary}`}>
                        <span className={`ticket-row-priority priority-${modifier(ticket.severity)}`} aria-hidden="true" />
                        <span className="ticket-row-main"><span className="ticket-reference tabular">{ticket.customer_report_reference || ticket.tm_ticket_no || ticket.id}</span><span className="ticket-row-summary">{ticket.summary}</span></span>
                        <span className="ticket-row-login"><strong>{ticket.customer_name}</strong><span>{ticket.login_id || ticket.customer_ref}</span></span>
                        <span className="ticket-row-appointment">{ticket.appointment ? <><strong>Visit</strong><span>{appointmentLabel(ticket.appointment)}</span></> : <span>No visit booked</span>}</span>
                        <span className="sr-only">{ticket.customer_name} {ticket.customer_ref}</span>
                        <span className={`status-pill status-${modifier(ticket.status)}`}>{statusLabel(ticket.status)}</span>
                        <span className={`severity-pill severity-${modifier(ticket.severity)}`}>{severityLabel(ticket.severity)}</span>
                        <span className="ticket-row-open">View <ArrowUpRight size={14} aria-hidden="true" /></span>
                      </Link>
                    </li>
                  ))}
                </ul>
              </div>
            ) : (
              <div className="queue-filter-empty" role="status"><h4>No tickets match this view</h4><p>Try another filter or clear the search to return to your full assignment queue.</p><button type="button" className="text-button" onClick={() => { setFilter('all'); setQuery('') }}>Show all tickets</button></div>
            )}
            {visibleTickets.length > 0 && <nav className="ticket-pagination" aria-label="Ticket pages"><span>Page {currentPage} of {pageCount}</span><div><button type="button" disabled={currentPage === 1} onClick={() => setPage(currentPage - 1)}>Previous</button><button type="button" disabled={currentPage === pageCount} onClick={() => setPage(currentPage + 1)}>Next</button></div></nav>}
          </Card>
        </div>
      )}
    </section>
  )
}
