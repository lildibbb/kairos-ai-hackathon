import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ReportCheckerPage } from './ReportCheckerPage'

const auth = vi.hoisted(() => ({ session: { userId: 'operator', accessToken: 'operator-token', role: 'operator' }, signOut: vi.fn() }))
vi.mock('../auth/AuthProvider', () => ({ useAuth: () => auth }))
const id = '10000000-0000-4000-8000-000000000001'
const row = { id, customer_ref: 'SYN-00042-0002', customer_name: 'Demo Customer', created_at: '2026-10-12T01:00:00Z', turn_count: 2, status: 'report_created', is_demo: true,
  report: { reference: 'DEMO-TT-123', status: 'assigned', area: 'Demo West', technician: 'Demo Technician', reason: 'customer_reported_persistent_issue_after_checks' } }
const detail = { turns: [{ message: 'Still not working', response: { conversation_id: id, request_id: id, checked_at: row.created_at, answer: 'Ticket recorded.', status: 'report_created', follow_up: null, report: { reference: 'DEMO-TT-123', status: 'assigned', is_demo: true }, is_demo: true,
  findings: [{ code: 'weak_wifi', observation: '-79 dBm', interpretation: 'Needs live verification', evidence_status: 'stale', observed_at: row.created_at }], warnings: ['Demo readings only'], mode: 'hosted', knowledge_status: 'available', response_mode: 'hosted' } }] }

describe('read-only report checker', () => {
  beforeEach(() => vi.stubGlobal('fetch', vi.fn().mockImplementation((url: string) => Promise.resolve(new Response(JSON.stringify(url.endsWith(id) ? detail : [row]))))))
  afterEach(() => vi.unstubAllGlobals())
  it('shows internal evidence and routing, with no editing controls', async () => {
    render(<ReportCheckerPage />)
    expect(await screen.findByText('-79 dBm')).toBeInTheDocument()
    expect(screen.getByText('Demo Technician')).toBeInTheDocument()
    expect(screen.getByText('DEMO-TT-123')).toBeInTheDocument()
    expect(screen.getByText(/Reply: hosted/)).toBeInTheDocument()
    expect(vi.mocked(fetch).mock.calls[0][1]?.headers).toMatchObject({ Authorization: 'Bearer operator-token' })
    expect(screen.queryByRole('button', { name: /assign|reboot|delete|save/i })).not.toBeInTheDocument()
    const user = userEvent.setup()
    await user.selectOptions(screen.getByRole('combobox'), 'resolved')
    expect(screen.getByText('No conversations in this view.')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Refresh reports' }))
    expect(fetch).toHaveBeenCalledTimes(4)
  })
})
