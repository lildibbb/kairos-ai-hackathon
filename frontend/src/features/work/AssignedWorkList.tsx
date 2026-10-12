import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'
import { gsap } from 'gsap'
import { Button } from '../../components/ui/button'
import { Card } from '../../components/ui/card'
import { Badge } from '../../components/ui/badge'
import { Skeleton } from '../../components/ui/skeleton'
import { Link } from 'react-router-dom'
import { useAuth } from '../auth/AuthProvider'
import { TicketsApiError, fetchMyTickets, type AssignedTicket } from '../../lib/api/tickets'
import { severityLabel, statusLabel } from './TicketHeader'
import { Funnel, MagnifyingGlass, ArrowUpRight } from '@phosphor-icons/react'
import { prefersReducedMotion } from '../../lib/motion'
import { NetworkOrb } from '../../components/illustration/NetworkOrb'

type LoadState = 'loading' | 'ready' | 'error'
type TicketFilter = 'all' | 'high' | 'open' | 'in-progress'

function modifier(value: string): string {
  return value.toLowerCase().replace(/[^a-z0-9]+/g, '-')
}

export function AssignedWorkList() {
  const dashboardRef = useRef<HTMLElement>(null)
  const { session } = useAuth()
  const token = session?.accessToken ?? ''
  const [tickets, setTickets] = useState<AssignedTicket[]>([])
  const [loadState, setLoadState] = useState<LoadState>('loading')
  const [loadError, setLoadError] = useState('')
  const [filter, setFilter] = useState<TicketFilter>('all')
  const [query, setQuery] = useState('')
  const [page, setPage] = useState(1)
  const pageSize = 8

  const load = useCallback(async (signal?: AbortSignal) => {
    setLoadState('loading')
    setLoadError('')
    try {
      const assigned = await fetchMyTickets(token, signal)
      setTickets(assigned)
      setLoadState('ready')
    } catch (error) {
      if (error instanceof DOMException && error.name === 'AbortError') return
      setLoadState('error')
      setLoadError(error instanceof TicketsApiError ? error.message : 'Assigned work could not be loaded.')
    }
  }, [token])

  useEffect(() => {
    const controller = new AbortController()
    void load(controller.signal)
    return () => controller.abort()
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
      const matchesQuery = !normalizedQuery || [ticket.summary, ticket.customer_name, ticket.customer_ref, ticket.service_type ?? '']
        .some((value) => value.toLowerCase().includes(normalizedQuery))
      return matchesFilter && matchesQuery
    })
  }, [filter, query, tickets])
  const pageCount = Math.max(1, Math.ceil(visibleTickets.length / pageSize))
  const pagedTickets = visibleTickets.slice((page - 1) * pageSize, page * pageSize)

  const filterOptions: Array<{ id: TicketFilter; label: string; count: number }> = [
    { id: 'all', label: 'All tickets', count: counts.all },
    { id: 'high', label: 'High severity', count: counts.high },
    { id: 'open', label: 'Open', count: counts.open },
    { id: 'in-progress', label: 'In progress', count: counts.inProgress },
  ]

  useLayoutEffect(() => {
    const root = dashboardRef.current
    if (loadState !== 'ready' || !root || prefersReducedMotion()) return
    if (!root.querySelector('.queue-metric')) return
    const context = gsap.context(() => {
      gsap.fromTo('.queue-hero-copy', { opacity: 0, y: 16 }, { opacity: 1, y: 0, duration: 0.4, ease: 'power3.out' })
      gsap.fromTo('.queue-signal-panel', { opacity: 0, scale: 0.94 }, { opacity: 1, scale: 1, duration: 0.6, delay: 0.08, ease: 'power3.out' })
      gsap.fromTo('.queue-metric', { opacity: 0, y: 12 }, { opacity: 1, y: 0, duration: 0.28, delay: 0.2, stagger: 0.06, ease: 'power3.out' })
      gsap.fromTo('.ticket-row', { opacity: 0, y: 10 }, { opacity: 1, y: 0, duration: 0.24, delay: 0.26, stagger: 0.04, ease: 'power3.out' })
    }, dashboardRef)
    return () => context.revert()
  }, [loadState])

  useEffect(() => { setPage(1) }, [filter, query])

  return (
    <section ref={dashboardRef} className="work-section assigned-work-dashboard" aria-labelledby="assigned-work-heading">
      <div className="work-dashboard-heading">
        <div className="queue-hero-copy">
          <p className="section-label">MY QUEUE</p>
          <h2 id="assigned-work-heading">Assigned tickets</h2>
          <p className="work-intro">Prioritize the incidents that need a response, then open a ticket for the full service path.</p>
        </div>
        <div className="queue-signal-panel" aria-label="Incident queue signal visualization">
          <NetworkOrb variant="compact" />
          <div className="queue-refresh">
            <span className="queue-refresh-indicator" aria-hidden="true" />
            <span>Live assignment queue</span>
          </div>
        </div>
      </div>

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
          <p>You have no open work right now. New tickets appear here when an operator processes an incident and assigns it to you.</p>
        </div>
      )}

      {loadState === 'ready' && tickets.length > 0 && (
        <div className="queue-layout">
          <div className="queue-metrics" aria-label="Ticket queue summary">
            <Card className="queue-metric queue-metric--primary"><span className="queue-metric-label">Assigned now</span><strong>{counts.all}</strong><span>tickets in your queue</span></Card>
            <Card className="queue-metric"><span className="queue-metric-label">Needs attention</span><strong>{counts.high}</strong><span>high severity</span></Card>
            <Card className="queue-metric"><span className="queue-metric-label">In progress</span><strong>{counts.inProgress}</strong><span>active investigations</span></Card>
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
              <div><p className="section-label">WORK ITEMS</p><h3>Assigned ticket register <span>{visibleTickets.length} shown</span></h3></div>
              <button className="sr-only" type="button" onClick={() => { setFilter('all'); setQuery('') }}>Reset ticket view</button>
            </div>
            {visibleTickets.length > 0 ? (
              <div className="ticket-table">
                <div className="ticket-table-cols" aria-hidden="true">
                  <span />
                  <span className="ticket-col-label">Ticket number</span>
                  <span className="ticket-col-label">Login ID</span>
                  <span className="ticket-col-label">Status</span>
                  <span className="ticket-col-label">Severity</span>
                  <span />
                </div>
                <ul className="ticket-list" aria-label="Assigned tickets">
                  {pagedTickets.map((ticket) => (
                    <li key={ticket.id} style={{ opacity: 1, transform: 'none' }}>
                      <Link className="ticket-row" to={`/tickets/${ticket.id}`} aria-label={`Open ticket: ${ticket.summary}`}>
                        <span className={`ticket-row-priority priority-${modifier(ticket.severity)}`} aria-hidden="true" />
                        <span className="ticket-row-main"><span className="ticket-row-summary tabular">{ticket.tm_ticket_no || ticket.id}</span></span>
                        <span className="ticket-row-login">{ticket.login_id || 'Login ID pending'}</span>
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
            {visibleTickets.length > 0 && <nav className="ticket-pagination" aria-label="Ticket pages"><span>Page {page} of {pageCount}</span><div><button type="button" disabled={page === 1} onClick={() => setPage(current => current - 1)}>Previous</button><button type="button" disabled={page === pageCount} onClick={() => setPage(current => current + 1)}>Next</button></div></nav>}
          </Card>
        </div>
      )}
    </section>
  )
}
