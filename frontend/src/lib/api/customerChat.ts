import { z } from 'zod'

const choiceSchema = z.object({ value: z.string(), label: z.string() })
export function isOfficialSalesUrl(value: string): boolean {
  try {
    const url = new URL(value)
    return url.protocol === 'https:' && ['unifi.com.my', 'www.unifi.com.my', 'selfcare.unifi.com.my'].includes(url.hostname)
      && (!url.port || url.port === '443') && !url.username && !url.password && !url.hash
  } catch { return false }
}
const salesOptionSchema = z.object({
  id: z.string(), name: z.string(), description: z.string(), official_url: z.string().refine(isOfficialSalesUrl),
  monthly_price_myr: z.number().nonnegative().nullable().default(null), contract_months: z.number().int().positive().nullable().default(null), eligibility_note: z.string(),
})
export const customerAnswerSchema = z.object({
  conversation_id: z.string().uuid(),
  request_id: z.string().uuid(),
  checked_at: z.string(),
  answer: z.string(),
  status: z.enum(['possible_issue', 'needs_live_check', 'needs_more_information', 'self_help', 'resolved', 'report_created', 'sales_options', 'action_confirmation', 'action_completed', 'action_cancelled']),
  follow_up: z.object({ id: z.string(), question: z.string(), choices: z.array(choiceSchema) }).nullable(),
  report: z.object({ ticket_id: z.string().uuid().nullable().default(null), reference: z.string(), status: z.enum(['assigned', 'queued']) }).nullable(),
  sales_options: z.array(salesOptionSchema).default([]),
  router_action: z.object({ id: z.string().uuid(), kind: z.enum(['reboot', 'restore_vlan']), label: z.string(),
    status: z.enum(['pending', 'succeeded', 'cancelled', 'expired']), simulation: z.literal(true), expires_at: z.string(),
  }).nullable().default(null),
})

export type CustomerAnswer = z.infer<typeof customerAnswerSchema>
export type CustomerTurn = { message: string; response: CustomerAnswer }
export type CustomerChatRequest = {
  message: string; request_id: string; conversation_id?: string; answer_choice?: string; action_id?: string
}

async function request(path: string, token: string, init: RequestInit = {}): Promise<unknown> {
  let response: Response
  try {
    response = await fetch(path, {
      ...init,
      headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
    })
  } catch {
    throw new Error('Support could not be reached. Check your connection and retry.')
  }
  if (!response.ok) {
    let message = 'The message could not be processed. Please retry.'
    if (response.status === 401) message = 'Your session has expired. Sign in again.'
    if (response.status === 403) message = 'Customer support is unavailable for this account. Contact support.'
    if (response.status === 404) message = 'This conversation is unavailable. Start a new conversation.'
    if (response.status === 409) message = 'The conversation could not accept this message. Retry or start a new conversation.'
    throw new Error(message)
  }
  return response.json()
}

export async function sendCustomerMessage(payload: CustomerChatRequest, token: string): Promise<CustomerAnswer> {
  const result = customerAnswerSchema.safeParse(await request('/portal/me/chat/messages', token, {
    method: 'POST', body: JSON.stringify(payload),
  }))
  if (!result.success) throw new Error('Support returned an unreadable answer. Please retry.')
  return result.data
}

export async function loadCustomerHistory(conversationId: string, token: string): Promise<CustomerTurn[]> {
  const schema = z.object({ conversation_id: z.string().uuid(), turns: z.array(z.object({ message: z.string(), response: customerAnswerSchema })) })
  const result = schema.safeParse(await request(`/portal/me/chat/conversations/${encodeURIComponent(conversationId)}`, token))
  if (!result.success) throw new Error('Conversation history could not be loaded.')
  return result.data.turns
}
