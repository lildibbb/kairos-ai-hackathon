import { z } from 'zod'
import { TicketsApiError } from './tickets'

const topologyNodeSchema = z.object({
  device_id: z.string().min(1),
  device_ref: z.string().min(1),
  device_type: z.string().min(1),
  name: z.string().min(1),
  status: z.string().min(1),
  service_id: z.string().nullable(),
  service_ref: z.string().nullable(),
  device_data: z.record(z.string(), z.unknown()).optional(),
})

const topologyEdgeSchema = z.object({
  source_device_id: z.string().min(1),
  target_device_id: z.string().min(1),
  service_id: z.string().nullable(),
  service_ref: z.string().nullable(),
})

const topologyPathSchema = z.object({
  ticket_id: z.string().min(1),
  service_id: z.string().nullable(),
  service_ref: z.string().nullable(),
  nodes: z.array(topologyNodeSchema),
  edges: z.array(topologyEdgeSchema),
})

export type TopologyNode = z.infer<typeof topologyNodeSchema>
export type TopologyEdge = z.infer<typeof topologyEdgeSchema>
export type TopologyPath = z.infer<typeof topologyPathSchema>

export async function fetchTicketTopology(
  ticketId: string,
  token: string,
  signal?: AbortSignal,
): Promise<TopologyPath> {
  let response: Response
  try {
    response = await fetch(`/tickets/${encodeURIComponent(ticketId)}/topology`, {
      headers: { Authorization: `Bearer ${token}` },
      signal,
    })
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') throw error
    throw new TicketsApiError('The service path could not be reached. Check your connection and retry.')
  }
  if (!response.ok) {
    if (response.status === 403 || response.status === 404) {
      throw new TicketsApiError('The service path is not available for your assigned work.', response.status)
    }
    throw new TicketsApiError('The service path could not be loaded. Retry in a moment.', response.status)
  }
  const parsed = topologyPathSchema.safeParse(await response.json().catch(() => null))
  if (!parsed.success) {
    throw new TicketsApiError('The topology service returned an unexpected response.')
  }
  return parsed.data
}
