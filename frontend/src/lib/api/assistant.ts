import { z } from 'zod'
import { TicketsApiError } from './tickets'

const citationSchema = z.object({
  chunk_id: z.string().min(1),
  document_id: z.string().min(1),
  document_title: z.string(),
  section: z.string(),
  source_type: z.string(),
  content: z.string(),
  score: z.number(),
})

const nextBestActionSchema = z.object({
  remediation: z.string().nullable(),
  dispatch_required: z.boolean(),
  suggestion: z.string().nullable(),
  evidence: z.array(z.string()),
  suggestion_evidence: z.array(z.string()),
})

export const assistantSummarySchema = z.object({
  problem: z.string(),
  solution: z.string().nullable(),
  product_recommendation: z.string().nullable(),
  actions: z.array(z.string()),
})

export const assistantAnswerSchema = z.object({
  session_id: z.string().min(1),
  answer: z.string(),
  uncertainty: z.string(),
  has_evidence: z.boolean(),
  citations: z.array(citationSchema),
  next_best_action: nextBestActionSchema.nullable(),
  summary: assistantSummarySchema.nullable().optional(),
  action_intent: z.string().nullable().optional(),
})

export const assistantStepSchema = z.object({
  id: z.string(),
  label: z.string(),
  status: z.enum(['running', 'done', 'skipped']),
  detail: z.string().optional(),
})
export type AssistantStep = z.infer<typeof assistantStepSchema>

export type AssistantCitation = z.infer<typeof citationSchema>
export type NextBestAction = z.infer<typeof nextBestActionSchema>
export type AssistantAnswer = z.infer<typeof assistantAnswerSchema>

export type AssistantStreamEvent =
  | { type: 'ready' | 'retrieval_started' }
  | { type: 'step'; step: AssistantStep }
  | { type: 'answer'; data: AssistantAnswer }
  | { type: 'complete'; session_id: string }
  | { type: 'error'; message: string }

export function openAssistantStream(
  ticketId: string,
  token: string,
  onEvent: (event: AssistantStreamEvent) => void,
  onClose?: (event: CloseEvent) => void,
): WebSocket {
  const socket = new WebSocket(assistantStreamUrl(ticketId, token))
  socket.addEventListener('message', (message) => {
    try {
      const parsed: unknown = JSON.parse(String(message.data))
      if (!parsed || typeof parsed !== 'object' || !('type' in parsed)) return
      const event = parsed as Record<string, unknown>
      if (event.type === 'answer') {
        const answer = assistantAnswerSchema.safeParse(event.data)
        if (!answer.success) {
          onEvent({ type: 'error', message: 'The assistant service returned an unexpected response.' })
          return
        }
        onEvent({ type: 'answer', data: answer.data })
      } else if (event.type === 'step') {
        const step = assistantStepSchema.safeParse(event)
        if (step.success) onEvent({ type: 'step', step: step.data })
      } else if (event.type === 'ready' || event.type === 'retrieval_started') {
        onEvent({ type: event.type })
      } else if (event.type === 'complete' && typeof event.session_id === 'string') {
        onEvent({ type: 'complete', session_id: event.session_id })
      } else if (event.type === 'error' && typeof event.message === 'string') {
        onEvent({ type: 'error', message: event.message })
      }
    } catch {
      onEvent({ type: 'error', message: 'The assistant service sent an unreadable event.' })
    }
  })
  socket.addEventListener('close', (event) => onClose?.(event))
  return socket
}

export function assistantStreamUrl(ticketId: string, token: string): string {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  const url = new URL(
    `${protocol}//${window.location.host}/tickets/${encodeURIComponent(ticketId)}/assistant/stream`,
  )
  url.searchParams.set('token', token)
  return url.toString()
}

export async function askAssistant(
  ticketId: string,
  question: string,
  token: string,
  signal?: AbortSignal,
): Promise<AssistantAnswer> {
  let response: Response
  try {
    response = await fetch(`/tickets/${encodeURIComponent(ticketId)}/assistant/messages`, {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${token}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ question }),
      signal,
    })
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') throw error
    throw new TicketsApiError('The assistant could not be reached. Check your connection and retry.')
  }
  if (!response.ok) {
    if (response.status === 403 || response.status === 404) {
      throw new TicketsApiError(
        'The assistant is not available for this assigned ticket.',
        response.status,
      )
    }
    if (response.status === 401) {
      throw new TicketsApiError('Your session has expired. Sign in again.', response.status)
    }
    throw new TicketsApiError(
      'The assistant could not answer this question. Retry in a moment.',
      response.status,
    )
  }
  const parsed = assistantAnswerSchema.safeParse(await response.json().catch(() => null))
  if (!parsed.success) {
    throw new TicketsApiError('The assistant service returned an unexpected response.')
  }
  return parsed.data
}

export async function askAssistantWithStream(
  ticketId: string,
  question: string,
  token: string,
  onProgress?: (message: string) => void,
  onStep?: (step: AssistantStep) => void,
): Promise<AssistantAnswer> {
  if (typeof WebSocket === 'undefined') return askAssistant(ticketId, question, token)

  return new Promise((resolve, reject) => {
    let socket: WebSocket
    let requestSent = false
    let settled = false
    const finishWithHttpFallback = () => {
      if (settled) return
      settled = true
      void askAssistant(ticketId, question, token).then(resolve, reject)
    }
    try {
      socket = openAssistantStream(
        ticketId,
        token,
        (event) => {
          if (event.type === 'ready') {
            requestSent = true
            socket.send(JSON.stringify({ question }))
          } else if (event.type === 'retrieval_started') {
            onProgress?.('Searching ticket evidence and service guidance...')
          } else if (event.type === 'step') {
            onStep?.(event.step)
            if (event.step.status === 'running') onProgress?.(`${event.step.label}...`)
          } else if (event.type === 'answer') {
            settled = true
            resolve(event.data)
            socket.close()
          } else if (event.type === 'error') {
            settled = true
            reject(new TicketsApiError(event.message))
            socket.close()
          }
        },
        () => {
          if (settled) return
          if (!requestSent) finishWithHttpFallback()
          else {
            settled = true
            reject(new TicketsApiError('The assistant stream closed before returning an answer.'))
          }
        },
      )
      socket.addEventListener('error', () => {
        if (requestSent || settled) return
        socket.close()
        finishWithHttpFallback()
      })
      socket.addEventListener('open', () => onProgress?.('Connecting to the ticket assistant...'))
    } catch {
      finishWithHttpFallback()
    }
  })
}
