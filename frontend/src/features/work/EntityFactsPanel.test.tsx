import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import type { EntityFact, TicketDetail } from '../../lib/api/tickets'
import { EntityFactsPanel } from './EntityFactsPanel'
import { TicketHeader } from './TicketHeader'

const facts: EntityFact[] = [
  {
    entity_type: 'device',
    entity_id: 'd1',
    group_key: 'router',
    field_key: 'ssid_5g',
    label: 'SSID 5 GHz',
    value_text: 'TestVilla_5G',
    value_number: null,
    is_sensitive: false,
  },
  {
    entity_type: 'device',
    entity_id: 'd1',
    group_key: 'router',
    field_key: 'channel_5g',
    label: 'Channel 5 GHz',
    value_text: '44',
    value_number: 44,
    is_sensitive: false,
  },
]

const detail = {
  ticket: {
    id: 't1',
    source_event_id: 'e1',
    customer_id: 'c1',
    service_id: 's1',
    assigned_technician_id: 'u1',
    severity: 'high',
    status: 'open',
    summary: 'ONU offline',
    tm_ticket_no: 'TT-EVT-1',
    ctt_activity_id: 'CTT-RTR-1',
    login_id: 'CUST-1',
    ticket_category: 'ONU_OFFLINE',
    ticket_created_at: '2026-10-12T09:51:52Z',
    staff_code: 'TM1234',
  },
  assigned_technician_name: 'Demo Technician',
  customer: { id: 'c1', customer_ref: 'CUST-1', name: 'Sample', address: '1 Way', is_demo: true },
  services: [],
  devices: [],
} as unknown as TicketDetail

describe('EntityFactsPanel', () => {
  it('renders the requested group with numeric values formatted from value_number', () => {
    render(<EntityFactsPanel facts={facts} groupKey="router" />)

    expect(screen.getByText('Router details')).toBeInTheDocument()
    expect(screen.getByText('SSID 5 GHz')).toBeInTheDocument()
    expect(screen.getByText('TestVilla_5G')).toBeInTheDocument()
    expect(screen.getByText('44')).toBeInTheDocument()
  })

  it('renders nothing for a group that has no facts', () => {
    const { container } = render(<EntityFactsPanel facts={facts} groupKey="optical" />)
    expect(container).toBeEmptyDOMElement()
  })
})

describe('TicketHeader operations block', () => {
  it('shows TMFORCE fields and the staff code', () => {
    render(<TicketHeader detail={detail} />)

    expect(screen.getByText('Ticket operations')).toBeInTheDocument()
    expect(screen.getAllByText('TT-EVT-1')[0]).toBeInTheDocument()
    expect(screen.getByText('CTT-RTR-1')).toBeInTheDocument()
    expect(screen.getByText('ONU_OFFLINE')).toBeInTheDocument()
    expect(screen.getAllByText('TM1234')[0]).toBeInTheDocument()
  })
})
