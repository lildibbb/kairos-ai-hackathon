import { Fragment, useCallback, useEffect, useRef, useState, type FormEvent } from 'react'
import { ArrowCounterClockwise, ArrowSquareOut, ChatCircleDots, CheckCircle, Headset, PaperPlaneRight, Phone, SignOut, Television, Ticket, WifiHigh, ArrowsClockwise, SlidersHorizontal, ShieldCheck } from '@phosphor-icons/react'
import { useAuth } from '../auth/AuthProvider'
import { Button } from '../../components/ui/button'
import { Textarea } from '../../components/ui/textarea'
import { loadCustomerHistory, sendCustomerMessage, type CustomerChatRequest, type CustomerTurn } from '../../lib/api/customerChat'
import { AppointmentPicker, visitDate, visitTime } from './AppointmentPicker'
import type { CustomerAppointment } from '../../lib/api/customerAppointments'

const starters = [
  { label: 'Slow internet', message: 'My internet is slow, I want to make a report.', icon: WifiHigh },
  { label: 'No connection', message: 'I have no internet, I want to make a report.', icon: ChatCircleDots },
  { label: 'Home phone', message: 'My home phone is not working, I want to make a report.', icon: Phone },
  { label: 'Unifi TV', message: 'My IPTV is freezing, I want to make a report.', icon: Television },
]

export function CustomerChatPage() {
  const { session, signOut } = useAuth()
  const storageKey = `customer-support-conversation:${session?.userId}`
  const [conversationId, setConversationId] = useState<string | undefined>()
  const [turns, setTurns] = useState<CustomerTurn[]>([])
  const [message, setMessage] = useState('')
  const [busy, setBusy] = useState(true)
  const [error, setError] = useState('')
  const [failedRequest, setFailedRequest] = useState<CustomerChatRequest>()
  const [appointment, setAppointment] = useState<CustomerAppointment | null>(null)
  const messageLog = useRef<HTMLDivElement>(null)
  const inFlight = useRef(false)
  const activeConversation = useRef<string>()
  const appointmentRevision = useRef(0)
  const appointmentKey = useRef('')
  const latest = turns[turns.length - 1]?.response
  const token = session?.accessToken
  const onAppointmentChange = useCallback((value: CustomerAppointment | null) => {
    if (activeConversation.current !== conversationId) return
    setAppointment(value)
    requestAnimationFrame(() => {
      const log = messageLog.current
      if (log) log.scrollTop = log.scrollHeight
    })
    const key = `${conversationId}:${value?.id ?? ''}:${value?.starts_at ?? ''}:${value?.ends_at ?? ''}`
    if (key === appointmentKey.current || !conversationId || !token) return
    appointmentKey.current = key
    const revision = ++appointmentRevision.current
    void loadCustomerHistory(conversationId, token).then((history) => {
      if (revision !== appointmentRevision.current || activeConversation.current !== conversationId) return
      const refreshed = new Map(history.map((turn) => [turn.response.request_id, turn]))
      // Merge responses only, so an in-flight refresh cannot remove a newer chat turn.
      setTurns((current) => current.map((turn) => refreshed.get(turn.response.request_id) ?? turn))
    }).catch(() => {
      if (revision === appointmentRevision.current && activeConversation.current === conversationId) {
        setError('The appointment details are shown below, but the conversation could not be refreshed. Refresh to check.')
      }
    })
  }, [conversationId, token])

  useEffect(() => {
    let cancelled = false
    let saved: string | null = null
    try { saved = window.sessionStorage.getItem(storageKey) } catch { /* Storage is optional. */ }
    if (!saved || !session) { setBusy(false); return }
    void loadCustomerHistory(saved, session.accessToken)
      .then((history) => { if (!cancelled) { activeConversation.current = saved ?? undefined; setTurns(history); setConversationId(saved ?? undefined) } })
      .catch((cause: unknown) => { if (!cancelled) setError(cause instanceof Error ? cause.message : 'History could not be loaded.') })
      .finally(() => { if (!cancelled) setBusy(false) })
    return () => { cancelled = true }
  }, [storageKey, session])

  useEffect(() => {
    const log = messageLog.current
    if (log) log.scrollTop = log.scrollHeight
  }, [turns, busy, appointment])
  useEffect(() => {
    if (latest?.router_action?.status !== 'pending' || !conversationId || !token) return
    const timer = window.setTimeout(() => {
      if (inFlight.current || activeConversation.current !== conversationId) return
      void loadCustomerHistory(conversationId, token).then((history) => {
        if (inFlight.current || activeConversation.current !== conversationId) return
        const refreshed = new Map(history.map((turn) => [turn.response.request_id, turn]))
        setTurns((current) => current.map((turn) => refreshed.get(turn.response.request_id) ?? turn))
      }).catch(() => setError('The action confirmation has expired. Refresh the conversation before continuing.'))
    }, Math.max(0, Date.parse(latest.router_action.expires_at) - Date.now()) + 250)
    return () => window.clearTimeout(timer)
  }, [conversationId, token, latest?.router_action?.id, latest?.router_action?.status, latest?.router_action?.expires_at])
  useEffect(() => {
    const scrollToLatest = () => {
      const log = messageLog.current
      if (log) log.scrollTop = log.scrollHeight
    }
    window.addEventListener('resize', scrollToLatest)
    return () => window.removeEventListener('resize', scrollToLatest)
  }, [])

  const submit = async (payload: CustomerChatRequest) => {
    if (!session || inFlight.current) return
    inFlight.current = true
    setBusy(true); setError(''); setFailedRequest(undefined)
    try {
      const response = await sendCustomerMessage(payload, session.accessToken)
      activeConversation.current = response.conversation_id
      setTurns((current) => [...current, { message: payload.message, response }])
      setConversationId(response.conversation_id)
      try { window.sessionStorage.setItem(storageKey, response.conversation_id) } catch { /* Conversation still works without storage. */ }
      setMessage('')
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'The message could not be sent.')
      setFailedRequest(payload)
    } finally { inFlight.current = false; setBusy(false) }
  }

  const send = (text: string, answerChoice?: string) => {
    if (busy || !text.trim()) return
    const actionId = answerChoice === 'confirm_router_action' || answerChoice === 'cancel_router_action' ? latest?.router_action?.id : undefined
    void submit({ message: text.trim(), request_id: crypto.randomUUID(), conversation_id: conversationId, answer_choice: answerChoice, action_id: actionId })
  }
  const onSubmit = (event: FormEvent) => { event.preventDefault(); send(message) }
  const newConversation = () => {
    activeConversation.current = undefined
    appointmentRevision.current += 1
    appointmentKey.current = ''
    setTurns([]); setConversationId(undefined); setError(''); setFailedRequest(undefined); setMessage('')
    setAppointment(null)
    try { window.sessionStorage.removeItem(storageKey) } catch { /* Storage is optional. */ }
  }

  return (
    <main className="customer-portal">
      <header className="portal-header">
        <div className="portal-brand"><img src="/unifi.svg" alt="Unifi" width="100" height="39" /><span className="portal-brand-divider" /><span>Customer support</span></div>
        <div className="portal-tools">
          <Button variant="quiet" title="Sign out" aria-label="Sign out" onClick={signOut}><SignOut size={20} /></Button>
        </div>
      </header>
      <div className="portal-layout">
        <aside className="portal-sidebar" aria-label="Support overview">
          <p className="portal-overline">MY SUPPORT</p>
          <div className="portal-active"><ChatCircleDots size={20} /><span>Support chat</span></div>
          <Button className="portal-new-chat" variant="quiet" disabled={busy || latest?.router_action?.status === 'pending'} title={latest?.router_action?.status === 'pending' ? 'Confirm or cancel the pending action first' : 'New conversation'} onClick={newConversation}><ArrowCounterClockwise size={18} />New conversation</Button>
          <div className="portal-report-summary">
            <Ticket size={22} aria-hidden="true" /><h2>Your Report</h2>
            {latest?.report ? <><p className="portal-reference">{latest.report.reference}</p><p className="portal-receipt-status">{latest.report.status === 'assigned' ? 'Assigned for technician review' : 'Waiting for assignment'}</p><p>{appointment ? <>Appointment confirmed.<br />{visitDate(appointment.starts_at)}<br />{visitTime(appointment.starts_at)} - {visitTime(appointment.ends_at)}</> : 'Appointment not yet confirmed.'}</p></> : <p>{latest?.status === 'resolved' ? 'Resolved with self-help. No ticket needed.' : 'No open report in this conversation.'}</p>}
          </div>
          <div className="portal-sidebar-footer"><Headset size={20} aria-hidden="true" /><span>Here to help you stay connected.</span></div>
        </aside>
        <section className="portal-chat" aria-label="Customer support conversation">
          <div className="portal-chat-heading"><div className="portal-avatar"><Headset size={24} /></div><div><h1>Connection Support</h1><p>Unifi Home assistant</p></div><span className="portal-session-state">{busy ? 'Checking' : 'Ready to help'}</span></div>
          <div className="portal-messages" ref={messageLog} role="log" aria-label="Messages" aria-live="polite">
            {turns.length === 0 && !busy && <div className="portal-welcome"><div className="portal-welcome-icon"><ChatCircleDots size={32} /></div><h2>Hi, how can we help?</h2><p>Tell us what's happening with your connection.<br />We'll check the issue and work through it together.</p><div className="portal-starters">{starters.map(({ label, message: text, icon: Icon }) => <Button variant="quiet" key={label} onClick={() => send(text)}><Icon size={20} />{label}</Button>)}</div></div>}
            {turns.map((turn, index) => (
              <Fragment key={turn.response.request_id}>
                <div className="portal-message portal-user"><span>You</span><p>{turn.message}</p></div>
                <div className="portal-message portal-assistant"><span><Headset size={16} />Unifi assistant</span><p>{turn.response.answer}</p>{turn.response.status === 'resolved' && <div className="portal-resolved"><CheckCircle size={18} />Resolved</div>}{index < turns.length - 1 && turn.response.follow_up && <p className="portal-question">{turn.response.follow_up.question}</p>}</div>
              </Fragment>
            ))}
            {!!latest?.sales_options.length && <section className="portal-sales" aria-label="Unifi options">{latest.sales_options.map((offer) => <article key={offer.id}><h2>{offer.name}</h2><p>{offer.description}</p>{offer.monthly_price_myr !== null && <p className="portal-offer-price">RM {offer.monthly_price_myr.toFixed(2)}/month{offer.contract_months ? `, ${offer.contract_months}-month contract` : ''}</p>}<p className="portal-offer-terms">{offer.eligibility_note}</p><a href={offer.official_url} target="_blank" rel="noopener noreferrer">View on Unifi<ArrowSquareOut size={16} /></a></article>)}</section>}
            {latest?.report?.ticket_id && session && <AppointmentPicker key={latest.report.ticket_id} ticketId={latest.report.ticket_id} token={session.accessToken} onChange={onAppointmentChange} />}
            {busy && <p className="portal-thinking" role="status"><Headset size={18} />Checking your report...</p>}
          </div>
          {latest?.follow_up && <div className="portal-follow-up">
            {latest.router_action && <div className="portal-router-action" aria-label="Router action">
              {latest.router_action.kind === 'reboot' ? <ArrowsClockwise size={22} /> : <SlidersHorizontal size={22} />}
              <div><strong>{latest.router_action.label}</strong><span>{latest.router_action.status === 'pending' ? 'Awaiting your confirmation' : latest.router_action.status === 'succeeded' ? 'Completed. Awaiting your connection check.' : latest.router_action.status}</span></div>
              <span className="portal-action-simulation"><ShieldCheck size={16} />Simulation</span>
            </div>}
            <p className="portal-question">{latest.follow_up.question}</p>
            <div className="portal-choices" role="group" aria-label={latest.follow_up.question}>
              {latest.follow_up.choices.map((choice) => <Button variant="quiet" key={choice.value} disabled={busy || !!failedRequest} onClick={() => send(choice.label, choice.value)}>{choice.label}</Button>)}
            </div>
          </div>}
          {error && <div className="portal-error"><p role="alert">{error}</p>{failedRequest && <Button disabled={busy} onClick={() => void submit(failedRequest)}>Retry message</Button>}</div>}
          <form className="portal-composer" onSubmit={onSubmit}>
            <label className="portal-sr-only" htmlFor="customer-message">Your message</label>
            <div><Textarea id="customer-message" value={message} onChange={(event) => setMessage(event.target.value)} maxLength={1000} rows={2} disabled={busy || !!failedRequest} placeholder="Tell us what's happening..." />
              <Button type="submit" disabled={busy || !!failedRequest || !message.trim()} title="Send message" aria-label="Send message"><PaperPlaneRight size={22} /></Button></div>
          </form>
        </section>
      </div>
    </main>
  )
}
