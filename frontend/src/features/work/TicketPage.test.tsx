import { act, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, expect, it, vi } from 'vitest'
import { TicketPage } from './TicketPage'

vi.mock('../auth/AuthProvider', () => ({ useAuth: () => ({ session: { accessToken: 'token', role: 'technician' } }) }))
vi.mock('./TicketHeader', () => ({ TicketHeader: () => null }))
vi.mock('./CustomerServiceSummary', () => ({ CustomerServiceSummary: () => null }))
vi.mock('./SensitiveCredentialReveal', () => ({ SensitiveCredentialReveal: () => null }))
const device = { id: 'd1', device_ref: 'R1', name: 'Router', device_type: 'router', status: 'offline', credential_available: false }
vi.mock('../../lib/api/tickets', async (original) => ({
  ...await original<typeof import('../../lib/api/tickets')>(),
  fetchTicket: async () => ({ ticket: { id: 't1', source_event_id: 'e1' }, devices: [device], services: [], customer: {} }),
}))
vi.mock('../../lib/api/topology', () => ({ fetchTicketTopology: async () => ({ ticket_id: 't1', service_ref: 'svc-1', nodes: [{ device_id: 'd1', name: 'Access router', device_type: 'router', device_ref: 'R1', status: 'offline' }], edges: [] }) }))
const json = (value: unknown) => new Response(JSON.stringify(value))
const proposal = { id: 'p1', ticket_id: 't1', tool_name: 'reboot_router', device_id: 'd1', device_ref: 'R1', kind: 'stateful', requires_confirmation: true, parameters: {}, status: 'proposed', summary: 'Reboot router', confirmation_id: 'c1', created_at: '2026-10-12T12:00:00Z' }
afterEach(() => vi.unstubAllGlobals())

it('puts the labeled customer topology before the investigation workbench and exposes device selection', async () => {
  render(<MemoryRouter initialEntries={['/tickets/t1']}><Routes><Route path="/tickets/:ticketId" element={<TicketPage />} /></Routes></MemoryRouter>)
  const topology = await screen.findByRole('region', { name: 'Customer network topology' })
  expect(topology).toHaveTextContent('1 device · 0 connections')
  const deviceButton = within(topology).getByRole('button', { name: /Access router/ })
  const launcher = screen.getByRole('button', { name: 'Open AI assistant' })
  expect(topology.compareDocumentPosition(launcher) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
  await userEvent.setup().click(deviceButton)
  expect(deviceButton).toHaveAttribute('aria-pressed', 'true')
})

it('opens the AI assistant in a closable sidebar from Overview', async () => {
  render(<MemoryRouter initialEntries={['/tickets/t1']}><Routes><Route path="/tickets/:ticketId" element={<TicketPage />} /></Routes></MemoryRouter>)
  const user = userEvent.setup()
  await user.click(await screen.findByRole('button', { name: 'Open AI assistant' }))
  const drawer = screen.getByRole('dialog', { name: 'Investigate this incident' })
  expect(drawer).toBeVisible()
  await user.click(within(drawer).getByRole('button', { name: 'Close AI assistant' }))
  expect(document.querySelector('.assistant-drawer')).toHaveAttribute('aria-hidden', 'true')
})

it.each(['older-first', 'newer-first'])('latest-started action owns trace with %s responses', async (order) => {
  let resolveOlder!: (response: Response) => void
  let resolveNewer!: (response: Response) => void
  const older = new Promise<Response>((resolve) => { resolveOlder = resolve })
  const newer = new Promise<Response>((resolve) => { resolveNewer = resolve })
  vi.stubGlobal('fetch', vi.fn(async (url) => {
     if (String(url).endsWith('/assistant/messages')) return json({ session_id: 's1', answer: 'Check router', uncertainty: '', has_evidence: true, citations: [{ chunk_id: 'kb-1', document_id: 'doc-1', document_title: 'Router procedure', section: 'Checks', source_type: 'procedure', content: 'Check the router.', score: 0.9 }], next_best_action: null })
    if (String(url).endsWith('/catalog')) return json([{ name: 'get_device_status', title: 'Check status', description: 'Check status', kind: 'read_only', category: 'diagnostics', risk: 'low', requires_confirmation: false, target_device_types: null }])
    if (String(url).endsWith('/agent-plan')) return json({ ticket_id: 't1', question: '', device_id: 'd1', summary: 'Start here.', suggestions: [{ tool_name: 'reboot_router', title: 'Reboot home router', description: 'Reboot router', kind: 'stateful', category: 'diagnostics', risk: 'medium', requires_confirmation: true, device_id: 'd1', device_ref: 'R1', device_type: 'router', parameters: {}, rationale: 'Router is offline.', steps: [], evidence: [], confidence: 0.8 }] })
    if (String(url).endsWith('/agent-propose')) return json(proposal)
    if (String(url).endsWith('/confirm')) return newer
    return older
  }))
  const user = userEvent.setup()
  render(<MemoryRouter initialEntries={['/tickets/t1']}><Routes><Route path="/tickets/:ticketId" element={<TicketPage />} /></Routes></MemoryRouter>)
  await user.click(await screen.findByRole('button', { name: 'Open AI assistant' }))
  await user.click(await screen.findByRole('button', { name: 'What should I check first?' }))
   await screen.findByRole('button', { name: 'Prepare this action' })
  await user.click(await screen.findByRole('button', { name: 'Prepare this action' }))
  await screen.findByRole('button', { name: 'Approve and run' })
   const trace = within(screen.getByRole('list', { name: 'Incident trace' }))
  const action = trace.getByText('Action').closest('li')!
  await user.click(screen.getByRole('button', { name: 'Approve and run' }))
  const finishOlder = () => resolveOlder(json({ ...proposal, id: 'old', kind: 'read_only', requires_confirmation: false, status: 'succeeded', summary: 'Older check complete' }))
  const finishNewer = () => resolveNewer(json({ ...proposal, status: 'failed', message: 'Newer execution failed', correlation_id: 'c1', executed_at: proposal.created_at }))
  if (order === 'older-first') {
    await act(async () => finishOlder())
    expect(action).toHaveTextContent('Awaiting execution result')
    expect(action).not.toHaveTextContent('Complete')
    await act(async () => finishNewer())
  } else {
    await act(async () => finishNewer())
    await act(async () => finishOlder())
  }
  expect(action).toHaveTextContent('Blocked')
  expect(action).toHaveTextContent('Newer execution failed')
  expect(action).not.toHaveTextContent('Older check complete')
})

it('keeps evidence current when the newest overlapping question completes first', async () => {
  let resolveOlder!: (response: Response) => void
  let resolveNewer!: (response: Response) => void
  let markBothRequestsStarted!: () => void
  const bothRequestsStarted = new Promise<void>((resolve) => { markBothRequestsStarted = resolve })
  const older = new Promise<Response>((resolve) => { resolveOlder = resolve })
  const newer = new Promise<Response>((resolve) => { resolveNewer = resolve })
  let request = 0
  vi.stubGlobal('fetch', vi.fn((url) => {
    if (String(url).endsWith('/assistant/messages')) {
      request += 1
      if (request === 2) markBothRequestsStarted()
      return request === 1 ? older : newer
    }
    return Promise.resolve(json({}))
  }))
  const user = userEvent.setup()
  render(<MemoryRouter initialEntries={['/tickets/t1']}><Routes><Route path="/tickets/:ticketId" element={<TicketPage />} /></Routes></MemoryRouter>)
  await user.click(await screen.findByRole('button', { name: 'Open AI assistant' }))
  await user.click(await screen.findByRole('button', { name: 'What should I check first?' }))
  const composer = screen.getByRole('textbox', { name: 'Ask about this ticket' })
  await user.type(composer, 'Why is the service down?')
  await user.click(screen.getByRole('button', { name: 'Send question' }))
  await act(async () => bothRequestsStarted)
  const trace = within(screen.getByRole('list', { name: 'Incident trace' }))
  const evidence = trace.getByText('Evidence').closest('li')!
  await act(async () => resolveNewer(json({ session_id: 's1', answer: 'New result', uncertainty: '', has_evidence: true, citations: [], next_best_action: null })))
  expect(evidence).toHaveTextContent('Current')
  expect(evidence).toHaveTextContent('Investigation still in progress')
  expect(evidence).not.toHaveTextContent('Complete')
  expect(evidence).not.toHaveTextContent('Evidence returned')
  await act(async () => resolveOlder(json({ session_id: 's1', answer: 'Older result', uncertainty: '', has_evidence: true, citations: [], next_best_action: null })))
  expect(evidence).toHaveTextContent('Complete')
  expect(evidence).toHaveTextContent('Evidence returned')
})
