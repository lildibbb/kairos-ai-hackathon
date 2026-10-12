import { z } from 'zod'
import { customerAnswerSchema } from './customerChat'

const reportSchema = z.object({ reference: z.string(), status: z.string(), area: z.string().nullable(), technician: z.string().nullable(), reason: z.string(),
  appointment: z.object({ starts_at: z.string(), ends_at: z.string(), status: z.string() }).nullable().default(null),
})
const conversationSchema = z.object({ id: z.string().uuid(), customer_ref: z.string(), customer_name: z.string(), created_at: z.string(), turn_count: z.number(), status: z.string(), is_demo: z.boolean(), report: reportSchema.nullable() })
const internalAnswerSchema = customerAnswerSchema.extend({
  findings: z.array(z.object({ code: z.string(), observation: z.string(), interpretation: z.string(), evidence_status: z.string(), observed_at: z.string().nullable() })),
  warnings: z.array(z.string()), mode: z.string(), knowledge_status: z.string(),
  response_mode: z.enum(['static', 'hosted', 'fallback']).default('static'),
  assessment: z.object({ category: z.string(), evidence: z.array(z.string()) }).optional(),
  orchestration: z.enum(['guided', 'agent_hosted', 'agent_local', 'agent_fallback']).default('guided'),
  agent_trace: z.array(z.object({ tool: z.string(), outcome: z.enum(['observed', 'selected', 'fallback']) })).default([]),
  router_action_details: z.record(z.string(), z.unknown()).nullable().default(null),
})
export type CheckedConversation = z.infer<typeof conversationSchema>
export type CheckedTurn = { message: string; response: z.infer<typeof internalAnswerSchema> }

async function get(path: string, token: string, signal?: AbortSignal) {
  const response = await fetch(path, { headers: { Authorization: `Bearer ${token}` }, signal })
  if (!response.ok) throw new Error(response.status === 401 ? 'Session expired. Sign in again.' : response.status === 403 ? 'Operator or supervisor access is required.' : 'The checker could not load this report.')
  return response.json() as Promise<unknown>
}

export async function listCustomerReports(token: string, signal?: AbortSignal): Promise<CheckedConversation[]> {
  return z.array(conversationSchema).parse(await get('/admin/customer-reports', token, signal))
}

export async function inspectCustomerConversation(id: string, token: string, signal?: AbortSignal): Promise<CheckedTurn[]> {
  return z.object({ turns: z.array(z.object({ message: z.string(), response: internalAnswerSchema })) }).parse(
    await get(`/admin/customer-reports/${encodeURIComponent(id)}`, token, signal),
  ).turns
}
