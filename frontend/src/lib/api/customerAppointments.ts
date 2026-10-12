import { z } from 'zod'

const windowSchema = z.object({ slot_id: z.string().uuid(), starts_at: z.string().datetime({ offset: true }), ends_at: z.string().datetime({ offset: true }) })
const appointmentSchema = windowSchema.extend({ id: z.string().uuid(), ticket_id: z.string().uuid(), status: z.enum(['confirmed', 'cancelled']) })
const availabilitySchema = z.object({ timezone: z.literal('Asia/Kuala_Lumpur'), slots: z.array(windowSchema), appointment: appointmentSchema.nullable() })
export type CustomerAppointment = z.infer<typeof appointmentSchema>
export type VisitAvailability = z.infer<typeof availabilitySchema>
export type BookingRequest = { slot_id: string; request_id: string }

export class AppointmentRequestError extends Error {
  constructor(message: string, readonly status?: number) { super(message) }
}

async function request(ticketId: string, suffix: string, token: string, init: RequestInit = {}) {
  let response: Response
  try {
    response = await fetch(`/portal/me/reports/${encodeURIComponent(ticketId)}/${suffix}`, {
      ...init, headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
    })
  } catch { throw new AppointmentRequestError('The booking response could not be received. Retry to check the same request.') }
  if (!response.ok) {
    let message = response.status === 401 ? 'Your session has expired. Sign in again.' : 'The appointment could not be processed. Please retry.'
    if (response.status === 409) {
      try { const body: unknown = await response.json(); const parsed = z.object({ detail: z.string() }).safeParse(body); if (parsed.success) message = parsed.data.detail } catch { /* Use the fallback. */ }
    }
    throw new AppointmentRequestError(message, response.status)
  }
  return response.json() as Promise<unknown>
}

export async function loadVisitAvailability(ticketId: string, token: string): Promise<VisitAvailability> {
  return availabilitySchema.parse(await request(ticketId, 'appointment-slots', token))
}
export async function bookCustomerVisit(ticketId: string, payload: BookingRequest, token: string): Promise<CustomerAppointment> {
  return appointmentSchema.parse(await request(ticketId, 'appointments', token, { method: 'POST', body: JSON.stringify(payload) }))
}
export async function cancelCustomerVisit(ticketId: string, appointmentId: string, token: string): Promise<CustomerAppointment> {
  return appointmentSchema.parse(await request(ticketId, `appointments/${encodeURIComponent(appointmentId)}`, token, { method: 'DELETE' }))
}
