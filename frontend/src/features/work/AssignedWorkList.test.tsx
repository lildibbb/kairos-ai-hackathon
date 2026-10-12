import { act, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { AuthProvider } from '../auth/AuthProvider'
import { AssignedWorkList } from './AssignedWorkList'

const tickets = [{
  id: 'ticket-7', source_event_id: 'event-7', customer_id: 'customer-7',
  service_id: null, assigned_technician_id: 'tech-1', severity: 'high', status: 'open',
  summary: 'ONU offline at customer site', customer_ref: 'CUST-7',
  customer_name: 'Test customer', service_type: null, service_ref: null,
}]
const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status })
const view = () => <AuthProvider><MemoryRouter><Routes>
  <Route path="/" element={<AssignedWorkList />} />
  <Route path="/tickets/:ticketId" element={<h1>Ticket workspace</h1>} />
</Routes></MemoryRouter></AuthProvider>

beforeEach(() => window.sessionStorage.setItem('field-force-auth-session', JSON.stringify({
  accessToken: 'tech-token', userId: 'tech-1', role: 'technician', expiresAt: Date.now() + 60_000,
})))
afterEach(() => { vi.useRealTimers(); vi.unstubAllGlobals(); window.sessionStorage.clear() })

it('loads actual rows, keeps focus on rerender, and opens the returned ticket', async () => {
  const user = userEvent.setup()
  let resolve!: (response: Response) => void
  const fetchMock = vi.fn(() => new Promise<Response>(done => { resolve = done }))
  vi.stubGlobal('fetch', fetchMock)
  const { rerender } = render(view())
  expect(screen.getByRole('status')).toHaveTextContent('Loading your assigned tickets.')
  await act(async () => resolve(json(tickets)))
  const list = screen.getByRole('list', { name: 'Assigned tickets' })
  const row = within(list).getByRole('listitem')
  expect(row).toHaveTextContent('Test customer')
  expect(row).toHaveTextContent('CUST-7')
  const link = within(row).getByRole('link', { name: 'Open ticket: ONU offline at customer site' })
  expect(link).toHaveAttribute('href', '/tickets/ticket-7')
  await waitFor(() => expect(row).toHaveStyle({ opacity: '1', transform: 'none' }))
  for (let index = 0; index < 7; index += 1) await user.tab()
  expect(link).toHaveFocus()
  rerender(view())
  expect(within(list).getByRole('listitem')).toBe(row)
  expect(row).toHaveStyle({ opacity: '1', transform: 'none' })
  expect(link).toHaveFocus()
  expect(fetchMock).toHaveBeenCalledTimes(1)
  await user.keyboard('{Enter}')
  expect(screen.getByRole('heading', { name: 'Ticket workspace' })).toBeInTheDocument()
})

it('shows load failure and retries to the empty state', async () => {
  const user = userEvent.setup()
  vi.stubGlobal('fetch', vi.fn().mockResolvedValueOnce(json({}, 500)).mockResolvedValueOnce(json([])))
  render(view())
  expect(await screen.findByRole('alert')).toHaveTextContent('The assigned work list could not be loaded.')
  await user.click(screen.getByRole('button', { name: 'Retry loading assigned work' }))
  expect(await screen.findByRole('heading', { name: 'No assigned tickets' })).toBeInTheDocument()
  expect(screen.queryByRole('link')).not.toBeInTheDocument()
})

it('renders returned rows immediately with reduced motion', async () => {
  vi.stubGlobal('matchMedia', vi.fn(() => ({ matches: true, addListener: vi.fn(), removeListener: vi.fn() })))
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(json(tickets)))
  render(view())
  const row = await screen.findByRole('listitem')
  expect(row).toHaveStyle({ opacity: '1', transform: 'none' })
  expect(within(row).getByRole('link')).toHaveAttribute('href', '/tickets/ticket-7')
})

it('refreshes on focus and finds a newly assigned ticket by the customer reference', async () => {
  const user = userEvent.setup()
  const customerTicket = { ...tickets[0], id: 'customer-ticket', summary: 'Customer reports slow internet',
    tm_ticket_no: 'INC-INTERNAL', customer_report_reference: 'TT-CUSTOMER-123' }
  const fetchMock = vi.fn().mockResolvedValueOnce(json(tickets)).mockResolvedValueOnce(json([...tickets, customerTicket]))
  vi.stubGlobal('fetch', fetchMock)
  render(view())
  await screen.findByRole('list', { name: 'Assigned tickets' })
  act(() => window.dispatchEvent(new Event('focus')))
  expect(await screen.findByText('TT-CUSTOMER-123')).toBeInTheDocument()
  await user.type(screen.getByRole('searchbox', { name: 'Search assigned tickets' }), 'TT-CUSTOMER-123')
  expect(screen.getAllByRole('listitem')).toHaveLength(1)
  expect(screen.getByRole('link', { name: 'Open ticket: Customer reports slow internet' })).toHaveAttribute('href', '/tickets/customer-ticket')
})

it('keeps the current queue when a background refresh fails and supports manual retry', async () => {
  const user = userEvent.setup()
  vi.stubGlobal('fetch', vi.fn().mockResolvedValueOnce(json(tickets))
    .mockResolvedValueOnce(json({}, 500)).mockResolvedValueOnce(json(tickets)))
  render(view())
  await screen.findByRole('list', { name: 'Assigned tickets' })
  expect(screen.getByRole('button', { name: 'Refresh assigned tickets' }).closest('.queue-heading-note')).toBeNull()
  await user.click(screen.getByRole('button', { name: 'Refresh assigned tickets' }))
  expect(await screen.findByRole('alert')).toBeInTheDocument()
  expect(screen.getByRole('list', { name: 'Assigned tickets' })).toBeInTheDocument()
  await user.click(screen.getByRole('button', { name: 'Refresh assigned tickets' }))
  await waitFor(() => expect(screen.queryByRole('alert')).not.toBeInTheDocument())
})

it('polls while visible and removes its refresh listeners on unmount', async () => {
  const fetchMock = vi.fn().mockResolvedValue(json(tickets))
  vi.stubGlobal('fetch', fetchMock)
  const { unmount } = render(view())
  await screen.findByRole('list', { name: 'Assigned tickets' })
  vi.useFakeTimers()
  // Remount so the polling timer is owned by the fake clock.
  unmount()
  const mounted = render(view())
  await act(async () => { await Promise.resolve() })
  await act(async () => { vi.advanceTimersByTime(30_000) })
  expect(fetchMock).toHaveBeenCalledTimes(3)
  mounted.unmount()
  act(() => { vi.advanceTimersByTime(30_000); window.dispatchEvent(new Event('focus')) })
  expect(fetchMock).toHaveBeenCalledTimes(3)
})
