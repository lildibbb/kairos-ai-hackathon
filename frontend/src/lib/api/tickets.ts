import { z } from 'zod'

const ticketSchema = z.object({
  id: z.string().min(1),
  source_event_id: z.string().min(1),
  customer_id: z.string().min(1),
  service_id: z.string().nullable(),
  assigned_technician_id: z.string().min(1),
  severity: z.string().min(1),
  status: z.string().min(1),
  summary: z.string().min(1),
  tm_ticket_no: z.string().nullable().optional(),
  ctt_activity_id: z.string().nullable().optional(),
  login_id: z.string().nullable().optional(),
  ticket_category: z.string().nullable().optional(),
  ticket_created_at: z.string().nullable().optional(),
  staff_code: z.string().nullable().optional(),
})

const assignedTicketSchema = ticketSchema.extend({
  customer_report_reference: z.string().nullable().optional(),
  customer_ref: z.string().min(1),
  customer_name: z.string().min(1),
  service_type: z.string().nullable(),
  service_ref: z.string().nullable(),
  appointment: z.object({ starts_at: z.string(), ends_at: z.string(), status: z.literal('confirmed') }).nullable().optional(),
})

export const customerSchema = z.object({
  id: z.string().min(1),
  customer_ref: z.string().min(1),
  name: z.string().min(1),
  address: z.string().min(1),
  is_demo: z.boolean(),
  account_no: z.string().nullable().optional(),
  contact_no: z.string().nullable().optional(),
  email_address: z.string().nullable().optional(),
  contract_term: z.number().int().nullable().optional(),
  commitment_start: z.string().nullable().optional(),
  commitment_end: z.string().nullable().optional(),
})

const serviceSchema = z.object({
  id: z.string().min(1),
  service_type: z.string().min(1),
  service_ref: z.string().min(1),
  status: z.string().min(1),
  details: z.record(z.unknown()),
  credential_available: z.boolean().default(false),
})

const entityFactSchema = z.object({
  entity_type: z.string().min(1),
  entity_id: z.string().min(1),
  group_key: z.string().min(1),
  field_key: z.string().min(1),
  label: z.string().min(1),
  value_text: z.string().nullable(),
  value_number: z.number().nullable(),
  is_sensitive: z.boolean(),
})

const ticketFactsSchema = z.object({
  ticket_id: z.string().min(1),
  facts: z.array(entityFactSchema),
})

export const deviceSchema = z.object({
  id: z.string().min(1),
  device_ref: z.string().min(1),
  device_type: z.string().min(1),
  name: z.string().min(1),
  status: z.string().min(1),
  credential_available: z.boolean(),
  mac_address: z.string().nullable().optional(),
  login_id: z.string().nullable().optional(),
  friendly_name: z.string().nullable().optional(),
  manufacturer: z.string().nullable().optional(),
  brand: z.string().nullable().optional(),
  cloud_device_type: z.string().nullable().optional(),
  link_type: z.string().nullable().optional(),
  ip_address: z.string().nullable().optional(),
  ssid_2_4ghz: z.string().nullable().optional(),
  ssid_5ghz: z.string().nullable().optional(),
  channel_2_4ghz: z.number().int().nullable().optional(),
  channel_5ghz: z.number().int().nullable().optional(),
  antenna_2_4ghz: z.string().nullable().optional(),
  antenna_5ghz: z.string().nullable().optional(),
  protocol_2_4ghz: z.string().nullable().optional(),
  protocol_5ghz: z.string().nullable().optional(),
  rssi: z.number().int().nullable().optional(),
  rx_rate: z.number().int().nullable().optional(),
  tx_rate: z.number().int().nullable().optional(),
  last_seen: z.string().nullable().optional(),
  parent_mac: z.string().nullable().optional(),
  platform: z.string().nullable().optional(),
  bandwidth_2_4ghz: z.string().nullable().optional(),
  bandwidth_5ghz: z.string().nullable().optional(),
})

export const routerSchema = z.object({
  serial_number: z.string(),
  login_id: z.string(),
  manufacturer: z.string().nullable().optional(),
  model: z.string().nullable().optional(),
  cpu_usage_pct: z.number().int().nullable().optional(),
  cpu_temperature_c: z.number().int().nullable().optional(),
  memory_usage_pct: z.number().int().nullable().optional(),
  monthly_usage_gb: z.number().nullable().optional(),
  rx_power_dbm: z.number().nullable().optional(),
})

export const customerSummarySchema = z.object({
  login_id: z.string(),
  summary: z.string(),
  recommendation: z.string().nullable().optional(),
  model: z.string().nullable().optional(),
  generated_at: z.string().nullable().optional(),
})

const ticketDetailSchema = z.object({
  ticket: ticketSchema,
  assigned_technician_name: z.string(),
  customer: customerSchema,
  services: z.array(serviceSchema),
  devices: z.array(deviceSchema),
  routers: z.array(routerSchema).default([]),
  customer_summary: customerSummarySchema.nullable().optional(),
  appointment: z.object({ starts_at: z.string(), ends_at: z.string(), status: z.literal('confirmed') }).nullable().optional(),
})

const credentialRevealSchema = z.object({
  device_id: z.string().min(1),
  device_ref: z.string().min(1),
  credential_type: z.string().min(1),
  credential: z.string().min(1),
})

const serviceCredentialRevealSchema = z.object({
  service_id: z.string().min(1),
  service_ref: z.string().min(1),
  credential_type: z.string().min(1),
  credential: z.string().min(1),
})

export type AssignedTicket = z.infer<typeof assignedTicketSchema>
export type TicketDetail = z.infer<typeof ticketDetailSchema>
export type Customer = z.infer<typeof customerSchema>
export type ServiceDetail = z.infer<typeof serviceSchema>
export type Device = z.infer<typeof deviceSchema>
export type Router = z.infer<typeof routerSchema>
export type CustomerSummary = z.infer<typeof customerSummarySchema>
export type CredentialReveal = z.infer<typeof credentialRevealSchema>
export type ServiceCredentialReveal = z.infer<typeof serviceCredentialRevealSchema>
export type EntityFact = z.infer<typeof entityFactSchema>

export class TicketsApiError extends Error {
  readonly status: number | null

  constructor(message: string, status: number | null = null) {
    super(message)
    this.name = 'TicketsApiError'
    this.status = status
  }
}

function authHeaders(token: string): HeadersInit {
  return { Authorization: `Bearer ${token}` }
}

async function readJson(response: Response): Promise<unknown> {
  try {
    return await response.json()
  } catch {
    return null
  }
}

function isAbort(error: unknown): boolean {
  return error instanceof DOMException && error.name === 'AbortError'
}

export async function fetchMyTickets(token: string, signal?: AbortSignal): Promise<AssignedTicket[]> {
  let response: Response
  try {
    response = await fetch('/tickets/mine', { headers: authHeaders(token), signal })
  } catch (error) {
    if (isAbort(error)) throw error
    throw new TicketsApiError('The assigned work list could not be reached. Check your connection and retry.')
  }
  if (!response.ok) {
    if (response.status === 401 || response.status === 403) {
      throw new TicketsApiError('Your account cannot view assigned work.', response.status)
    }
    throw new TicketsApiError('The assigned work list could not be loaded. Retry in a moment.', response.status)
  }
  const parsed = z.array(assignedTicketSchema).safeParse(await readJson(response))
  if (!parsed.success) {
    throw new TicketsApiError('The assigned work service returned an unexpected response.')
  }
  return parsed.data
}

export async function fetchTicket(
  ticketId: string,
  token: string,
  signal?: AbortSignal,
): Promise<TicketDetail> {
  let response: Response
  try {
    response = await fetch(`/tickets/${encodeURIComponent(ticketId)}`, {
      headers: authHeaders(token),
      signal,
    })
  } catch (error) {
    if (isAbort(error)) throw error
    throw new TicketsApiError('The ticket could not be reached. Check your connection and retry.')
  }
  if (!response.ok) {
    if (response.status === 403 || response.status === 404) {
      throw new TicketsApiError('This ticket is not part of your assigned work.', response.status)
    }
    if (response.status === 401) {
      throw new TicketsApiError('Your session has expired. Sign in again.', response.status)
    }
    throw new TicketsApiError('The ticket could not be loaded. Retry in a moment.', response.status)
  }
  const parsed = ticketDetailSchema.safeParse(await readJson(response))
  if (!parsed.success) {
    throw new TicketsApiError('The ticket service returned an unexpected response.')
  }
  return parsed.data
}

export async function revealDeviceCredential(
  ticketId: string,
  deviceId: string,
  token: string,
): Promise<CredentialReveal> {
  let response: Response
  try {
    response = await fetch(
      `/tickets/${encodeURIComponent(ticketId)}/devices/${encodeURIComponent(deviceId)}/credential`,
      { headers: authHeaders(token) },
    )
  } catch {
    throw new TicketsApiError('The credential could not be reached. Check your connection and retry.')
  }
  if (!response.ok) {
    if (response.status === 403 || response.status === 404) {
      throw new TicketsApiError('This credential is not available for your assigned work.', response.status)
    }
    throw new TicketsApiError('The credential could not be revealed. Retry in a moment.', response.status)
  }
  const parsed = credentialRevealSchema.safeParse(await readJson(response))
  if (!parsed.success) {
    throw new TicketsApiError('The credential service returned an unexpected response.')
  }
  return parsed.data
}

export async function revealServiceCredential(
  ticketId: string,
  serviceId: string,
  token: string,
): Promise<ServiceCredentialReveal> {
  let response: Response
  try {
    response = await fetch(
      `/tickets/${encodeURIComponent(ticketId)}/services/${encodeURIComponent(serviceId)}/credential`,
      { headers: authHeaders(token) },
    )
  } catch {
    throw new TicketsApiError('The credential could not be reached. Check your connection and retry.')
  }
  if (!response.ok) {
    if (response.status === 403 || response.status === 404) {
      throw new TicketsApiError('This credential is not available for your assigned work.', response.status)
    }
    throw new TicketsApiError('The credential could not be revealed. Retry in a moment.', response.status)
  }
  const parsed = serviceCredentialRevealSchema.safeParse(await readJson(response))
  if (!parsed.success) {
    throw new TicketsApiError('The credential service returned an unexpected response.')
  }
  return parsed.data
}

export async function fetchTicketFacts(
  ticketId: string,
  token: string,
  signal?: AbortSignal,
): Promise<EntityFact[]> {
  let response: Response
  try {
    response = await fetch(`/tickets/${encodeURIComponent(ticketId)}/facts`, {
      headers: authHeaders(token),
      signal,
    })
  } catch (error) {
    if (isAbort(error)) throw error
    throw new TicketsApiError('The ticket facts could not be reached. Check your connection and retry.')
  }
  if (!response.ok) {
    if (response.status === 403 || response.status === 404) {
      throw new TicketsApiError('Ticket facts are not available for your assigned work.', response.status)
    }
    throw new TicketsApiError('The ticket facts could not be loaded.', response.status)
  }
  const parsed = ticketFactsSchema.safeParse(await readJson(response))
  if (!parsed.success) {
    throw new TicketsApiError('The ticket facts service returned an unexpected response.')
  }
  return parsed.data.facts
}
