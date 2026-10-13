import { act, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { TroubleshootingAssistant } from './TroubleshootingAssistant'
import { askAssistantWithStream } from '../../lib/api/assistant'
import { writeConversation } from '../../lib/assistant/conversation-storage'

const CITED_ANSWER = {
  session_id: 'session-1',
  answer: 'Recommendation: inspect the optical path before dispatch.',
  uncertainty: 'Field conditions vary.',
  has_evidence: true,
  citations: [
    {
      chunk_id: 'kb-onu-offline-v1:1.0:inspect-optical-path',
      document_id: 'kb-onu-offline-v1',
      document_title: 'ONU Offline Field Checks',
      section: 'Inspect optical path',
      source_type: 'curated_procedure',
      content: 'Verify the patch lead is seated and inspect for visible bends or damage.',
      score: 0.82,
    },
  ],
  next_best_action: {
    remediation: 'Reseat the patch lead and recheck.',
    dispatch_required: false,
    suggestion: null,
    evidence: ['kb-onu-offline-v1:1.0:inspect-optical-path'],
    suggestion_evidence: [],
  },
}

const NO_EVIDENCE_ANSWER = {
  session_id: 'session-2',
  answer: 'No service guidance matched this question, so there is no cited procedure to rely on.',
  uncertainty: '',
  has_evidence: false,
  citations: [],
  next_best_action: null,
}

const DEVICES = [
  {
    id: 'device-router',
    device_ref: 'DEV-RTR-1',
    device_type: 'router',
    name: 'Customer router',
    status: 'unreachable',
    credential_available: false,
  },
]

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

describe('TroubleshootingAssistant', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn())
    window.sessionStorage.clear()
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    window.sessionStorage.clear()
  })

  it('renders a cited answer with an evidence panel after asking', async () => {
    vi.mocked(fetch).mockResolvedValue(jsonResponse(CITED_ANSWER))
    const user = userEvent.setup()
    render(<TroubleshootingAssistant ticketId="ticket-1" token="token" devices={DEVICES} />)

    await user.type(screen.getByLabelText('Ask about this ticket', { selector: 'textarea' }), 'Why is the ONU offline?')
    await user.click(screen.getByRole('button', { name: 'Send question' }))

    expect(
      await screen.findByText('Recommendation: inspect the optical path before dispatch.'),
    ).toBeInTheDocument()
    expect(screen.getByText('Retrieved evidence')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: /Retrieved evidence/ }))
    expect(screen.getByText('ONU Offline Field Checks')).toBeInTheDocument()
    expect(screen.getByText('Reseat the patch lead and recheck.')).toBeInTheDocument()
    expect(screen.getByRole('status')).toHaveTextContent('Completed')
    const citation = screen.getByText('ONU Offline Field Checks').closest('details')
    expect(citation).not.toHaveAttribute('open')
    await user.click(screen.getByText('ONU Offline Field Checks'))
    expect(citation).toHaveAttribute('open')
  })

  it('starts the ticket summary when investigation is requested by the workbench', async () => {
    vi.mocked(fetch).mockResolvedValue(jsonResponse(CITED_ANSWER))

    const view = render(<TroubleshootingAssistant ticketId="ticket-1" token="token" devices={DEVICES} investigationRequest={1} />)

    expect(await screen.findByText('Summarize this ticket')).toBeInTheDocument()
    expect(await screen.findByText(CITED_ANSWER.answer)).toBeInTheDocument()
    view.unmount()
  })

  it('restores this user’s ticket conversation after the assistant remounts', async () => {
    vi.mocked(fetch).mockResolvedValue(jsonResponse(NO_EVIDENCE_ANSWER))
    const props = { ticketId: 'ticket-1', token: 'token', userId: 'tech-1', devices: DEVICES }
    const user = userEvent.setup()
    const firstRender = render(<TroubleshootingAssistant {...props} />)

    await user.type(screen.getByLabelText('Ask about this ticket', { selector: 'textarea' }), 'Keep this investigation')
    await user.click(screen.getByRole('button', { name: 'Send question' }))
    expect(await screen.findByText(NO_EVIDENCE_ANSWER.answer)).toBeInTheDocument()
    firstRender.unmount()

    render(<TroubleshootingAssistant {...props} />)

    expect(screen.getByText('Keep this investigation')).toBeInTheDocument()
    expect(screen.getByText(NO_EVIDENCE_ANSWER.answer)).toBeInTheDocument()
    expect(fetch).toHaveBeenCalledTimes(1)
  })

  it('provides a labeled conversation log for scrolling through messages', async () => {
    vi.mocked(fetch).mockResolvedValue(jsonResponse(NO_EVIDENCE_ANSWER))
    const user = userEvent.setup()
    render(<TroubleshootingAssistant ticketId="ticket-1" token="token" devices={DEVICES} />)
    await user.click(screen.getByRole('button', { name: 'What should I check first?' }))

    expect(await screen.findByRole('log', { name: 'Ticket conversation' })).toHaveClass('assistant-conversation')
  })

  it('submits a starter question and a keyboard follow-up', async () => {
    vi.mocked(fetch).mockImplementation(() => Promise.resolve(jsonResponse(NO_EVIDENCE_ANSWER)))
    const user = userEvent.setup()
    render(<TroubleshootingAssistant ticketId="ticket-1" token="token" devices={DEVICES} />)

    await user.click(screen.getByRole('button', { name: 'What should I check first?' }))
    expect(await screen.findByText(NO_EVIDENCE_ANSWER.answer)).toBeInTheDocument()
    expect(screen.getByText('What should I check first?')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'What should I check first?' })).not.toBeInTheDocument()

    const input = screen.getByLabelText('Ask about this ticket', { selector: 'textarea' })
    await user.type(input, 'What about the router?')
    await user.keyboard('{Control>}{Enter}{/Control}')
    expect(await screen.findByText('What about the router?')).toBeInTheDocument()
    expect(input).toHaveValue('')
    // "check" is actionable, so the first answer also starts a plan request even though it cited
    // no knowledge source; the router follow-up is a plain question.
    await new Promise((r) => setTimeout(r, 500)); console.log('CALLS', vi.mocked(fetch).mock.calls.map(([u, i]) => `${u} ${String((i as RequestInit)?.body)}`))
    await waitForAssistantRequests(2)
    await vi.waitFor(() => expect(fetch).toHaveBeenCalledTimes(3))
  })

  it('keeps the composer available for a follow-up while a reply is pending', async () => {
    const pending: Array<(response: Response) => void> = []
    vi.mocked(fetch).mockImplementation(() => new Promise((resolve) => pending.push(resolve)))
    const user = userEvent.setup()
    render(<TroubleshootingAssistant ticketId="ticket-1" token="token" devices={DEVICES} />)

    await user.click(screen.getByRole('button', { name: 'What should I check first?' }))
    const input = screen.getByLabelText('Ask about this ticket', { selector: 'textarea' })
    expect(input).toBeEnabled()
    expect(screen.getByText(/You can ask a follow-up while the assistant responds/)).toBeInTheDocument()
    await user.type(input, 'Which device should I inspect?')
    await user.click(screen.getByRole('button', { name: 'Send question' }))

    expect(screen.getByText('Which device should I inspect?')).toBeInTheDocument()
    await waitForAssistantRequests(2)
    expect(fetch).toHaveBeenCalledTimes(2)
    await act(async () => pending.forEach((resolve) => resolve(jsonResponse(NO_EVIDENCE_ANSWER))))
  })

  it.each(['failure', 'no-evidence'] as const)(
    'keeps latest evidence progress when an older request resolves with %s',
    async (olderOutcome) => {
      const sockets: StubSocket[] = []
      class StubSocket extends EventTarget {
        constructor() { super(); sockets.push(this) }
        send = vi.fn()
        close() { this.dispatchEvent(new Event('close')) }
        emit(event: unknown) { this.dispatchEvent(new MessageEvent('message', { data: JSON.stringify(event) })) }
      }
      vi.stubGlobal('WebSocket', StubSocket)
      const onEvidenceProgress = vi.fn()
      const user = userEvent.setup()
      render(<TroubleshootingAssistant ticketId="ticket-1" token="token" devices={DEVICES} onEvidenceProgress={onEvidenceProgress} />)

      await user.click(screen.getByRole('button', { name: 'What should I check first?' }))
      await user.type(screen.getByLabelText('Ask about this ticket', { selector: 'textarea' }), 'Check the router too')
      await user.click(screen.getByRole('button', { name: 'Send question' }))

      await act(async () => {
        sockets[1].emit({ type: 'ready' })
        sockets[1].emit({ type: 'answer', data: CITED_ANSWER })
      })
      expect(onEvidenceProgress).toHaveBeenLastCalledWith(expect.objectContaining({ state: 'complete', detail: 'Evidence returned' }))

      await act(async () => {
        sockets[0].emit({ type: 'ready' })
        if (olderOutcome === 'failure') sockets[0].emit({ type: 'error', message: 'Older request failed' })
        else sockets[0].emit({ type: 'answer', data: NO_EVIDENCE_ANSWER })
      })

      expect(onEvidenceProgress).toHaveBeenLastCalledWith(expect.objectContaining({ state: 'complete', detail: 'Evidence returned' }))
      expect(screen.getByText(CITED_ANSWER.answer)).toBeInTheDocument()
      if (olderOutcome === 'no-evidence') expect(screen.getByText(NO_EVIDENCE_ANSWER.answer)).toBeInTheDocument()
        else expect(screen.getAllByRole('alert').some((node) => node.textContent?.includes('Older request failed'))).toBe(true)
    },
  )

  it('shows an explicit no-evidence response without a citation list', async () => {
    vi.mocked(fetch).mockResolvedValue(jsonResponse(NO_EVIDENCE_ANSWER))
    const user = userEvent.setup()
    render(<TroubleshootingAssistant ticketId="ticket-1" token="token" devices={DEVICES} />)

    await user.type(screen.getByLabelText('Ask about this ticket', { selector: 'textarea' }), 'A question with no matching guidance')
    await user.click(screen.getByRole('button', { name: 'Send question' }))

    expect(
      await screen.findByText('No service guidance matched this question, so there is no cited procedure to rely on.'),
    ).toBeInTheDocument()
    expect(screen.getByText(/no cited source/)).toBeInTheDocument()
    expect(screen.queryByText('Retrieved evidence')).not.toBeInTheDocument()
  })

  it('shows a retryable error when the assistant request fails', async () => {
    vi.mocked(fetch).mockResolvedValue(new Response('', { status: 502 }))
    const user = userEvent.setup()
    render(<TroubleshootingAssistant ticketId="ticket-1" token="token" devices={DEVICES} />)

    await user.type(screen.getByLabelText('Ask about this ticket', { selector: 'textarea' }), 'Why is the ONU offline?')
    await user.click(screen.getByRole('button', { name: 'Send question' }))

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'The assistant could not answer this question.',
    )
    expect(screen.getByRole('button', { name: 'Retry this question' })).toBeInTheDocument()
  })

  it('lets the agent plan, prepare and confirm an action before state changes', async () => {
    vi.mocked(fetch)
      .mockResolvedValueOnce(jsonResponse(CITED_ANSWER))
      .mockResolvedValueOnce(
        jsonResponse({
          ticket_id: 'ticket-1',
          question: 'Configure the router to change the channel',
          device_id: 'device-router',
          summary: 'Start with a reboot.',
          suggestions: [
            {
              tool_name: 'reboot_router',
              title: 'Reboot home router',
              description: 'Simulate a reboot of the customer home router.',
              kind: 'stateful',
              category: 'diagnostics',
              risk: 'medium',
              requires_confirmation: true,
              device_id: 'device-router',
              device_ref: 'DEV-RTR-1',
              device_type: 'router',
              parameters: {},
              rationale: 'The router is unreachable and the procedure ends with a reboot.',
              steps: [
                'Confirm the router is the affected device',
                'Reboot the home router',
                'Confirm the router returns online and services recover',
              ],
              evidence: ['kb-1'],
              confidence: 0.83,
            },
          ],
        }),
      )
      .mockResolvedValueOnce(
        jsonResponse({
          id: 'proposal-1',
          ticket_id: 'ticket-1',
          tool_name: 'reboot_router',
          device_id: 'device-router',
          device_ref: 'DEV-RTR-1',
          kind: 'stateful',
          requires_confirmation: true,
          parameters: { device_id: 'device-router' },
          status: 'proposed',
          summary: 'Reboot the customer router',
          confirmation_id: 'confirm-1',
          created_at: '2026-05-20T12:00:00Z',
        }),
      )
      .mockResolvedValueOnce(
        jsonResponse({
          id: 'proposal-1',
          ticket_id: 'ticket-1',
          tool_name: 'reboot_router',
          device_id: 'device-router',
          device_ref: 'DEV-RTR-1',
          status: 'succeeded',
          message: 'Customer router rebooted and is back online.',
          correlation_id: 'confirm-1',
          executed_at: '2026-05-20T12:01:00Z',
        }),
      )
    const user = userEvent.setup()
    render(<TroubleshootingAssistant ticketId="ticket-1" token="token" devices={DEVICES} />)

    await user.type(screen.getByLabelText('Ask about this ticket', { selector: 'textarea' }), 'Configure the router to change the channel')
    await user.click(screen.getByRole('button', { name: 'Send question' }))

    expect(await screen.findByText('Reboot home router')).toBeInTheDocument()
    expect(screen.getByText(/The router is unreachable and the procedure/)).toBeInTheDocument()
    expect(screen.getByText('Configuration plan')).toBeInTheDocument()
    expect(screen.getByText('Confirm the router returns online and services recover')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Prepare this action' }))

    expect(await screen.findByText('Reboot the customer router')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Approve and run' }))

    // The execute and verify phases are animated before the outcome is shown.
    expect((await screen.findAllByText('Customer router rebooted and is back online.', {}, { timeout: 6000 })).length).toBeGreaterThan(0)
    expect(screen.getByRole('region', { name: 'Tool call status' })).toHaveTextContent('reboot_router()')
    expect(fetch).toHaveBeenCalledTimes(4)
  })

  it('uses the assistant WebSocket and reports retrieval progress', async () => {
    class StubSocket extends EventTarget {
      readyState = 0

      constructor() {
        super()
        queueMicrotask(() => {
          this.readyState = 1
          this.dispatchEvent(new Event('open'))
          this.dispatchEvent(new MessageEvent('message', { data: JSON.stringify({ type: 'ready' }) }))
        })
      }

      send(message: string) {
        expect(JSON.parse(message)).toEqual({ question: 'Why is the ONU offline?' })
        this.dispatchEvent(new MessageEvent('message', { data: JSON.stringify({ type: 'retrieval_started' }) }))
        this.dispatchEvent(new MessageEvent('message', { data: JSON.stringify({ type: 'answer', data: CITED_ANSWER }) }))
      }

      close() {
        this.readyState = 3
        this.dispatchEvent(new Event('close'))
      }
    }
    vi.stubGlobal('WebSocket', StubSocket)
    const progress: string[] = []

    const answer = await askAssistantWithStream(
      'ticket-1',
      'Why is the ONU offline?',
      'token',
      (message) => progress.push(message),
    )

    expect(answer.answer).toBe(CITED_ANSWER.answer)
    expect(progress).toContain('Connecting to the ticket assistant...')
    expect(progress).toContain('Searching ticket evidence and service guidance...')
    expect(fetch).not.toHaveBeenCalled()
  })

  it('keeps retrieval in one row through stream failure, retry and no-evidence response', async () => {
    const sockets: StubSocket[] = []
    class StubSocket extends EventTarget {
      constructor() { super(); sockets.push(this) }
      send = vi.fn()
      close() { this.dispatchEvent(new Event('close')) }
      emit(event: unknown) { this.dispatchEvent(new MessageEvent('message', { data: JSON.stringify(event) })) }
    }
    vi.stubGlobal('WebSocket', StubSocket)
    const user = userEvent.setup()
    render(<TroubleshootingAssistant ticketId="ticket-1" token="token" devices={DEVICES} />)
    await user.click(screen.getByRole('button', { name: 'What should I check first?' }))
    const row = screen.getByRole('status')
    expect(screen.getByLabelText('Generating assistant response')).toBeInTheDocument()
    act(() => { sockets[0].emit({ type: 'ready' }); sockets[0].emit({ type: 'retrieval_started' }) })
    expect(row).toHaveTextContent('Searching ticket evidence and service guidance...')
    expect(row).toHaveTextContent('Pending')
    await act(async () => sockets[0].emit({ type: 'error', message: 'Retrieval unavailable' }))
    expect(screen.getByRole('status')).toBe(row)
    expect(row).toHaveTextContent('Failed')
    expect(screen.queryByLabelText('Generating assistant response')).not.toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Retry this question' }))
    expect(row).toHaveTextContent('Pending')
    expect(screen.getByLabelText('Generating assistant response')).toBeInTheDocument()
    act(() => sockets[1].emit({ type: 'ready' }))
    expect(sockets[1].send).toHaveBeenCalledWith(JSON.stringify({ question: 'What should I check first?' }))
    await act(async () => sockets[1].emit({ type: 'answer', data: NO_EVIDENCE_ANSWER }))
    expect(screen.getByRole('status')).toBe(row)
    expect(row).toHaveTextContent('No evidence')
    expect(screen.queryByLabelText('Generating assistant response')).not.toBeInTheDocument()
    expect(screen.getByText(NO_EVIDENCE_ANSWER.answer)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Retry this question' })).not.toBeInTheDocument()
  })

  it('ignores an old ticket response after switching tickets', async () => {
    let resolve!: (response: Response) => void
    vi.mocked(fetch).mockImplementationOnce(() => new Promise((done) => { resolve = done }))
    const user = userEvent.setup()
    const { rerender } = render(<TroubleshootingAssistant ticketId="ticket-1" token="token" devices={DEVICES} />)
    await user.click(screen.getByRole('button', { name: 'What should I check first?' }))
    rerender(<TroubleshootingAssistant ticketId="ticket-2" token="token" devices={DEVICES} />)
    await waitForAssistantRequests(1)
    await vi.waitFor(() => expect(resolve).toBeTypeOf('function'))
    await act(async () => resolve(jsonResponse(CITED_ANSWER)))
    expect(screen.queryByText(CITED_ANSWER.answer)).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'What should I check first?' })).toBeInTheDocument()
  })

  it.each(['close', 'malformed'] as const)('fails honestly on %s stream without HTTP replay', async (failure) => {
    let socket!: StubSocket
    class StubSocket extends EventTarget {
      constructor() { super(); socket = this }
      send = vi.fn()
      close() { this.dispatchEvent(new Event('close')) }
    }
    vi.stubGlobal('WebSocket', StubSocket)
    const user = userEvent.setup()
    render(<TroubleshootingAssistant ticketId="ticket-1" token="token" devices={DEVICES} />)
    await user.click(screen.getByRole('button', { name: 'What should I check first?' }))
    await act(async () => {
      socket.dispatchEvent(new MessageEvent('message', { data: JSON.stringify({ type: 'ready' }) }))
      if (failure === 'close') socket.close()
      else socket.dispatchEvent(new MessageEvent('message', { data: JSON.stringify({ type: 'answer', data: {} }) }))
    })
    expect(screen.getByRole('status')).toHaveTextContent(failure === 'close' ? 'Outcome not confirmed' : 'Failed')
    expect(screen.getByRole('button', { name: 'Retry this question' })).toBeEnabled()
    expect(assistantMessageRequests()).toHaveLength(0)
  })
})

function assistantMessageRequests() {
  return vi.mocked(fetch).mock.calls.filter(([input]) =>
    String(input).endsWith('/assistant/messages'),
  )
}

it('restores an unconfirmed action warning without offering its previous approval again', () => {
  writeConversation('restore-user', 'restore-ticket', [{ id: 1, question: 'Check router', state: 'answered', activity: 'completed', answer: CITED_ANSWER,
    message: 'Outcome not confirmed for reboot_router. Proposal reference: p1. Check audit history before preparing another action.',
    action: { plan: null, proposal: null, execution: null, rejected: false, attempts: [] },
  }])
  render(<TroubleshootingAssistant ticketId="restore-ticket" token="token" userId="restore-user" devices={DEVICES} />)
  expect(screen.getAllByText(/Outcome not confirmed for reboot_router/).length).toBeGreaterThan(0)
  expect(screen.queryByRole('button', { name: 'Approve and run' })).not.toBeInTheDocument()
})

async function waitForAssistantRequests(count: number) {
  await vi.waitFor(() => expect(assistantMessageRequests()).toHaveLength(count))
}
