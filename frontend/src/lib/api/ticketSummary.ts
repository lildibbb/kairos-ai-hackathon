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

const orderProductSchema = z.object({
  code: z.string(),
  name: z.string(),
  description: z.string(),
  monthly_price_myr: z.number().nullable(),
  one_time_price_myr: z.number().nullable(),
  speed_mbps: z.number().nullable().optional(),
  tier: z.string().nullable().optional(),
  features: z.array(z.string()).default([]),
  badge: z.string().nullable().optional(),
})

const orderOptionSchema = z.object({
  action: z.string(),
  label: z.string(),
  recommended: z.boolean(),
  products: z.array(orderProductSchema),
})

const ticketSummarySchema = z.object({
  ticket_id: z.string(),
  problem: z.string(),
  solution: z.string().nullable(),
  product_recommendation: z.string().nullable(),
  actions: z.array(z.string()),
  facts: z.array(z.string()),
  citations: z.array(citationSchema),
  order_options: z.array(orderOptionSchema),
  plan_name: z.string().nullable(),
  plan_price_myr: z.number().nullable().optional(),
  model: z.string().nullable(),
  generated_at: z.string().nullable(),
  cached: z.boolean(),
})

const orderSchema = z.object({
  id: z.string(),
  ticket_id: z.string(),
  action: z.string(),
  product_code: z.string(),
  product_name: z.string(),
  monthly_price_myr: z.number().nullable(),
  one_time_price_myr: z.number().nullable(),
  notes: z.string().nullable(),
  status: z.string(),
  email_status: z.string(),
  email_recipient: z.string().nullable(),
  email_error: z.string().nullable(),
  created_at: z.string().nullable(),
})

export type TicketSummary = z.infer<typeof ticketSummarySchema>
export type OrderOption = z.infer<typeof orderOptionSchema>
export type OrderProduct = z.infer<typeof orderProductSchema>
export type ServiceOrder = z.infer<typeof orderSchema>

async function request(url: string, token: string, init: RequestInit = {}): Promise<Response> {
  try {
    return await fetch(url, {
      ...init,
      headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json', ...(init.headers ?? {}) },
    })
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') throw error
    throw new TicketsApiError('The service could not be reached. Check your connection and retry.')
  }
}

async function detail(response: Response, fallback: string): Promise<never> {
  const body = await response.json().catch(() => null)
  throw new TicketsApiError(body && typeof body.detail === 'string' ? body.detail : fallback, response.status)
}

export async function fetchTicketSummary(ticketId: string, token: string, options: { refresh?: boolean; signal?: AbortSignal } = {}): Promise<TicketSummary> {
  const query = options.refresh ? '?refresh=true' : ''
  const response = await request(`/tickets/${encodeURIComponent(ticketId)}/summary${query}`, token, { signal: options.signal })
  if (!response.ok) return detail(response, 'The AI summary could not be generated. Retry in a moment.')
  const parsed = ticketSummarySchema.safeParse(await response.json().catch(() => null))
  if (!parsed.success) throw new TicketsApiError('The summary service returned an unexpected response.')
  return parsed.data
}

export async function fetchOrders(ticketId: string, token: string): Promise<ServiceOrder[]> {
  const response = await request(`/tickets/${encodeURIComponent(ticketId)}/orders`, token)
  if (!response.ok) return detail(response, 'Orders could not be loaded.')
  const parsed = z.array(orderSchema).safeParse(await response.json().catch(() => null))
  if (!parsed.success) throw new TicketsApiError('The order service returned an unexpected response.')
  return parsed.data
}

export async function submitOrder(
  ticketId: string,
  input: { action: string; productCode: string; notes?: string },
  token: string,
): Promise<ServiceOrder> {
  const response = await request(`/tickets/${encodeURIComponent(ticketId)}/orders`, token, {
    method: 'POST',
    body: JSON.stringify({ action: input.action, product_code: input.productCode, notes: input.notes || null }),
  })
  if (!response.ok) return detail(response, 'The order could not be submitted. Retry in a moment.')
  const parsed = orderSchema.safeParse(await response.json().catch(() => null))
  if (!parsed.success) throw new TicketsApiError('The order service returned an unexpected response.')
  return parsed.data
}
