import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { CustomerChatPage } from './CustomerChatPage'

const auth = vi.hoisted(() => ({ session: { userId: 'customer-1', accessToken: 'test-token', role: 'customer' }, signOut: vi.fn() }))
vi.mock('../auth/AuthProvider', () => ({ useAuth: () => auth }))

const conversationId = '10000000-0000-4000-8000-000000000001'
const requestId = '20000000-0000-4000-8000-000000000001'
const answer = {
  conversation_id: conversationId, request_id: requestId, checked_at: '2026-10-12T01:00:00Z',
  answer: "Let's narrow the problem down together.",
  status: 'needs_live_check', report: null,
  findings: [{ code: 'weak_wifi', observation: 'Stored signal: -79 dBm.', interpretation: 'A live comparison is needed.', evidence_status: 'simulated', observed_at: '2026-10-12T01:00:00Z' }],
  follow_up: { id: 'device_scope', question: 'Every device or one device?', choices: [{ value: 'all_devices', label: 'Every device' }] },
}

describe('customer support chat', () => {
  beforeEach(() => {
    window.sessionStorage.clear()
    vi.stubGlobal('fetch', vi.fn())
    vi.stubGlobal('crypto', { randomUUID: vi.fn().mockReturnValueOnce(requestId).mockReturnValue('20000000-0000-4000-8000-000000000002') })
  })
  afterEach(() => { vi.unstubAllGlobals(); window.sessionStorage.clear() })

  it('submits an authenticated complaint and shows only the conversation and follow-up', async () => {
    vi.mocked(fetch).mockResolvedValueOnce(new Response(JSON.stringify(answer))).mockResolvedValueOnce(new Response(JSON.stringify({ ...answer, request_id: '20000000-0000-4000-8000-000000000002' })))
    render(<CustomerChatPage />)
    const user = userEvent.setup()
    await user.type(screen.getByLabelText('Your message'), 'My internet is slow')
    await user.click(screen.getByRole('button', { name: 'Send message' }))
    expect(await screen.findByText(answer.answer)).toBeInTheDocument()
    expect(screen.queryByText('Stored signal: -79 dBm.')).not.toBeInTheDocument()
    expect(screen.queryByText('Connection Assessment')).not.toBeInTheDocument()
    expect(screen.queryByText(/local prototype|local demo/i)).not.toBeInTheDocument()
    const [url, options] = vi.mocked(fetch).mock.calls[0]
    expect(url).toBe('/portal/me/chat/messages')
    expect(options?.headers).toMatchObject({ Authorization: 'Bearer test-token' })
    expect(JSON.parse(options?.body as string)).toMatchObject({ message: 'My internet is slow', request_id: requestId })
    expect(window.sessionStorage.getItem('customer-support-conversation:customer-1')).toBe(conversationId)
    await user.click(screen.getByRole('button', { name: 'Every device' }))
    await waitFor(() => expect(fetch).toHaveBeenCalledTimes(2))
    expect(JSON.parse(vi.mocked(fetch).mock.calls[1][1]?.body as string)).toMatchObject({ conversation_id: conversationId, answer_choice: 'all_devices' })
  })

  it('retries a failed request with the same id and preserves the complaint', async () => {
    vi.mocked(fetch).mockRejectedValueOnce(new Error('offline')).mockResolvedValueOnce(new Response(JSON.stringify(answer)))
    render(<CustomerChatPage />)
    const user = userEvent.setup()
    await user.type(screen.getByLabelText('Your message'), 'My internet is slow')
    await user.click(screen.getByRole('button', { name: 'Send message' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Check your connection')
    expect(screen.getByLabelText('Your message')).toHaveValue('My internet is slow')
    await user.click(screen.getByRole('button', { name: 'Retry message' }))
    expect(await screen.findByText(answer.answer)).toBeInTheDocument()
    expect(vi.mocked(fetch).mock.calls[0][1]?.body).toBe(vi.mocked(fetch).mock.calls[1][1]?.body)
  })

  it('binds the confirmation button to the server-issued action and keeps retry IDs', async () => {
    const actionId = '30000000-0000-4000-8000-000000000001'
    const pending = { ...answer, status: 'action_confirmation', answer: 'Please confirm the simulated restart.',
      router_action: { id: actionId, kind: 'reboot', label: 'Restart router', status: 'pending', simulation: true, expires_at: new Date(Date.now() + 600000).toISOString() },
      follow_up: { id: 'router_action_confirmation', question: 'Proceed?', choices: [{ value: 'confirm_router_action', label: 'Confirm action' }, { value: 'cancel_router_action', label: 'Cancel action' }] },
    }
    vi.mocked(fetch).mockResolvedValueOnce(new Response(JSON.stringify(pending)))
      .mockRejectedValueOnce(new Error('offline'))
      .mockResolvedValueOnce(new Response(JSON.stringify({ ...pending, request_id: '20000000-0000-4000-8000-000000000002', status: 'action_completed',
        router_action: { ...pending.router_action, status: 'succeeded' }, answer: 'Restart simulation complete. Please check your connection.',
        follow_up: { id: 'router_action_check', question: 'Has it improved?', choices: [{ value: 'resolved', label: "It's working now" }] },
      })))
    render(<CustomerChatPage />)
    const user = userEvent.setup()
    await user.type(screen.getByLabelText('Your message'), 'Restart my router')
    await user.click(screen.getByRole('button', { name: 'Send message' }))
    await user.click(await screen.findByRole('button', { name: 'Confirm action' }))
    expect(await screen.findByRole('alert')).toBeInTheDocument()
    const confirmation = vi.mocked(fetch).mock.calls[1][1]?.body
    expect(JSON.parse(confirmation as string)).toMatchObject({ action_id: actionId, answer_choice: 'confirm_router_action' })
    await user.click(screen.getByRole('button', { name: 'Retry message' }))
    expect(await screen.findByText('Restart simulation complete. Please check your connection.')).toBeInTheDocument()
    expect(vi.mocked(fetch).mock.calls[2][1]?.body).toBe(confirmation)
    expect(screen.getByText('Simulation')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Confirm action' })).not.toBeInTheDocument()
  })

  it('rejects an action response that claims to operate real equipment', async () => {
    vi.mocked(fetch).mockResolvedValue(new Response(JSON.stringify({ ...answer,
      router_action: { id: '30000000-0000-4000-8000-000000000001', kind: 'reboot', label: 'Restart', status: 'succeeded', simulation: false, expires_at: '' },
    })))
    render(<CustomerChatPage />)
    const user = userEvent.setup()
    await user.type(screen.getByLabelText('Your message'), 'Restart my router')
    await user.click(screen.getByRole('button', { name: 'Send message' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('unreadable answer')
  })

  it('restores server-owned history and can start a new conversation', async () => {
    window.sessionStorage.setItem('customer-support-conversation:customer-1', conversationId)
    vi.mocked(fetch).mockResolvedValue(new Response(JSON.stringify({ conversation_id: conversationId, turns: [{ message: 'Previous report', response: answer }] })))
    render(<CustomerChatPage />)
    expect(await screen.findByText('Previous report')).toBeInTheDocument()
    const user = userEvent.setup()
    await user.click(screen.getByRole('button', { name: 'New conversation' }))
    expect(screen.queryByText('Previous report')).not.toBeInTheDocument()
    expect(window.sessionStorage.getItem('customer-support-conversation:customer-1')).toBeNull()
  })

  it('does not display malformed report receipts', async () => {
    vi.mocked(fetch).mockResolvedValue(new Response(JSON.stringify({ ...answer, report: { reference: 'bad', status: 'router_rebooted' } })))
    render(<CustomerChatPage />)
    const user = userEvent.setup()
    await user.type(screen.getByLabelText('Your message'), 'slow internet')
    await user.click(screen.getByRole('button', { name: 'Send message' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('unreadable answer')
    expect(screen.queryByText(answer.answer)).not.toBeInTheDocument()
  })

  it('shows a ticket receipt without exposing the technician or household records', async () => {
    vi.mocked(fetch).mockResolvedValue(new Response(JSON.stringify({ ...answer, status: 'report_created', follow_up: null, report: { reference: 'TT-123', status: 'assigned' } })))
    render(<CustomerChatPage />)
    const user = userEvent.setup()
    await user.type(screen.getByLabelText('Your message'), 'My internet is slow')
    await user.click(screen.getByRole('button', { name: 'Send message' }))
    expect(await screen.findByText('TT-123')).toBeInTheDocument()
    expect(screen.getByText('Assigned for technician review')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Every device' })).not.toBeInTheDocument()
    expect(screen.queryByText('Stored signal: -79 dBm.')).not.toBeInTheDocument()
  })

  it('shows official sales options without inventing a price', async () => {
    vi.mocked(fetch).mockResolvedValue(new Response(JSON.stringify({ ...answer, status: 'sales_options', sales_options: [{
      id: 'official-mesh', name: 'Mesh Wi-Fi options', description: 'Explore current options.', official_url: 'https://unifi.com.my/lifestyle',
      monthly_price_myr: null, contract_months: null, eligibility_note: 'Confirm eligibility and terms before ordering.',
    }] })))
    render(<CustomerChatPage />)
    const user = userEvent.setup()
    await user.type(screen.getByLabelText('Your message'), 'Tell me about mesh')
    await user.click(screen.getByRole('button', { name: 'Send message' }))
    expect(await screen.findByRole('link', { name: 'View on Unifi' })).toHaveAttribute('href', 'https://unifi.com.my/lifestyle')
    expect(screen.queryByText(/RM /)).not.toBeInTheDocument()
  })

  it('rejects sales links outside approved official hosts', async () => {
    vi.mocked(fetch).mockResolvedValue(new Response(JSON.stringify({ ...answer, sales_options: [{
      id: 'malicious', name: 'Offer', description: 'Untrusted', official_url: 'https://unifi.com.my.evil.invalid/', eligibility_note: '',
    }] })))
    render(<CustomerChatPage />)
    const user = userEvent.setup()
    await user.type(screen.getByLabelText('Your message'), 'Tell me about mesh')
    await user.click(screen.getByRole('button', { name: 'Send message' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('unreadable answer')
    expect(screen.queryByRole('link')).not.toBeInTheDocument()
  })

  it('refreshes the chat receipt after booking, rescheduling and cancellation', async () => {
    const ticketId = '30000000-0000-4000-8000-000000000001'
    const slots = [
      { slot_id: '40000000-0000-4000-8000-000000000001', starts_at: '2026-10-13T02:00:00Z', ends_at: '2026-10-13T04:00:00Z' },
      { slot_id: '40000000-0000-4000-8000-000000000002', starts_at: '2026-10-13T05:00:00Z', ends_at: '2026-10-13T07:00:00Z' },
    ]
    let booked: (typeof slots[number] & { id: string; ticket_id: string; status: string }) | null = null
    const receipt = () => ({ ...answer, status: 'report_created', follow_up: null,
      report: { ticket_id: ticketId, reference: 'TT-123', status: 'assigned' },
      answer: booked ? `Your appointment is confirmed for ${booked.starts_at}.` : 'An appointment has not yet been confirmed.',
    })
    vi.mocked(fetch).mockImplementation(async (url, init) => {
      const path = String(url)
      if (path.endsWith('/chat/messages')) return new Response(JSON.stringify(receipt()))
      if (path.includes('/chat/conversations/')) return new Response(JSON.stringify({ conversation_id: conversationId, turns: [{ message: 'No internet', response: receipt() }] }))
      if (init?.method === 'POST') {
        const selection = JSON.parse(init.body as string)
        booked = { ...slots.find((slot) => slot.slot_id === selection.slot_id)!, id: selection.slot_id, ticket_id: ticketId, status: 'confirmed' }
        return new Response(JSON.stringify(booked))
      }
      if (init?.method === 'DELETE') {
        const cancelled = { ...booked!, status: 'cancelled' }
        booked = null
        return new Response(JSON.stringify(cancelled))
      }
      return new Response(JSON.stringify({ timezone: 'Asia/Kuala_Lumpur', slots: slots.filter((slot) => slot.slot_id !== booked?.slot_id), appointment: booked }))
    })
    const confirm = vi.spyOn(window, 'confirm').mockReturnValue(true)
    render(<CustomerChatPage />)
    const user = userEvent.setup()
    await user.type(screen.getByLabelText('Your message'), 'No internet')
    await user.click(screen.getByRole('button', { name: 'Send message' }))
    await user.click(await screen.findByRole('button', { name: 'Confirm appointment' }))
    expect(await screen.findByText(`Your appointment is confirmed for ${slots[0].starts_at}.`)).toBeInTheDocument()
    expect(screen.queryByText('An appointment has not yet been confirmed.')).not.toBeInTheDocument()
    await user.click(await screen.findByRole('button', { name: 'Reschedule appointment' }))
    expect(await screen.findByText(`Your appointment is confirmed for ${slots[1].starts_at}.`)).toBeInTheDocument()
    expect(screen.queryByText(`Your appointment is confirmed for ${slots[0].starts_at}.`)).not.toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Cancel appointment' }))
    expect(await screen.findByText('An appointment has not yet been confirmed.')).toBeInTheDocument()
    expect(screen.queryByText(`Your appointment is confirmed for ${slots[1].starts_at}.`)).not.toBeInTheDocument()
    confirm.mockRestore()
  })
})
