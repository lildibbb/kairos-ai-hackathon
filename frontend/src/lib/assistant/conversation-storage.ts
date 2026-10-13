import { z } from 'zod'
import { assistantAnswerSchema, assistantStepSchema } from '../api/assistant'
import { agentPlanSchema, executionSchema, proposalSchema } from '../api/tools'

const activitySchema = z.enum(['pending', 'completed', 'needs-approval', 'no-evidence', 'failed'])
const planSchema = agentPlanSchema
const actionStateSchema = z.object({
  plan: planSchema.nullable(), proposal: proposalSchema.nullable(), execution: executionSchema.nullable(),
  rejected: z.boolean(), attempts: z.array(z.object({ proposal: proposalSchema.nullable(), execution: executionSchema })),
})
const turnSchema = z.object({
  id: z.number().int().positive(),
  question: z.string(),
  state: z.enum(['pending', 'answered', 'error']),
  answer: assistantAnswerSchema.optional(),
  message: z.string().optional(),
  activity: activitySchema,
  action: actionStateSchema.optional(),
  steps: z.array(assistantStepSchema).optional(),
})

export type StoredConversationTurn = z.infer<typeof turnSchema>
export type StoredActionState = z.infer<typeof actionStateSchema>

function storageKey(userId: string, ticketId: string) {
  return `field-force-chat-history:v1:${encodeURIComponent(userId)}:${encodeURIComponent(ticketId)}`
}

export function readConversation(userId: string, ticketId: string): StoredConversationTurn[] {
  try {
    const stored = window.sessionStorage.getItem(storageKey(userId, ticketId))
    if (!stored) return []
    const parsed = z.array(turnSchema).safeParse(JSON.parse(stored))
    if (!parsed.success) return []
    return parsed.data.map((turn) => turn.state === 'pending'
      ? { ...turn, state: 'error', activity: 'failed', message: 'This reply did not finish. Retry the question to continue.' }
      : turn)
  } catch {
    return []
  }
}

export function writeConversation(userId: string, ticketId: string, turns: StoredConversationTurn[]) {
  try {
    window.sessionStorage.setItem(storageKey(userId, ticketId), JSON.stringify(turns))
  } catch {
    // Storage can be unavailable or full; the live conversation remains usable.
  }
}
