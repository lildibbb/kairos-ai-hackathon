import { useCallback, useEffect, useRef, useState } from 'react'
import { Button } from '../../components/ui/button'
import { Link, useParams } from 'react-router-dom'
import { useAuth } from '../auth/AuthProvider'
import {
  TicketsApiError,
  fetchTicket,
  fetchTicketFacts,
  type EntityFact,
  type TicketDetail,
} from '../../lib/api/tickets'
import { fetchTicketTopology, type TopologyPath as TopologyPathData } from '../../lib/api/topology'
import { TopologyPath } from '../topology/TopologyPath'
import { TroubleshootingAssistant } from '../assistant/TroubleshootingAssistant'
import { TicketHeader } from './TicketHeader'
import { IncidentTrace, type IncidentStage } from './IncidentTrace'
import type { ToolExecution } from '../../lib/api/tools'
import type { AssistantAnswer } from '../../lib/api/assistant'
import { AssistantEvidenceSummary } from '../assistant/AssistantEvidenceSummary'
import { TicketWorkspaceTabs } from './TicketWorkspaceTabs'
import { ChatsCircle, X } from '@phosphor-icons/react'
import * as Dialog from '@radix-ui/react-dialog'

type PageState = 'loading' | 'ready' | 'error' | 'denied'
type TopologyState = 'loading' | 'ready' | 'error'

export function TicketPage() {
  const { ticketId } = useParams()
  const { session } = useAuth()
  return <TicketWorkspace key={`${ticketId}:${session?.accessToken}`} />
}

function TicketWorkspace() {
  const { ticketId } = useParams()
  const { session } = useAuth()
  const token = session?.accessToken ?? ''
  const backTo = session?.role === 'technician' ? '/work' : '/operations'

  const [detail, setDetail] = useState<TicketDetail | null>(null)
  const [facts, setFacts] = useState<EntityFact[]>([])
  const [pageState, setPageState] = useState<PageState>('loading')
  const [pageError, setPageError] = useState('')
  const [topology, setTopology] = useState<TopologyPathData | null>(null)
  const [topologyState, setTopologyState] = useState<TopologyState>('loading')
  const [topologyError, setTopologyError] = useState('')
  const [selectedDeviceId, setSelectedDeviceId] = useState<string>()
  const [evidenceStage, setEvidenceStage] = useState<IncidentStage>({ id: 'evidence', label: 'Evidence', state: 'upcoming', detail: 'Evidence not yet confirmed' })
  const [actionStage, setActionStage] = useState<IncidentStage>({ id: 'action', label: 'Action', state: 'upcoming', detail: 'No confirmed outcome' })
  const [actionDeviceId, setActionDeviceId] = useState<string>()
  const [actionOutcome, setActionOutcome] = useState<string>()
  const [assistantOpen, setAssistantOpen] = useState(false)
  const assistantTriggerRef = useRef<HTMLButtonElement>(null)
  const assistantCloseRef = useRef<HTMLButtonElement>(null)
  useEffect(() => {
    if (assistantOpen) assistantCloseRef.current?.focus()
  }, [assistantOpen])
  const [answer, setAnswer] = useState<AssistantAnswer>()
  const actionOwner = useRef(0)
  const evidenceRequests = useRef(new Map<number, { message?: string }>())
  const evidenceRequestSequence = useRef(0)
  const reportEvidenceProgress = useCallback((stage: IncidentStage, request: number, settled = false) => {
    const activeRequests = [...evidenceRequests.current.keys()]
    if (request !== Math.max(...activeRequests, 0)) {
      if (settled) evidenceRequests.current.delete(request)
      return
    }
    if (!settled) {
      evidenceRequests.current.set(request, { message: stage.detail })
      setEvidenceStage(stage)
      return
    }
    evidenceRequests.current.delete(request)
    const remaining = [...evidenceRequests.current.entries()].sort(([left], [right]) => right - left)[0]
    if (remaining) {
      setEvidenceStage({ id: 'evidence', label: 'Evidence', state: 'current', detail: remaining[1].message ?? 'Investigation still in progress' })
    } else {
      setEvidenceStage(stage)
    }
  }, [])
  const startEvidenceRequest = useCallback(() => {
    const request = ++evidenceRequestSequence.current
    evidenceRequests.current.set(request, {})
    return (stage: IncidentStage) => reportEvidenceProgress(stage, request, stage.state !== 'current')
  }, [reportEvidenceProgress])
  const startAction = useCallback((deviceId?: string) => {
    setActionDeviceId(deviceId)
    if (deviceId) setSelectedDeviceId(deviceId)
    const operation = ++actionOwner.current
    return (stage: IncidentStage, outcome?: ToolExecution) => {
      if (operation !== actionOwner.current) return
      setActionStage(stage)
      setActionOutcome(outcome?.status === 'succeeded' ? outcome.message : undefined)
      if (outcome?.status === 'succeeded' && ticketId) {
        void fetchTicketTopology(ticketId, token).then((path) => { if (operation === actionOwner.current) setTopology(path) }).catch(() => { setTopologyError('Action completed, but the updated service path could not be loaded.'); setTopologyState('error') })
      }
    }
  }, [ticketId, token])

  useEffect(() => {
    setSelectedDeviceId(undefined)
  }, [ticketId])

  const load = useCallback(
    async (signal?: AbortSignal) => {
      if (!ticketId) {
        setPageState('error')
        setPageError('No ticket was specified.')
        return
      }
      setPageState('loading')
      setPageError('')
      setTopology(null)
      setTopologyState('loading')
      setFacts([])

      try {
        const loaded = await fetchTicket(ticketId, token, signal)
        setDetail(loaded)
        setPageState('ready')
        void fetchTicketFacts(ticketId, token, signal)
          .then((loadedFacts) => { setFacts(loadedFacts) })
          .catch(() => { setFacts([]) })
      } catch (error) {
        if (error instanceof DOMException && error.name === 'AbortError') return
        if (error instanceof TicketsApiError && (error.status === 403 || error.status === 404)) {
          setPageState('denied')
          return
        }
        setPageState('error')
        setPageError(error instanceof TicketsApiError ? error.message : 'The ticket could not be loaded.')
        return
      }

      setTopologyState('loading')
      setTopologyError('')
      try {
        const path = await fetchTicketTopology(ticketId, token, signal)
        setTopology(path)
        setTopologyState('ready')
      } catch (error) {
        if (error instanceof DOMException && error.name === 'AbortError') return
        setTopologyState('error')
        setTopologyError(
          error instanceof TicketsApiError ? error.message : 'The service path could not be loaded.',
        )
      }
    },
    [ticketId, token],
  )

  useEffect(() => {
    const controller = new AbortController()
    void load(controller.signal)
    return () => controller.abort()
  }, [load])

  return (
    <main className="app-shell ticket-workspace">
        <header className="app-header">
        <p className="app-context"><span className="brand-mark">F</span> Fieldforce</p>
        <h1>Incident workspace</h1>
        <Link className="inline-link" to={backTo}>
          {session?.role === 'technician' ? 'Back to my work' : 'Back to event intake'}
        </Link>
      </header>

      {pageState === 'loading' && (
        <p className="state-panel" role="status">
          Loading ticket details.
        </p>
      )}

      {pageState === 'error' && (
        <div className="state-panel">
          <p className="form-error" role="alert">
            {pageError}
          </p>
          <Button className="process-button" type="button" onClick={() => void load()}>
            Retry loading ticket
          </Button>
        </div>
      )}

      {pageState === 'denied' && (
        <section className="state-panel" aria-labelledby="denied-heading">
          <h3 id="denied-heading">Ticket not available</h3>
          <p>
            This ticket is not part of your assigned work. Return to your list to open a ticket assigned
            to you.
          </p>
          <Link className="inline-link" to={backTo}>
            {session?.role === 'technician' ? 'Back to my work' : 'Back to event intake'}
          </Link>
        </section>
      )}

      {pageState === 'ready' && detail && (
        <div className="ticket-page">
          <TicketHeader detail={detail} />
          <IncidentTrace key={detail.ticket.id} confirmedActionOutcome={actionOutcome} stages={[
            { id: 'event', label: 'Event', state: 'complete', detail: `Source event: ${detail.ticket.source_event_id}` },
            { id: 'ticket', label: 'Ticket', state: 'current', detail: 'Ticket context loaded' },
            {
              id: 'topology', label: 'Topology',
              state: topologyState === 'error' ? 'blocked'
                : topologyState === 'ready' && topology?.ticket_id === detail.ticket.id && topology.nodes.length > 0
                  ? 'complete' : 'upcoming',
              detail: topologyState === 'error' ? 'Service path unavailable. Retry below.'
                : topologyState === 'loading' ? 'Loading service path'
                  : topology?.nodes.length ? 'Service path loaded' : 'No service path available',
            },
            evidenceStage,
            actionStage,
          ]} />
          <div className="investigation-workspace">
          <section className="panel topology-panel" aria-labelledby="topology-heading">
            <div className="topology-panel-heading">
              <div>
                <h3 id="topology-heading">Customer network topology</h3>
              </div>
              <div className="topology-heading-actions">
                {topologyState === 'ready' && topology && topology.nodes.length > 0 && (
                  <p className="topology-count">{topology.nodes.length} {topology.nodes.length === 1 ? 'device' : 'devices'} · {topology.edges.length} {topology.edges.length === 1 ? 'connection' : 'connections'}</p>
                )}
                <button type="button" ref={assistantTriggerRef} className="ai-launcher" onClick={() => setAssistantOpen(true)} aria-label="Open AI assistant" aria-haspopup="dialog" aria-expanded={assistantOpen}>
                  <ChatsCircle size={19} weight="duotone" aria-hidden="true" />
                  <span>Investigate with assistant</span>
                </button>
              </div>
            </div>

            {topologyState === 'loading' && (
              <p className="muted-note" role="status">Loading the service path.</p>
            )}
            {topologyState === 'error' && (
              <div>
                <p className="form-error" role="alert">{topologyError}</p>
                <Button className="process-button" type="button" onClick={() => void load()}>
                  Retry service path
                </Button>
              </div>
            )}
            {topologyState === 'ready' && topology && (
              <TopologyPath
                key={topology.ticket_id}
                nodes={topology.nodes}
                edges={topology.edges}
                serviceRef={topology.service_ref}
                facts={facts}
                actionStage={actionStage}
                actionDeviceId={actionDeviceId}
                selectedDeviceId={selectedDeviceId}
                onSelectDevice={setSelectedDeviceId}
                onClearSelection={() => setSelectedDeviceId(undefined)}
              />
            )}
          </section>
          <AssistantEvidenceSummary answer={answer} observed={detail.ticket.summary} onInvestigate={() => setAssistantOpen(true)} />
          </div>
          <Dialog.Root modal={false} open={assistantOpen} onOpenChange={setAssistantOpen}>
            <Dialog.Portal forceMount>
              <Dialog.Content className="assistant-drawer redesigned-assistant" hidden={!assistantOpen} aria-hidden={!assistantOpen} aria-label="AI assistant" aria-describedby="assistant-description" onOpenAutoFocus={(event) => event.preventDefault()} onInteractOutside={(event) => event.preventDefault()} onEscapeKeyDown={() => assistantTriggerRef.current?.focus()} onCloseAutoFocus={(event) => { event.preventDefault(); assistantTriggerRef.current?.focus() }}>
                <div className="assistant-drawer-heading">
                  <div><p className="section-label">Fieldforce / Investigation</p><Dialog.Title>Investigate this incident</Dialog.Title><Dialog.Description id="assistant-description">Ticket context and service evidence, in one conversation.</Dialog.Description></div>
                  <Dialog.Close ref={assistantCloseRef} className="assistant-drawer-close" aria-label="Close AI assistant" onClick={() => assistantTriggerRef.current?.focus()}><X size={20} aria-hidden="true" /></Dialog.Close>
                </div>
                <TroubleshootingAssistant key={detail.ticket.id} ticketId={detail.ticket.id} token={token} userId={session?.userId} devices={detail.devices} services={detail.services}
                  onAnswer={setAnswer} onSelectDevice={(id) => { setSelectedDeviceId(id); setAssistantOpen(false) }} onEvidenceStart={startEvidenceRequest} onActionStart={startAction} onRefresh={() => void load()} />
              </Dialog.Content>
            </Dialog.Portal>
          </Dialog.Root>
          <TicketWorkspaceTabs detail={detail} facts={facts} token={token} onSelectDevice={(id) => { setSelectedDeviceId(id); setAssistantOpen(false) }} />
        </div>
      )}
    </main>
  )
}
