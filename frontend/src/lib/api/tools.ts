import { z } from 'zod'
import { TicketsApiError } from './tickets'

const catalogItemSchema = z.object({
  name: z.string().min(1),
  title: z.string().min(1),
  description: z.string().min(1),
  kind: z.enum(['read_only', 'stateful']),
  category: z.enum(['diagnostics', 'wifi', 'optical', 'service', 'network']),
  risk: z.enum(['low', 'medium', 'high']),
  requires_confirmation: z.boolean(),
  target_device_types: z.array(z.string()).nullable(),
})

const toolReasoningSchema = z.object({
  observations: z.array(z.string()).default([]),
  why: z.string().default(''),
  expected: z.string().default(''),
  risk: z.string().default(''),
  rollback: z.string().default(''),
  sources: z.array(z.string()).default([]),
  trigger: z.string().default('model'),
})

const traceStepSchema = z.object({
  label: z.string(),
  detail: z.string().default(''),
  ms: z.number().default(400),
  status: z.string().default('ok'),
})

const toolResultSchema = z.object({
  trace: z.array(traceStepSchema).default([]),
  data: z.record(z.unknown()).default({}),
}).nullable().optional()

const planSuggestionSchema = z.object({
  tool_name: z.string().min(1),
  title: z.string().min(1),
  description: z.string().min(1),
  kind: z.enum(['read_only', 'stateful']),
  category: z.enum(['diagnostics', 'wifi', 'optical', 'service', 'network']),
  risk: z.enum(['low', 'medium', 'high']),
  requires_confirmation: z.boolean(),
  device_id: z.string().min(1),
  device_ref: z.string().min(1),
  device_type: z.string().min(1),
  parameters: z.record(z.unknown()),
  rationale: z.string(),
  steps: z.array(z.string()),
  evidence: z.array(z.string()),
  confidence: z.number(),
  reasoning: toolReasoningSchema.optional(),
})

export const agentPlanSchema = z.object({
  ticket_id: z.string().min(1),
  question: z.string(),
  device_id: z.string(),
  summary: z.string(),
  suggestions: z.array(planSuggestionSchema),
  reasoning: z.array(z.object({ kind: z.string(), text: z.string(), level: z.string().default('ok') })).default([]),
  alternatives: z.array(z.object({ tool_name: z.string(), reason: z.string() })).default([]),
  intent: z.string().nullable().optional(),
})

export const proposalSchema = z.object({
  id: z.string().min(1),
  ticket_id: z.string().min(1),
  tool_name: z.string().min(1),
  device_id: z.string().min(1),
  device_ref: z.string().min(1),
  kind: z.enum(['read_only', 'stateful']),
  requires_confirmation: z.boolean(),
  parameters: z.record(z.unknown()),
  status: z.enum(['proposed', 'succeeded', 'failed']),
  summary: z.string(),
  confirmation_id: z.string().min(1),
  created_at: z.string(),
  result: toolResultSchema,
}).refine((proposal) => proposal.kind === 'read_only'
  ? !proposal.requires_confirmation && proposal.status !== 'proposed'
  : proposal.requires_confirmation)

export const executionSchema = z.object({
  id: z.string().min(1),
  ticket_id: z.string().min(1),
  tool_name: z.string().min(1),
  device_id: z.string().min(1),
  device_ref: z.string().min(1),
  status: z.enum(['succeeded', 'failed']),
  message: z.string(),
  correlation_id: z.string().min(1),
  executed_at: z.string(),
  result: toolResultSchema,
})

export type ToolCatalogItem = z.infer<typeof catalogItemSchema>
export type ToolProposal = z.infer<typeof proposalSchema>
export type ToolExecution = z.infer<typeof executionSchema>
export type AgentPlanSuggestion = z.infer<typeof planSuggestionSchema>
export type AgentPlan = z.infer<typeof agentPlanSchema>
export type ToolReasoning = z.infer<typeof toolReasoningSchema>
export type TraceStep = z.infer<typeof traceStepSchema>
export type ToolResult = NonNullable<z.infer<typeof toolResultSchema>>

export function executionFromProposal(proposal: ToolProposal): ToolExecution | null {
  if (proposal.status !== 'succeeded' && proposal.status !== 'failed') return null
  return {
    id: proposal.id, ticket_id: proposal.ticket_id, tool_name: proposal.tool_name,
    device_id: proposal.device_id, device_ref: proposal.device_ref, status: proposal.status,
    message: proposal.summary, correlation_id: proposal.confirmation_id,
    // Backend execution records use the same row.created_at timestamp.
    executed_at: proposal.created_at,
    result: proposal.result,
  }
}

async function post(path: string, token: string, body: unknown): Promise<Response> {
  try {
    return await fetch(path, {
      method: 'POST',
      headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    })
  } catch {
    throw new TicketsApiError('The action service could not be reached. Check your connection and retry.')
  }
}

export async function fetchToolCatalog(ticketId: string, token: string): Promise<ToolCatalogItem[]> {
  let response: Response
  try {
    response = await fetch(`/tickets/${encodeURIComponent(ticketId)}/tools/catalog`, {
      headers: { Authorization: `Bearer ${token}` },
    })
  } catch {
    throw new TicketsApiError('The action catalog could not be reached.')
  }
  if (!response.ok) {
    throw new TicketsApiError('The action catalog could not be loaded.', response.status)
  }
  const parsed = z.array(catalogItemSchema).safeParse(await response.json().catch(() => null))
  if (!parsed.success) {
    throw new TicketsApiError('The action catalog returned an unexpected response.')
  }
  return parsed.data
}

export async function proposeTool(
  ticketId: string,
  input: { toolName: string; deviceId: string; parameters?: Record<string, number> },
  token: string,
): Promise<ToolProposal> {
  const response = await post(`/tickets/${encodeURIComponent(ticketId)}/tools/propose`, token, {
    tool_name: input.toolName,
    device_id: input.deviceId,
    parameters: input.parameters ?? {},
  })
  if (!response.ok) {
    if (response.status === 403) {
      throw new TicketsApiError('This action is not permitted here.', response.status)
    }
    if (response.status === 422) {
      throw new TicketsApiError('The action details were rejected. Check the values and retry.', response.status)
    }
    if (response.status === 404) {
      throw new TicketsApiError('This action target is not available for your assigned work.', response.status)
    }
    throw new TicketsApiError('The action could not be prepared. Retry in a moment.', response.status)
  }
  const parsed = proposalSchema.safeParse(await response.json().catch(() => null))
  if (!parsed.success) {
    throw new TicketsApiError('The action service returned an unexpected response.')
  }
  return parsed.data
}

export async function proposeAgentTool(
  ticketId: string,
  input: { question: string; deviceId?: string; toolName?: string; parameters?: Record<string, unknown> },
  token: string,
): Promise<ToolProposal> {
  const response = await post(`/tickets/${encodeURIComponent(ticketId)}/tools/agent-propose`, token, {
    question: input.question,
    device_id: input.deviceId || null,
    tool_name: input.toolName,
    parameters: input.parameters ?? {},
  })
  if (!response.ok) {
    if (response.status === 403 || response.status === 404) {
      throw new TicketsApiError('This action is not available for your assigned ticket.', response.status)
    }
    if (response.status === 422) {
      const body = await response.json().catch(() => null)
      throw new TicketsApiError(
        body && typeof body.detail === 'string'
          ? body.detail
          : 'The agent could not ground a safe action in the retrieved procedure.',
        response.status,
      )
    }
    throw new TicketsApiError('The agent could not prepare an action. Retry in a moment.', response.status)
  }
  const parsed = proposalSchema.safeParse(await response.json().catch(() => null))
  if (!parsed.success) {
    throw new TicketsApiError('The action service returned an unexpected response.')
  }
  return parsed.data
}

export async function fetchAgentPlan(
  ticketId: string,
  input: { question: string; deviceId?: string },
  token: string,
): Promise<AgentPlan> {
  const response = await post(`/tickets/${encodeURIComponent(ticketId)}/tools/agent-plan`, token, {
    question: input.question,
    device_id: input.deviceId || null,
  })
  if (!response.ok) {
    if (response.status === 403 || response.status === 404) {
      throw new TicketsApiError('This action is not available for your assigned ticket.', response.status)
    }
    if (response.status === 422) {
      const body = await response.json().catch(() => null)
      throw new TicketsApiError(
        body && typeof body.detail === 'string'
          ? body.detail
          : 'The agent could not ground a safe action in the retrieved procedure.',
        response.status,
      )
    }
    throw new TicketsApiError('The assistant could not build an action plan. Retry in a moment.', response.status)
  }
  const parsed = agentPlanSchema.safeParse(await response.json().catch(() => null))
  if (!parsed.success) {
    throw new TicketsApiError('The action service returned an unexpected response.')
  }
  return parsed.data
}

export async function confirmTool(
  ticketId: string,
  proposalId: string,
  confirmationId: string,
  token: string,
): Promise<ToolExecution> {
  const response = await post(
    `/tickets/${encodeURIComponent(ticketId)}/tools/${encodeURIComponent(proposalId)}/confirm`,
    token,
    { confirmation_id: confirmationId },
  )
  if (!response.ok) {
    if (response.status === 403 || response.status === 404) {
      throw new TicketsApiError('This action cannot be confirmed here.', response.status)
    }
    throw new TicketsApiError('The action could not be executed. Retry in a moment.', response.status)
  }
  const parsed = executionSchema.safeParse(await response.json().catch(() => null))
  if (!parsed.success) {
    throw new TicketsApiError('The action service returned an unexpected response.')
  }
  return parsed.data
}
