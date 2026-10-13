import { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react'
import { Scene3D } from '../../components/illustration/Scene3D'
import './intake-motion.css'
import { Button } from '../../components/ui/button'
import { useAuth } from '../auth/AuthProvider'
import {
  EventsApiError,
  describeEventType,
  fetchPendingEvents,
  processEvent,
  type PendingEvent,
  type ProcessEventResult,
} from '../../lib/api/events'
import { EventReviewPanel } from './EventReviewPanel'

type LoadState = 'loading' | 'ready' | 'error'

export function EventIntakeQueue() {
  const { session } = useAuth()
  const token = session?.accessToken ?? ''
  const [events, setEvents] = useState<PendingEvent[]>([])
  const [loadState, setLoadState] = useState<LoadState>('loading')
  const [loadError, setLoadError] = useState('')
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [results, setResults] = useState<Record<string, ProcessEventResult>>({})
  const [requests, setRequests] = useState<Record<string, { pending: boolean; error: string }>>({})
  const inFlight = useRef(new Map<string, AbortController>())
  const reviewRef = useRef<HTMLDivElement>(null)
  const focusResult = useRef(false)

  useLayoutEffect(() => {
    if (focusResult.current) {
      reviewRef.current?.querySelector<HTMLAnchorElement>('.ticket-confirmation a')?.focus()
      focusResult.current = false
    }
  }, [results])

  const load = useCallback(
    async (signal?: AbortSignal) => {
      setLoadState('loading')
      setLoadError('')
      setResults({})
      try {
        const pending = await fetchPendingEvents(token, signal)
        if (signal?.aborted) return
        setEvents(pending)
        setSelectedId((current) =>
          current && pending.some((event) => event.id === current) ? current : pending[0]?.id ?? null,
        )
        setLoadState('ready')
      } catch (error) {
        if (signal?.aborted) return
        if (error instanceof DOMException && error.name === 'AbortError') return
        setLoadState('error')
        setLoadError(error instanceof EventsApiError ? error.message : 'The event queue could not be loaded.')
      }
    },
    [token],
  )

  useEffect(() => {
    const controller = new AbortController()
    void load(controller.signal)
    return () => {
      controller.abort()
      for (const request of inFlight.current.values()) request.abort()
      inFlight.current.clear()
    }
  }, [load])

  const selectEvent = (eventId: string) => {
    setSelectedId(eventId)
  }

  const process = async (eventId: string) => {
    if (inFlight.current.has(eventId) || results[eventId]) return
    const controller = new AbortController()
    inFlight.current.set(eventId, controller)
    setRequests(current => ({ ...current, [eventId]: { pending: true, error: '' } }))
    try {
      const result = await processEvent(eventId, token, controller.signal)
      if (controller.signal.aborted) return
      focusResult.current = Boolean(reviewRef.current?.dataset.eventId === eventId
        && reviewRef.current?.contains(document.activeElement)
        && document.activeElement?.classList.contains('process-button'))
      setResults(current => ({ ...current, [eventId]: result }))
      setRequests(current => ({ ...current, [eventId]: { pending: false, error: '' } }))
    } catch (caught) {
      if (controller.signal.aborted) return
      const error = caught instanceof EventsApiError ? caught.message : 'The event could not be processed. Retry.'
      setRequests(current => ({ ...current, [eventId]: { pending: false, error } }))
    } finally {
      if (inFlight.current.get(eventId) === controller) inFlight.current.delete(eventId)
    }
  }

  if (loadState === 'loading') {
    return (
      <section className="intake" aria-labelledby="intake-heading">
        <h2 id="intake-heading">Event intake</h2>
        <p className="state-panel" role="status">
          Loading pending events.
        </p>
      </section>
    )
  }

  if (loadState === 'error') {
    return (
      <section className="intake" aria-labelledby="intake-heading">
        <h2 id="intake-heading">Event intake</h2>
        <div className="state-panel">
          <p className="form-error" role="alert">
            {loadError}
          </p>
          <Button className="process-button" type="button" onClick={() => void load()}>
            Retry loading events
          </Button>
        </div>
      </section>
    )
  }

  if (events.length === 0) {
    return (
      <section className="intake" aria-labelledby="intake-heading">
        <h2 id="intake-heading">Event intake</h2>
        <div className="state-panel empty-state">
          <Scene3D className="empty-scene" variant="resolved" size={180} />
          <h3>No pending events</h3>
          <p>
            The seeded intake feed has no unprocessed events. New events appear here when the
            network reports an incident.
          </p>
        </div>
      </section>
    )
  }

  const selected = events.find((event) => event.id === selectedId) ?? events[0]
  const unresolved = events.filter(event => !results[event.id]).length

  return (
    <section className="intake" aria-labelledby="intake-heading">
      <Scene3D className="intake-scene" variant="network" size={150} />
      <h2 id="intake-heading">Event intake</h2>
      <p className="intake-intro">
        {unresolved === 0 ? 'No events are waiting to be processed.'
          : unresolved === 1 ? '1 event is waiting to be processed.' : `${unresolved} events are waiting to be processed.`}
      </p>

      <ul className="event-list">
        {events.map((event) => {
          const isSelected = event.id === selected.id
          return (
            <li key={event.id}>
              <Button
                type="button"
                className={isSelected ? 'event-select is-selected' : 'event-select'}
                aria-pressed={isSelected}
                onClick={() => selectEvent(event.id)}
              >
                <span className="event-type">{describeEventType(event.event_type)}</span>
                <span className="event-ref tabular">{event.source_event_id}</span>
                <span className="event-device">{event.device_name}</span>
              </Button>
            </li>
          )
        })}
      </ul>

      <div ref={reviewRef} className="intake-review" data-event-id={selected.id}>
        <EventReviewPanel
          key={selected.id}
          event={selected}
          submitting={requests[selected.id]?.pending ?? false}
          error={requests[selected.id]?.error ?? ''}
          result={results[selected.id] ?? null}
          onProcess={() => void process(selected.id)}
        />
      </div>
    </section>
  )
}
