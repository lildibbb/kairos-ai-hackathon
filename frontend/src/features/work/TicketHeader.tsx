import type { TicketDetail } from '../../lib/api/tickets'
import { Badge } from '../../components/ui/badge'
import { categoryInfo, readableSummary } from '../../lib/ticketCategory'

function statusBadgeVariant(status: string): 'success' | 'warning' | 'error' | 'secondary' {
  switch (status.toLowerCase()) {
    case 'active':
    case 'online':
    case 'resolved':
      return 'success'
    case 'in_progress':
    case 'in progress':
    case 'unknown':
    case 'degraded':
      return 'warning'
    case 'offline':
    case 'unreachable':
    case 'suspended':
      return 'error'
    default:
      return 'secondary'
  }
}

function severityBadgeVariant(severity: string): 'success' | 'warning' | 'error' | 'secondary' {
  switch (severity.toLowerCase()) {
    case 'high':
      return 'error'
    case 'medium':
      return 'warning'
    default:
      return 'secondary'
  }
}

export function statusLabel(status: string): string {
  switch (status.toLowerCase()) {
    case 'open':
      return 'Open'
    case 'in_progress':
    case 'in progress':
      return 'In progress'
    case 'resolved':
      return 'Resolved'
    case 'closed':
      return 'Closed'
    case 'active':
      return 'Active'
    case 'suspended':
      return 'Suspended'
    default:
      return status.replace(/_/g, ' ')
  }
}

export function severityLabel(severity: string): string {
  switch (severity.toLowerCase()) {
    case 'high':
      return 'High severity'
    case 'medium':
      return 'Medium severity'
    case 'low':
      return 'Low severity'
    default:
      return severity
  }
}

function modifier(value: string): string {
  return value.toLowerCase().replace(/[^a-z0-9]+/g, '-')
}

function appointmentDate(value: string): string {
  return new Date(value).toLocaleDateString('en-MY', {
    timeZone: 'Asia/Kuala_Lumpur', weekday: 'short', day: 'numeric', month: 'short', year: 'numeric',
  })
}

function appointmentTime(value: string): string {
  return new Date(value).toLocaleTimeString('en-MY', {
    timeZone: 'Asia/Kuala_Lumpur', hour: '2-digit', minute: '2-digit', hour12: false,
  })
}

function initials(name: string): string {
  return name.split(/\s+/).filter((word) => /^[A-Za-z]/.test(word) && !/^(a\/l|a\/p|bin|binti)$/i.test(word))
    .slice(0, 2).map((word) => word[0].toUpperCase()).join('')
}

function createdLabel(value: string): string {
  return new Date(value).toLocaleString('en-MY', {
    timeZone: 'Asia/Kuala_Lumpur', day: 'numeric', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit', hour12: false,
  })
}

type TicketHeaderProps = {
  detail: TicketDetail
}

export function TicketHeader({ detail }: TicketHeaderProps) {
  const { ticket, customer, assigned_technician_name } = detail
  const category = ticket.ticket_category ? categoryInfo(ticket.ticket_category) : undefined
  const operations = [
    ticket.tm_ticket_no && { label: 'Ticket number', value: ticket.tm_ticket_no, mono: true },
    ticket.ctt_activity_id && { label: 'Activity ID (CTT)', value: ticket.ctt_activity_id, mono: true },
    ticket.login_id && { label: 'Login ID', value: ticket.login_id, mono: true },
    ticket.ticket_category && { label: 'Event code', value: ticket.ticket_category, mono: true, title: category?.meaning },
    ticket.staff_code && { label: 'Staff code', value: ticket.staff_code, mono: true },
    ticket.ticket_created_at && { label: 'Created', value: `${createdLabel(ticket.ticket_created_at)} MYT`, title: ticket.ticket_created_at },
    { label: 'Source event', value: ticket.source_event_id, mono: true },
  ].filter(Boolean) as { label: string; value: string; mono?: boolean; code?: string; title?: string }[]

  return (
    <section className="panel ticket-header ticket-hero" aria-labelledby="ticket-heading">
      <h2 id="ticket-heading">{readableSummary(ticket.summary)}</h2>
      <p className="ticket-status-line">
        <Badge className={`status-pill status-${modifier(ticket.status)}`} variant={statusBadgeVariant(ticket.status)}>{statusLabel(ticket.status)}</Badge>
        <Badge className={`severity-pill severity-${modifier(ticket.severity)}`} variant={severityBadgeVariant(ticket.severity)}>
          {severityLabel(ticket.severity)}
        </Badge>
        <span className="ticket-ref tabular">{ticket.tm_ticket_no || ticket.id}</span>
      </p>
      {category?.meaning && <p className="ticket-category-meaning">{category.meaning}</p>}

      <div className="ticket-people">
        <div className="ticket-person">
          <span className="ticket-avatar" aria-hidden="true">{initials(customer.name)}</span>
          <div>
            <small>Customer</small>
            <strong>{customer.name}</strong>
            <span className="tabular">{customer.customer_ref}</span>
          </div>
        </div>
        <div className="ticket-person">
          <span className="ticket-avatar is-staff" aria-hidden="true">{assigned_technician_name ? initials(assigned_technician_name) : '?'}</span>
          <div>
            <small>Assigned technician</small>
            <strong>{assigned_technician_name || 'Unassigned'}</strong>
            {ticket.staff_code && <span className="tabular">{ticket.staff_code}</span>}
          </div>
        </div>
        {detail.appointment && <div className="ticket-person ticket-appointment is-booked">
          <span className="ticket-avatar is-calendar" aria-hidden="true">{new Date(detail.appointment.starts_at).toLocaleDateString('en-MY', { timeZone: 'Asia/Kuala_Lumpur', day: 'numeric' })}</span>
          <div>
            <small>Technician appointment</small>
            <strong>{appointmentDate(detail.appointment.starts_at)}</strong>
            <span>{appointmentTime(detail.appointment.starts_at)} - {appointmentTime(detail.appointment.ends_at)} (Malaysia time)</span>
          </div>
        </div>}
      </div>

      <details className="ticket-operations">
        <summary>Ticket operations <span>{operations.length} fields</span></summary>
        <dl className="ticket-ops-grid">
          {operations.map((item) => (
            <div key={item.label} className="ticket-ops-item">
              <dt>{item.label}</dt>
              <dd className={item.mono ? 'tabular' : undefined} title={item.title ?? item.code}>{item.value}</dd>
            </div>
          ))}
        </dl>
      </details>
    </section>
  )
}
