import { useEffect, useId, useRef, useState } from 'react'
import { ArrowsClockwise, CalendarCheck, X } from '@phosphor-icons/react'
import { Button } from '../../components/ui/button'
import { AppointmentRequestError, bookCustomerVisit, cancelCustomerVisit, loadVisitAvailability, type BookingRequest, type CustomerAppointment, type VisitAvailability } from '../../lib/api/customerAppointments'

export const visitDate = (value: string) => new Date(value).toLocaleDateString('en-MY', { timeZone: 'Asia/Kuala_Lumpur', weekday: 'short', day: 'numeric', month: 'short', year: 'numeric' })
export const visitTime = (value: string) => new Date(value).toLocaleTimeString('en-MY', { timeZone: 'Asia/Kuala_Lumpur', hour: '2-digit', minute: '2-digit', hour12: false })

export function AppointmentPicker({ ticketId, token, onChange }: { ticketId: string; token: string; onChange: (appointment: CustomerAppointment | null) => void }) {
  const id = useId()
  const [data, setData] = useState<VisitAvailability>()
  const [date, setDate] = useState('')
  const [slotId, setSlotId] = useState('')
  const [busy, setBusy] = useState(true)
  const [error, setError] = useState('')
  const [retry, setRetry] = useState<BookingRequest>()
  const [notice, setNotice] = useState('')
  const inFlight = useRef(false)
  const reload = async () => {
    const result = await loadVisitAvailability(ticketId, token)
    setData(result); onChange(result.appointment)
    setDate(''); setSlotId('')
  }
  useEffect(() => {
    let cancelled = false
    void loadVisitAvailability(ticketId, token).then((result) => {
      if (!cancelled) { setData(result); onChange(result.appointment) }
    }).catch(() => { if (!cancelled) setError('Visit times could not be loaded. Please refresh.') })
      .finally(() => { if (!cancelled) setBusy(false) })
    return () => { cancelled = true }
  }, [ticketId, token, onChange])
  const dates = [...new Set(data?.slots.map((slot) => visitDate(slot.starts_at)))]
  const selectedDate = date || dates[0] || ''
  const seen = new Set<string>()
  const slots = (data?.slots ?? []).filter((slot) => {
    const key = `${slot.starts_at}:${slot.ends_at}`
    if (visitDate(slot.starts_at) !== selectedDate || seen.has(key)) return false
    seen.add(key); return true
  })
  const selectedSlot = slots.find((slot) => slot.slot_id === slotId) ?? slots[0]
  const refresh = async () => {
    if (inFlight.current) return
    inFlight.current = true; setBusy(true); setError('')
    try { await reload() } catch { setError('Visit times could not be loaded. Please refresh.') }
    finally { inFlight.current = false; setBusy(false) }
  }
  const book = async () => {
    if (inFlight.current || (!selectedSlot && !retry)) return
    inFlight.current = true; setBusy(true); setError(''); setNotice('')
    const payload = retry ?? { slot_id: selectedSlot!.slot_id, request_id: crypto.randomUUID() }
    try {
      const appointment = await bookCustomerVisit(ticketId, payload, token)
      setRetry(undefined); onChange(appointment.status === 'confirmed' ? appointment : null)
      setData((current) => current ? { ...current, appointment: appointment.status === 'confirmed' ? appointment : null } : current)
      setNotice(appointment.status === 'confirmed' ? 'Your appointment is confirmed.' : 'This booking was cancelled. Choose another time to make a new booking.')
      await reload().catch(() => { setError('The booking was saved, but updated times could not be loaded. Refresh to check.') })
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'The appointment could not be processed.')
      if (cause instanceof AppointmentRequestError && cause.status !== undefined) {
        setRetry(undefined)
        if (cause.status === 409) await reload().catch(() => {})
      } else setRetry(payload)
    } finally { inFlight.current = false; setBusy(false) }
  }
  const cancel = async () => {
    if (inFlight.current || !data?.appointment) return
    if (!window.confirm('Cancel this technician appointment? Your trouble ticket will remain open.')) return
    inFlight.current = true; setBusy(true); setError(''); setNotice('')
    try {
      await cancelCustomerVisit(ticketId, data.appointment.id, token)
      setData((current) => current ? { ...current, appointment: null } : current); onChange(null)
      setNotice('Your appointment was cancelled. Your trouble ticket remains open.')
      await reload()
    } catch (cause) { setError(cause instanceof Error ? cause.message : 'Cancellation could not be confirmed. Refresh to check.') }
    finally { inFlight.current = false; setBusy(false) }
  }
  return <section className="portal-appointment" aria-label="Technician appointment">
    <div className="portal-appointment-heading"><h2><CalendarCheck size={20} />Technician appointment</h2><Button variant="quiet" onClick={() => void refresh()} disabled={busy || !!retry} title="Refresh visit times" aria-label="Refresh visit times"><ArrowsClockwise size={18} /></Button></div>
    {data?.appointment && <div className="portal-booking-confirmed"><div><strong>Confirmed</strong><p>{visitDate(data.appointment.starts_at)}<br />{visitTime(data.appointment.starts_at)} - {visitTime(data.appointment.ends_at)} (Malaysia time)</p></div><Button variant="quiet" onClick={() => void cancel()} disabled={busy || !!retry} title="Cancel appointment" aria-label="Cancel appointment"><X size={18} /></Button></div>}
    {busy && <p role="status">Checking visit times...</p>}
    {!busy && data && dates.length === 0 && <p>No visit windows are currently available. Your ticket remains open for the support team to arrange a suitable time.</p>}
    {data && dates.length > 0 && <div className="portal-booking-controls">
      <label htmlFor={`${id}-date`}>Date<select id={`${id}-date`} value={selectedDate} onChange={(event) => { setDate(event.target.value); setSlotId('') }} disabled={busy || !!retry}>{dates.map((value) => <option key={value}>{value}</option>)}</select></label>
      <label htmlFor={`${id}-time`}>Visit window<select id={`${id}-time`} value={selectedSlot?.slot_id ?? ''} onChange={(event) => setSlotId(event.target.value)} disabled={busy || !!retry}>{slots.map((slot) => <option value={slot.slot_id} key={slot.slot_id}>{visitTime(slot.starts_at)} - {visitTime(slot.ends_at)}</option>)}</select></label>
      <Button onClick={() => void book()} disabled={busy || !selectedSlot}>{retry ? 'Retry booking' : data.appointment ? 'Reschedule appointment' : 'Confirm appointment'}</Button>
    </div>}
    {notice && <p className="portal-booking-notice" role="status">{notice}</p>}
    {error && <p className="portal-error" role="alert">{error}</p>}
  </section>
}
