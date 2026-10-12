import type { TicketDetail } from '../../lib/api/tickets'
import { Badge } from '../../components/ui/badge'

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

type TicketHeaderProps = {
  detail: TicketDetail
}

export function TicketHeader({ detail }: TicketHeaderProps) {
  const { ticket, customer, assigned_technician_name } = detail

  return (
    <section className="panel ticket-header" aria-labelledby="ticket-heading">
      <h2 id="ticket-heading">{ticket.summary}</h2>
      <p className="ticket-status-line">
        <Badge className={`status-pill status-${modifier(ticket.status)}`} variant={statusBadgeVariant(ticket.status)}>{statusLabel(ticket.status)}</Badge>
        <Badge className={`severity-pill severity-${modifier(ticket.severity)}`} variant={severityBadgeVariant(ticket.severity)}>
          {severityLabel(ticket.severity)}
        </Badge>
      </p>
      <dl className="data-list">
        <div className="data-row">
          <dt>Customer</dt>
          <dd>
            {customer.name} <span className="tabular">({customer.customer_ref})</span>
          </dd>
        </div>
        <div className="data-row">
          <dt>Assigned technician</dt>
          <dd>{assigned_technician_name || 'Unassigned'}</dd>
        </div>
        <div className="data-row">
          <dt>Source event</dt>
          <dd className="tabular">{ticket.source_event_id}</dd>
        </div>
      </dl>

      {(ticket.tm_ticket_no || ticket.ctt_activity_id || ticket.login_id || ticket.ticket_category) && (
        <details className="ticket-operations">
          <summary>Ticket operations</summary>
          <dl className="data-list">
            {ticket.tm_ticket_no && (
              <div className="data-row">
                <dt>Ticket number</dt>
                <dd className="tabular">{ticket.tm_ticket_no}</dd>
              </div>
            )}
            {ticket.ctt_activity_id && (
              <div className="data-row">
                <dt>Activity ID (CTT)</dt>
                <dd className="tabular">{ticket.ctt_activity_id}</dd>
              </div>
            )}
            {ticket.login_id && (
              <div className="data-row">
                <dt>Login ID</dt>
                <dd className="tabular">{ticket.login_id}</dd>
              </div>
            )}
            {ticket.ticket_category && (
              <div className="data-row">
                <dt>Category</dt>
                <dd>{ticket.ticket_category}</dd>
              </div>
            )}
            {assigned_technician_name && (
              <div className="data-row">
                <dt>Staff</dt>
                <dd>
                  {assigned_technician_name}
                  {ticket.staff_code ? <span className="tabular"> ({ticket.staff_code})</span> : null}
                </dd>
              </div>
            )}
            {ticket.ticket_created_at && (
              <div className="data-row">
                <dt>Created</dt>
                <dd className="tabular">{ticket.ticket_created_at}</dd>
              </div>
            )}
          </dl>
        </details>
      )}
    </section>
  )
}
