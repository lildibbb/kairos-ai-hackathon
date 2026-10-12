import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { AppointmentPicker } from './AppointmentPicker'

const ticketId = '10000000-0000-4000-8000-000000000001'
const slotId = '20000000-0000-4000-8000-000000000001'
const requestId = '30000000-0000-4000-8000-000000000001'
const slot = { slot_id: slotId, starts_at: '2026-10-13T02:00:00Z', ends_at: '2026-10-13T04:00:00Z' }
const booking = { ...slot, id: '40000000-0000-4000-8000-000000000001', ticket_id: ticketId, status: 'confirmed' }
const available = { timezone: 'Asia/Kuala_Lumpur', slots: [slot], appointment: null }

describe('appointment selection', () => {
  beforeEach(() => { vi.stubGlobal('fetch', vi.fn()); vi.stubGlobal('crypto', { randomUUID: () => requestId }) })
  afterEach(() => vi.unstubAllGlobals())

  it('confirms only after a successful booking response and displays Malaysia time', async () => {
    vi.mocked(fetch).mockResolvedValueOnce(new Response(JSON.stringify(available)))
      .mockResolvedValueOnce(new Response(JSON.stringify(booking)))
      .mockResolvedValueOnce(new Response(JSON.stringify({ ...available, slots: [], appointment: booking })))
    const onChange = vi.fn()
    render(<AppointmentPicker ticketId={ticketId} token="token" onChange={onChange} />)
    const user = userEvent.setup()
    expect(screen.queryByText('Confirmed')).not.toBeInTheDocument()
    await user.click(await screen.findByRole('button', { name: 'Confirm appointment' }))
    expect(await screen.findByText('Confirmed')).toBeInTheDocument()
    expect(screen.getByText(/10:00 - 12:00 \(Malaysia time\)/)).toBeInTheDocument()
    expect(JSON.parse(vi.mocked(fetch).mock.calls[1][1]?.body as string)).toEqual({ slot_id: slotId, request_id: requestId })
    expect(onChange).toHaveBeenCalledWith(booking)
  })

  it('refreshes alternatives after a conflict without confirming a booking', async () => {
    vi.mocked(fetch).mockResolvedValueOnce(new Response(JSON.stringify(available)))
      .mockResolvedValueOnce(new Response(JSON.stringify({ detail: 'That visit window was just booked. Please choose another time.' }), { status: 409 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ ...available, slots: [] })))
    render(<AppointmentPicker ticketId={ticketId} token="token" onChange={vi.fn()} />)
    await userEvent.setup().click(await screen.findByRole('button', { name: 'Confirm appointment' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('just booked')
    await waitFor(() => expect(screen.getByText(/No visit windows/)).toBeInTheDocument())
    expect(screen.queryByText('Confirmed')).not.toBeInTheDocument()
  })

  it('retries an uncertain transport failure with the same request id', async () => {
    vi.mocked(fetch).mockResolvedValueOnce(new Response(JSON.stringify(available)))
      .mockRejectedValueOnce(new Error('network'))
      .mockResolvedValueOnce(new Response(JSON.stringify(booking)))
      .mockResolvedValueOnce(new Response(JSON.stringify({ ...available, slots: [], appointment: booking })))
    render(<AppointmentPicker ticketId={ticketId} token="token" onChange={vi.fn()} />)
    const user = userEvent.setup()
    await user.click(await screen.findByRole('button', { name: 'Confirm appointment' }))
    await user.click(await screen.findByRole('button', { name: 'Retry booking' }))
    expect(await screen.findByText('Confirmed')).toBeInTheDocument()
    expect(vi.mocked(fetch).mock.calls[1][1]?.body).toBe(vi.mocked(fetch).mock.calls[2][1]?.body)
  })

  it('cancels only after confirmation and leaves the ticket open', async () => {
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    vi.mocked(fetch).mockResolvedValueOnce(new Response(JSON.stringify({ ...available, appointment: booking })))
      .mockResolvedValueOnce(new Response(JSON.stringify({ ...booking, status: 'cancelled' })))
      .mockResolvedValueOnce(new Response(JSON.stringify(available)))
    render(<AppointmentPicker ticketId={ticketId} token="token" onChange={vi.fn()} />)
    await userEvent.setup().click(await screen.findByRole('button', { name: 'Cancel appointment' }))
    expect(await screen.findByText(/Your appointment was cancelled/)).toBeInTheDocument()
    expect(vi.mocked(fetch).mock.calls[1][1]?.method).toBe('DELETE')
    vi.restoreAllMocks()
  })
})
