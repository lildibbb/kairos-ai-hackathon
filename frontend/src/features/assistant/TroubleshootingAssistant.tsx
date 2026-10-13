import { Fragment, useCallback, useEffect, useRef, useState } from 'react'
import { Scene3D } from '../../components/illustration/Scene3D'
import { motion, useReducedMotion } from 'framer-motion'
import { reveal } from '../../lib/motion'
import { Button } from '../../components/ui/button'
import { TicketsApiError, revealServiceCredential } from '../../lib/api/tickets'
import type { Device, ServiceDetail } from '../../lib/api/tickets'
import { askAssistantWithStream, type AssistantAnswer, type AssistantStep } from '../../lib/api/assistant'
import type { AgentActivityReporter } from '../../lib/assistant/agent-activity'
import { AgentActionPlan } from './AgentActionPlan'
import { NextBestActionPanel } from '../work/NextBestActionPanel'
import { OperationStatusLabel } from '../../components/ai/status'
import {
  Chatbot,
  ChatbotHeader,
  ChatbotMessage,
  ChatbotPromptInput,
  ChatbotSuggestions,
} from '@/components/ai/chatbot'
import { EvidenceCitation } from './EvidenceCitation'
import { Streamdown } from 'streamdown'
import type { IncidentStage } from '../work/IncidentTrace'
import type { ToolExecution } from '../../lib/api/tools'
import { readConversation, writeConversation, type StoredConversationTurn } from '../../lib/assistant/conversation-storage'
import { Reasoning } from '@/components/ai/reasoning'
import { Sources } from '@/components/ai/sources'
import { ChatsCircle } from '@phosphor-icons/react'
import { Books, Brain, CircleNotch, Database, MagnifyingGlass, ShieldCheck, Ticket, Wrench, type Icon } from '@phosphor-icons/react'
import {
  Conversation,
  ConversationContent,
  ConversationScrollButton,
} from '@/components/ai/conversation'
import {
  ChainOfThoughtSearchResults,
  ChainOfThoughtSearchResult,
  ChainOfThoughtStep,
} from '@/components/ai/chain-of-thought'

type Turn = StoredConversationTurn
function hasUnconfirmedOutcome(turn: Turn) {
  return turn.state === 'error' && /stream closed before|reply did not finish/i.test(turn.message ?? '')
}

type TroubleshootingAssistantProps = {
  ticketId: string
  token: string
  userId?: string
  devices: Device[]
  services?: ServiceDetail[]
  onAnswer?: (answer: AssistantAnswer) => void
  onSelectDevice?: (deviceId: string) => void
  onEvidenceProgress?: (stage: IncidentStage) => void
  onEvidenceStart?: () => NonNullable<TroubleshootingAssistantProps['onEvidenceProgress']>
  onActionProgress?: (stage: IncidentStage, outcome?: ToolExecution) => void
  onActionStart?: (deviceId?: string) => NonNullable<TroubleshootingAssistantProps['onActionProgress']>
  onRefresh?: () => void
  investigationRequest?: number
  onAgentActivity?: AgentActivityReporter
}

const STEP_ICON: Record<string, Icon> = {
  context: Ticket,
  facts: Database,
  retrieval: Books,
  model: Brain,
  guardrails: ShieldCheck,
}

function AgentSteps({ steps }: { steps: AssistantStep[] }) {
  return <ol className="agent-steps" aria-label="Agent progress">
    {steps.map((step) => {
      const StepIcon = STEP_ICON[step.id] ?? Wrench
      return <li key={step.id} className={`agent-step agent-step--${step.status}`}>
        <span className="agent-step__icon" aria-hidden="true">
          {step.status === 'running' ? <CircleNotch size={14} className="is-spinning" /> : <StepIcon size={14} weight="duotone" />}
        </span>
        <span className="agent-step__text"><span className="agent-step__label">{step.label}</span>{step.detail && <span className="agent-step__detail">{step.detail}</span>}</span>
      </li>
    })}
  </ol>
}

function EvidenceChain({ turn }: { turn: Turn }) {
  const pending = turn.state === 'pending'
  const answered = turn.state === 'answered'
  const citations = turn.answer?.citations ?? []
  const hasEvidence = Boolean(turn.answer?.has_evidence)
  const failed = turn.state === 'error'

  return (
    <Reasoning key={pending ? 'pending' : 'settled'} defaultOpen={pending} active={pending} title={pending ? 'Agent is working' : `Agent steps${turn.steps?.length ? ` (${turn.steps.length})` : ''}`} className="assistant-chain">
        {turn.steps && turn.steps.length > 0 ? <AgentSteps steps={turn.steps} /> : <>
        <ChainOfThoughtStep
          icon={MagnifyingGlass}
          label={pending ? 'Searching the ticket and knowledge base' : failed ? 'Search did not complete' : 'Searched the ticket and knowledge base'}
          description={
            pending
              ? turn.message ?? 'Connecting to the ticket assistant…'
              : failed
                ? 'Retrieval did not complete for this question.'
                : 'Matched the ticket context against indexed field procedures.'
          }
          status={pending ? 'active' : failed ? 'pending' : 'complete'}
        >
          {citations.length > 0 && (
            <ChainOfThoughtSearchResults>
              {citations.map((citation) => (
                <ChainOfThoughtSearchResult key={citation.chunk_id}>
                  {citation.section}
                </ChainOfThoughtSearchResult>
              ))}
            </ChainOfThoughtSearchResults>
          )}
        </ChainOfThoughtStep>
        <ChainOfThoughtStep
          icon={ShieldCheck}
          label={
            hasEvidence
              ? `Grounded the answer in ${citations.length} source${citations.length === 1 ? '' : 's'}`
              : pending ? 'Waiting for retrieved sources' : failed ? 'Evidence verification unavailable' : 'No matching source was found'
          }
          status={answered && hasEvidence ? 'complete' : 'pending'}
        />
        </>}
        {citations.length > 0 && turn.steps && turn.steps.length > 0 && (
          <ChainOfThoughtSearchResults>
            {citations.map((citation) => <ChainOfThoughtSearchResult key={citation.chunk_id}>{citation.section}</ChainOfThoughtSearchResult>)}
          </ChainOfThoughtSearchResults>
        )}
        {turn.answer?.next_best_action && (
          <ChainOfThoughtStep icon={Wrench} label="Prepared a next best action" status="complete" />
        )}
    </Reasoning>
  )
}

function AssistantAnswerBody({ answer }: { answer: AssistantAnswer }) {
  const reducedMotion = Boolean(useReducedMotion())
  return (
    <motion.div className="assistant-answer" variants={reveal} initial="hidden" animate="visible" custom={reducedMotion}>
      <div className="assistant-answer-text"><Streamdown mode="static">{answer.answer}</Streamdown></div>
      {answer.uncertainty && <p className="assistant-uncertainty">{answer.uncertainty}</p>}
      {!answer.has_evidence && !isCredentialQuestion(answer.answer) && (
        <p className="no-evidence-note">
          No knowledge document matched this question, so this answer has no cited source.
        </p>
      )}
      {answer.citations.length > 0 && (
        <Sources count={answer.citations.length} label="Retrieved evidence" className="citation-block">
          <ul className="citation-list">
            {answer.citations.map((citation, index) => (
              <EvidenceCitation key={citation.chunk_id} citation={citation} index={index} />
            ))}
          </ul>
        </Sources>
      )}
      {answer.next_best_action && (
        <NextBestActionPanel action={answer.next_best_action} citations={answer.citations} />
      )}
    </motion.div>
  )
}

function CredentialRequest({ ticketId, token, question, services = [] }: { ticketId: string; token: string; question: string; services?: ServiceDetail[] }) {
  const [state, setState] = useState<'idle' | 'loading' | 'revealed' | 'error'>('idle')
  const [value, setValue] = useState('')
  const loweredQuestion = question.toLowerCase()
  const service = services.find((item) => {
    const serviceType = item.service_type.toLowerCase()
    return ['iptv', 'vobb', 'hsi', 'internet'].some((type) => loweredQuestion.includes(type) && serviceType.includes(type))
  }) ?? services.find((item) => item.credential_available && item.service_type.toLowerCase() === 'vobb')
    ?? services.find((item) => item.credential_available)
  if (!service) return null
  const reveal = async () => {
    setState('loading')
    try {
      const result = await revealServiceCredential(ticketId, service.id, token)
      setValue(`${result.credential_type.replace(/_/g, ' ')}: ${result.credential}`)
      setState('revealed')
    } catch {
      setState('error')
    }
  }
  return <div className="credential-request" aria-live="polite">
    <p><strong>{service.service_type} credential available</strong> · {service.service_ref}</p>
    {state === 'revealed' ? <code>{value}</code> : <Button type="button" className="process-button" onClick={() => void reveal()} disabled={state === 'loading'}>{state === 'loading' ? 'Revealing credential…' : 'Reveal credential'}</Button>}
    {state === 'error' && <p className="form-error" role="alert">The credential could not be revealed. Retry.</p>}
  </div>
}

function isCredentialQuestion(question: string) {
  return /\b(credential|password|passcode|login|secret)\b/i.test(question)
}

function shouldOfferActionPlan(question: string) {
  return /\b(check|test|inspect|diagnose|configure|config|change|set|switch|move|rename|reserve|reboot|restart|reset|repair|fix|flush|block|optimi[sz]e|apply|run)\b/i.test(question)
}

export function TroubleshootingAssistant(props: TroubleshootingAssistantProps) {
  return <AssistantSession key={`${props.ticketId}:${props.userId ?? 'anonymous'}:${props.token}`} {...props} />
}

function AssistantSession({ ticketId, token, userId, devices, services, onAnswer, onSelectDevice, onEvidenceProgress, onEvidenceStart, onActionProgress, onActionStart, onRefresh, investigationRequest = 0, onAgentActivity }: TroubleshootingAssistantProps) {
  const [turns, setTurns] = useState<Turn[]>(() => userId ? readConversation(userId, ticketId) : [])
  const nextId = useRef(turns.reduce((largest, turn) => Math.max(largest, turn.id), 0) + 1)
  const active = useRef(true)
  const latestRequest = useRef(0)
  const lastInvestigationRequest = useRef(0)
  useEffect(() => { active.current = true; return () => { active.current = false } }, [])
  useEffect(() => { if (userId) writeConversation(userId, ticketId, turns) }, [ticketId, turns, userId])
  useEffect(() => {
    const latest = [...turns].reverse().find((turn) => turn.state === 'answered' && turn.answer && !isCredentialQuestion(turn.question))
    if (latest?.answer) onAnswer?.(latest.answer)
  }, [turns, onAnswer])

  const run = useCallback(
    async (id: number, question: string) => {
      const request = ++latestRequest.current
      const reportEvidence = onEvidenceStart?.() ?? onEvidenceProgress
      setTurns((current) =>
        current.map((turn) => (turn.id === id ? { ...turn, state: 'pending', activity: 'pending', message: undefined, steps: [] } : turn)),
      )
      onAgentActivity?.({ phase: 'thinking', label: 'Reading device health and the knowledge base' })
      try {
        const answer = await askAssistantWithStream(ticketId, question, token, (message) => {
          if (!active.current) return
          setTurns((current) => current.map((turn) => (turn.id === id ? { ...turn, message } : turn)))
          if (request === latestRequest.current || onEvidenceStart) reportEvidence?.({ id: 'evidence', label: 'Evidence', state: 'current', detail: message })
        }, (step) => {
          if (!active.current) return
          setTurns((current) => current.map((turn) => {
            if (turn.id !== id) return turn
            const steps = turn.steps ?? []
            return { ...turn, steps: steps.some((item) => item.id === step.id) ? steps.map((item) => item.id === step.id ? step : item) : [...steps, step] }
          }))
          if (step.status === 'running') onAgentActivity?.({ phase: 'thinking', label: step.label })
        })
        if (!active.current) return
        const plansAction = !isCredentialQuestion(question) && (Boolean(answer.action_intent) || shouldOfferActionPlan(question))
        if (!plansAction) onAgentActivity?.(null)
        setTurns((current) =>
          current.map((turn) => (turn.id === id ? { ...turn, state: 'answered', message: undefined, activity: answer.has_evidence ? 'completed' : 'no-evidence', answer } : turn)),
        )
        if (request === latestRequest.current || onEvidenceStart) reportEvidence?.({ id: 'evidence', label: 'Evidence', state: answer.has_evidence ? 'complete' : 'blocked', detail: answer.has_evidence ? 'Evidence returned' : 'No matching evidence returned' })
      } catch (error) {
        if (!active.current) return
        onAgentActivity?.(null)
        if (request === latestRequest.current || onEvidenceStart) reportEvidence?.({ id: 'evidence', label: 'Evidence', state: 'blocked', detail: error instanceof Error && /stream closed before/i.test(error.message) ? 'Outcome not confirmed' : 'Assistant request failed' })
        setTurns((current) =>
          current.map((turn) =>
            turn.id === id
              ? {
                  ...turn,
                  state: 'error',
                  activity: 'failed',
                  message:
                    error instanceof TicketsApiError
                      ? error.message
                      : 'The assistant could not answer this question.',
                }
              : turn,
          ),
        )
      }
    },
    [ticketId, token, onEvidenceProgress, onEvidenceStart, onAgentActivity],
  )

  useEffect(() => {
    if (investigationRequest <= 0 || investigationRequest === lastInvestigationRequest.current) return
    lastInvestigationRequest.current = investigationRequest
    const id = nextId.current++
    const question = 'Summarize this ticket'
    setTurns((current) => [...current, { id, question, state: 'pending', activity: 'pending' }])
    void run(id, question)
  }, [investigationRequest, run])

  const ask = (question: string) => {
    const id = nextId.current++
    setTurns((current) => [...current, { id, question, state: 'pending', activity: 'pending' }])
    void run(id, question)
  }

  const isSearching = turns.some((turn) => turn.state === 'pending')

  return (
    <Chatbot className="panel assistant-panel" aria-labelledby="assistant-heading">
      <ChatbotHeader
        label="Troubleshooting assistant"
        title="Investigate this incident"
        titleId="assistant-heading"
        context={<span className="assistant-context-label"><ChatsCircle size={16} aria-hidden="true" /> Ticket context included</span>}
      />

      {turns.length === 0 ? (
        <div className="assistant-empty">
          <Scene3D className="assistant-empty-scene" variant="signal" size={150} />
          <p className="assistant-empty-title">Find the fault.<br /><span>Follow the evidence.</span></p>
          <p className="muted-note">Ask a question about this incident. The assistant checks ticket details and service guidance, then shows the sources behind its answer.</p>
          <ChatbotSuggestions
            items={['What should I check first?', 'Why is the service down?', 'Summarize this ticket']}
            onSelect={ask}
          />
        </div>
      ) : (
        <Conversation className="assistant-conversation" aria-label="Ticket conversation">
          <ConversationContent className="assistant-thread">
            {turns.map((turn) => (
              <Fragment key={turn.id}>
                <ChatbotMessage from="user" roleLabel="You asked">
                  <p>{turn.question}</p>
                </ChatbotMessage>

                <ChatbotMessage from="assistant" roleLabel={turn.state === 'pending' ? 'Assistant · Investigating' : 'Assistant'}>
                    <p className="sr-only" role="status" aria-live="polite">{turn.state === 'pending' ? 'Pending' : hasUnconfirmedOutcome(turn) ? 'Outcome not confirmed' : turn.state === 'error' ? 'Failed' : turn.answer?.has_evidence ? 'Completed' : 'No evidence'}. {turn.message}</p>
                    <EvidenceChain turn={turn} />
                    {turn.state === 'pending' && (
                      <div className="response-generation" aria-label="Generating assistant response"><OperationStatusLabel status="searching" /><span>{[...(turn.steps ?? [])].reverse().find((step) => step.status === 'running')?.label ?? 'Connecting to the agent'}…</span></div>
                    )}
                    {turn.state === 'error' && (
                      <>
                        <OperationStatusLabel status={hasUnconfirmedOutcome(turn) ? 'unknown' : 'failed'} />
                        <p className="form-error" role="alert">
                          {turn.message}
                        </p>
                        <Button
                          className="process-button"
                          type="button"
                          onClick={() => void run(turn.id, turn.question)}
                        >
                          Retry this question
                        </Button>
                      </>
                    )}

                    {turn.state === 'answered' && turn.answer && (
                      <>
                        {turn.message && <p role="status" className="assistant-uncertainty">{turn.message}</p>}
                        <AssistantAnswerBody answer={turn.answer} />
                        {isCredentialQuestion(turn.question) && <CredentialRequest ticketId={ticketId} token={token} question={turn.question} services={services} />}
                        {!isCredentialQuestion(turn.question) && (Boolean(turn.answer.action_intent) || shouldOfferActionPlan(turn.question)) && (
                          <AgentActionPlan
                            ticketId={ticketId}
                            token={token}
                            question={turn.question}
                            devices={devices}
                            autoPrepare={Boolean(turn.answer.action_intent)}
                            onAgentActivity={onAgentActivity}
                            onSelectDevice={onSelectDevice}
                              onActionProgress={onActionProgress}
                              onActionStart={onActionStart}
                              onRefresh={onRefresh}
                              initialState={turn.action}
                              onStateChange={(action) => setTurns((current) => current.map((item) => item.id === turn.id ? { ...item, action } : item))}
                              onUnconfirmed={(message) => setTurns((current) => current.map((item) => item.id === turn.id ? { ...item, message } : item))}
                            />
                        )}
                      </>
                    )}
                </ChatbotMessage>
              </Fragment>
            ))}
          </ConversationContent>
          <ConversationScrollButton />
        </Conversation>
      )}

      <ChatbotPromptInput onSubmit={ask} disabled={false} isSearching={isSearching} />
    </Chatbot>
  )
}
