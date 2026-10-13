import { useEffect, useRef, useState } from 'react'
import { Check, X } from '@phosphor-icons/react'
import { Button } from '../../components/ui/button'
import { Card, CardContent, CardHeader } from '../../components/ui/card'
import { Label } from '../../components/ui/label'
import { Select, SelectItem } from '../../components/ui/select'
import type { Device } from '../../lib/api/tickets'
import { TicketsApiError } from '../../lib/api/tickets'
import {
  confirmTool,
  executionFromProposal,
  fetchAgentPlan,
  proposeAgentTool,
  type AgentPlan,
  type AgentPlanSuggestion,
  type ToolExecution,
  type ToolProposal,
  type ToolResult,
  type TraceStep,
} from '../../lib/api/tools'
import { ActionProposal } from './ActionProposal'
import { ToolActivity } from './ToolActivity'
import { ToolExecutionResult } from './ToolExecutionResult'
import { ToolCall } from '../../components/ai/tool-call'
import { ToolCallTimeline } from './ToolCallTimeline'
import {
  Confirmation,
  ConfirmationAccepted,
  ConfirmationAction,
  ConfirmationActions,
  ConfirmationRejected,
  ConfirmationRequest,
  ConfirmationTitle,
} from '@/components/ai/confirmation'
import type { IncidentStage } from '../work/IncidentTrace'
import type { StoredActionState } from '../../lib/assistant/conversation-storage'
import { type AgentActivityReporter, type AgentPhase, toolSignature, wait } from '../../lib/assistant/agent-activity'
import { ToolRunStatus } from './ToolRunStatus'
import { AgentReasoning } from './AgentReasoning'
import { resultMetrics, stepFocus, toolMeta } from './tool-meta'

type AgentActionPlanProps = {
  ticketId: string
  token: string
  question: string
  devices: Device[]
  onSelectDevice?: (deviceId: string) => void
  onActionProgress?: (stage: IncidentStage, outcome?: ToolExecution) => void
  onActionStart?: (deviceId?: string) => NonNullable<AgentActionPlanProps['onActionProgress']>
  initialState?: StoredActionState
  onStateChange?: (state: StoredActionState) => void
  onUnconfirmed?: (message: string) => void
  onRefresh?: () => void
  /** The request named an action outright; prepare the top-ranked tool call without a click. */
  autoPrepare?: boolean
  onAgentActivity?: AgentActivityReporter
}

type LiveRun = {
  suggestion: AgentPlanSuggestion
  phase: AgentPhase
  message?: string
  trace: TraceStep[]
  activeStep?: TraceStep
  progress?: number
  result?: ToolResult | null
  startedAt: number
}
type TrackExtra = Partial<Pick<LiveRun, 'trace' | 'activeStep' | 'progress' | 'result'>> & { focusIds?: string[]; metrics?: AgentActivityMetrics }
type AgentActivityMetrics = Parameters<AgentActivityReporter>[0] extends infer A ? A extends { metrics?: infer M } ? M : never : never

const PLANNING_LINES = ['Reading router telemetry', 'Checking client signal and channels', 'Searching the knowledge base', 'Ranking allowlisted tools', 'Validating parameters and target']

function PlanningPulse() {
  const [index, setIndex] = useState(0)
  useEffect(() => {
    const timer = setInterval(() => setIndex((current) => Math.min(current + 1, PLANNING_LINES.length - 1)), 900)
    return () => clearInterval(timer)
  }, [])
  return <ol className="planning-pulse" aria-label="Agent planning progress">
    {PLANNING_LINES.slice(0, index + 1).map((line, position) => <li key={line} className={position === index ? 'is-active' : 'is-done'}>
      <span aria-hidden="true" />{line}{position === index ? '…' : ''}
    </li>)}
  </ol>
}

const RISK_LABEL: Record<AgentPlanSuggestion['risk'], string> = {
  low: 'Low risk',
  medium: 'Needs approval',
  high: 'High impact',
}

export function AgentActionPlan(props: AgentActionPlanProps) {
  return <ActionPlanSession key={`${props.ticketId}:${props.token}:${props.question}`} {...props} />
}

function ActionPlanSession({ ticketId, token, question, devices, onSelectDevice, onActionProgress, onActionStart, initialState, onStateChange, onUnconfirmed, onRefresh, autoPrepare = false, onAgentActivity }: AgentActionPlanProps) {
  const active = useRef(true)
  const started = useRef(false)
  const clearTimer = useRef<ReturnType<typeof setTimeout>>()
  useEffect(() => { active.current = true; return () => { active.current = false; clearTimeout(clearTimer.current) } }, [])
  const [live, setLive] = useState<LiveRun | null>(null)
  const deviceName = (id: string, fallback: string) => devices.find((device) => device.id === id)?.name ?? fallback
  const track = (suggestion: AgentPlanSuggestion, phase: AgentPhase, message?: string, extra: TrackExtra = {}) => {
    clearTimeout(clearTimer.current)
    const { focusIds, metrics, ...runExtra } = extra
    setLive((current) => {
      const same = current?.suggestion.tool_name === suggestion.tool_name && current.suggestion.device_id === suggestion.device_id
      const base: LiveRun = same && current ? current : { suggestion, phase, trace: [], startedAt: Date.now() }
      return { ...base, ...runExtra, suggestion, phase, message: message ?? (phase === base.phase ? base.message : undefined) }
    })
    const target = deviceName(suggestion.device_id, suggestion.device_ref)
    onAgentActivity?.({
      phase,
      deviceId: suggestion.device_id,
      toolName: suggestion.tool_name,
      toolKind: suggestion.kind,
      label: phase === 'succeeded' || phase === 'failed' ? message ?? suggestion.title : `${toolMeta(suggestion.tool_name).verb} → ${target}`,
      step: extra.activeStep?.label,
      progress: extra.progress,
      focusIds,
      metrics,
    })
    if (phase === 'succeeded' || phase === 'failed') {
      clearTimer.current = setTimeout(() => onAgentActivity?.(null), 9000)
    }
  }

  // Replays the device trace returned by the simulator as a live stream, moving
  // the topology focus with each step. Without a trace, hold for fallbackMs.
  const replay = async (suggestion: AgentPlanSuggestion, result: ToolResult | null | undefined, fallbackMs: number) => {
    const steps = result?.trace ?? []
    if (steps.length === 0) {
      await wait(fallbackMs)
      return active.current
    }
    const done: TraceStep[] = []
    for (const [index, step] of steps.entries()) {
      if (!active.current) return false
      track(suggestion, 'executing', undefined, {
        trace: [...done], activeStep: step, progress: index / steps.length,
        focusIds: stepFocus(result, index, suggestion.device_id),
      })
      await wait(Math.min(Math.max(step.ms, 300), 1200))
      done.push(step)
    }
    if (!active.current) return false
    track(suggestion, 'executing', undefined, { trace: [...done], activeStep: undefined, progress: 1 })
    return true
  }

  const finish = (suggestion: AgentPlanSuggestion, outcome: { status: string; message: string; result?: ToolResult | null }) => {
    track(suggestion, outcome.status === 'succeeded' ? 'succeeded' : 'failed', outcome.message, {
      result: outcome.result, activeStep: undefined, progress: 1,
      metrics: outcome.status === 'succeeded' ? resultMetrics(suggestion.tool_name, outcome.result, suggestion.device_id) : undefined,
      focusIds: stepFocus(outcome.result, Number.MAX_SAFE_INTEGER, suggestion.device_id),
    })
  }
  const [deviceId, setDeviceId] = useState('')
  const [plan, setPlan] = useState<AgentPlan | null>(initialState?.plan ?? null)
  const [planning, setPlanning] = useState(false)
  const [proposing, setProposing] = useState<string | null>(null)
  const [proposal, setProposal] = useState<ToolProposal | null>(initialState?.proposal ?? null)
  const [execution, setExecution] = useState<ToolExecution | null>(initialState?.execution ?? null)
  const [rejected, setRejected] = useState(initialState?.rejected ?? false)
  const [attempts, setAttempts] = useState<{ proposal: ToolProposal | null; execution: ToolExecution }[]>(initialState?.attempts ?? [])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [unknownAttempts, setUnknownAttempts] = useState<ToolProposal[]>([])

  useEffect(() => {
    onStateChange?.({ plan, proposal, execution, rejected, attempts })
  }, [attempts, execution, plan, proposal, rejected])

  const buildPlan = async (overrideDeviceId?: string) => {
    if (planning) return
    const report = onActionStart?.(deviceId || undefined) ?? onActionProgress
    setPlanning(true)
    setError('')
    setRejected(false)
    setPlan(null)
    report?.({ id: 'action', label: 'Action', state: 'current', detail: 'Reasoning over evidence' })
    onAgentActivity?.({ phase: 'planning', label: 'Choosing the right tool and target device', deviceId: overrideDeviceId || deviceId || undefined })
    let autoTarget: AgentPlanSuggestion | undefined
    try {
      const result = await fetchAgentPlan(ticketId, { question, deviceId: overrideDeviceId || deviceId || undefined }, token)
      if (!active.current) return
      setPlan(result)
      if (result.device_id) {
        setDeviceId(result.device_id)
      }
      const top = result.suggestions[0]
      if (top && autoPrepare && !overrideDeviceId && top.confidence >= 0.85) autoTarget = top
      else if (top) onAgentActivity?.({ phase: 'awaiting', label: 'Plan ready: pick an action', deviceId: top.device_id, toolName: top.tool_name, toolKind: top.kind })
      else onAgentActivity?.(null)
      report?.({
        id: 'action',
        label: 'Action',
        state: result.suggestions.length > 0 ? 'current' : 'blocked',
        detail: result.suggestions.length > 0 ? 'Action plan ready for review' : 'No grounded action available',
      })
    } catch (caught) {
      if (!active.current) return
      report?.({ id: 'action', label: 'Action', state: 'blocked', detail: 'Plan request failed' })
      setError(caught instanceof TicketsApiError ? caught.message : 'The agent could not build an action plan.')
      onAgentActivity?.(null)
    } finally {
      if (active.current) setPlanning(false)
    }
    if (autoTarget && active.current) await prepare(autoTarget)
  }

  useEffect(() => {
    if (started.current) return
    started.current = true
    if (initialState) return
    // Every grounded answer gets an action decision. The planner may return
    // diagnostics or no safe action, but the technician never has to discover
    // a second manual planning workflow.
    void buildPlan()
    // The session is keyed by ticket/question, so this runs once per turn.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const prepare = async (suggestion: AgentPlanSuggestion) => {
    if (busy || proposing) return
    const report = onActionStart?.(suggestion.device_id) ?? onActionProgress
    setBusy(true)
    setProposing(suggestion.tool_name)
    report?.({ id: 'action', label: 'Action', state: 'current', detail: `Preparing ${suggestion.title}` })
    setError('')
    setRejected(false)
    if (execution) setAttempts((current) => [...current, { proposal, execution }])
    setProposal(null)
    setExecution(null)
    track(suggestion, suggestion.kind === 'read_only' ? 'executing' : 'planning')
    try {
      const [created] = await Promise.all([
        proposeAgentTool(
          ticketId,
          { question, deviceId: suggestion.device_id, toolName: suggestion.tool_name, parameters: suggestion.parameters },
          token,
        ),
        wait(suggestion.kind === 'read_only' ? 500 : 700),
      ])
      if (!active.current) return
      const outcome = executionFromProposal(created)
      if (outcome) {
        if (!await replay(suggestion, outcome.result, 900)) return
        track(suggestion, 'verifying', undefined, { progress: 1 })
        await wait(600)
        if (!active.current) return
        finish(suggestion, outcome)
      } else {
        track(suggestion, 'awaiting')
      }
      setProposal(created)
      setExecution(outcome)
      if (outcome) {
        report?.({ id: 'action', label: 'Action', state: outcome.status === 'succeeded' ? 'complete' : 'blocked', detail: outcome.message }, outcome)
      } else {
        report?.({ id: 'action', label: 'Action', state: 'current', detail: 'Proposal ready for review' })
      }
    } catch (caught) {
      if (!active.current) return
      report?.({ id: 'action', label: 'Action', state: 'blocked', detail: 'Proposal request failed' })
      track(suggestion, 'failed', caught instanceof TicketsApiError ? caught.message : 'The action could not be prepared.')
      setError(caught instanceof TicketsApiError ? caught.message : 'The action could not be prepared.')
    } finally {
      if (active.current) { setBusy(false); setProposing(null) }
    }
  }

  const confirm = async () => {
    if (!proposal || execution || !proposal.requires_confirmation || proposal.status !== 'proposed' || busy) return
    const report = onActionStart?.(proposal.device_id) ?? onActionProgress
    setBusy(true)
    setExecution(null)
    report?.({ id: 'action', label: 'Action', state: 'current', detail: 'Awaiting execution result' })
    setProposal(null)
    onUnconfirmed?.(`Outcome not confirmed for ${proposal.tool_name} on ${proposal.device_ref}. Proposal reference: ${proposal.id}. Check audit history before preparing another action.`)
    setError('')
    const running = live?.suggestion
    if (running) track(running, 'executing', undefined, { trace: [], activeStep: undefined, progress: undefined })
    try {
      const [result] = await Promise.all([
        confirmTool(ticketId, proposal.id, proposal.confirmation_id, token),
        wait(600),
      ])
      if (!active.current) return
      if (running) {
        if (!await replay(running, result.result, running.tool_name.startsWith('reboot') ? 2000 : 1200)) return
        track(running, 'verifying', undefined, { progress: 1 })
        await wait(800)
        if (!active.current) return
        finish(running, result)
      }
      setExecution(result)
      onUnconfirmed?.('')
       setProposal(proposal)
       onRefresh?.()
      report?.({ id: 'action', label: 'Action', state: result.status === 'succeeded' ? 'complete' : 'blocked', detail: result.message }, result)
    } catch (caught) {
      if (!active.current) return
      report?.({ id: 'action', label: 'Action', state: 'blocked', detail: 'Outcome not confirmed. Check audit history before creating a new proposal.' })
      if (running) track(running, 'failed', 'Outcome not confirmed')
      setUnknownAttempts((current) => [...current, proposal])
      setProposal(null)
      setError(caught instanceof TicketsApiError ? caught.message : 'The action could not be executed.')
    } finally {
      if (active.current) setBusy(false)
    }
  }

  const reject = () => {
    const report = onActionStart?.(deviceId) ?? onActionProgress
    setProposal(null)
    setExecution(null)
    setError('')
    setRejected(true)
    setLive(null)
    onAgentActivity?.(null)
    report?.({ id: 'action', label: 'Action', state: 'blocked', detail: 'Action rejected by technician' })
  }

  const reset = () => {
    const report = onActionStart?.(deviceId) ?? onActionProgress
    if (execution) setAttempts((current) => [...current, { proposal, execution }])
    setProposal(null)
    setExecution(null)
    setError('')
    report?.({ id: 'action', label: 'Action', state: 'upcoming', detail: 'Ready for another action' })
  }

  const awaitingApproval = Boolean(proposal && !execution && proposal.requires_confirmation && proposal.status === 'proposed')
  const hasSuggestions = Boolean(plan && plan.suggestions.length > 0)
  const showIdle = !proposal && !execution && !plan && !planning

  return (
    <Card className="agent-suggested-action" aria-label="Agent action plan">
      <CardHeader>
        <h4>Action plan</h4>
        <p className="tool-call-intro">
          The assistant reasons over the ticket evidence, picks the target device, and ranks grounded actions.
          Read-only checks run when requested. Changes require a reviewed proposal and approval.
        </p>
      </CardHeader>
      <CardContent><ToolCallTimeline>
        {plan && <AgentReasoning plan={plan} />}
        {live && <ToolRunStatus
          key={`${live.suggestion.tool_name}:${live.startedAt}`}
          toolName={live.suggestion.tool_name}
          signature={toolSignature(live.suggestion.tool_name, live.suggestion.parameters)}
          target={deviceName(live.suggestion.device_id, live.suggestion.device_ref)}
          stateful={live.suggestion.kind === 'stateful'}
          phase={live.phase}
          message={live.message}
          reasoning={live.suggestion.reasoning}
          trace={live.trace}
          activeStep={live.activeStep}
          progress={live.progress}
          result={live.result}
          startedAt={live.startedAt} />}
        {planning && <PlanningPulse />}
        {showIdle && (
          <>
            {rejected && <p className="muted-note">Action rejected. Ask the agent to plan a different approach.</p>}
            <Button className="process-button" type="button" onClick={() => void buildPlan()} disabled={busy || devices.length === 0}>
              Ask agent to build an action plan
            </Button>
          </>
        )}

        {error && (
          <>
            <p className="form-error" role="alert">
              {error}
            </p>
            {!planning && (
              <Button className="process-button" type="button" onClick={() => void buildPlan()} disabled={busy}>
                Retry the plan
              </Button>
            )}
          </>
        )}

        {(planning || (proposal && !execution)) && <ToolActivity
           state={planning || (busy && Boolean(proposal)) ? 'pending' : execution ? 'completed' : proposal?.requires_confirmation ? 'needs-approval' : 'completed'}
           label={planning ? 'Reasoning over evidence' : proposal ? proposal.tool_name : 'Action plan'}
           description={planning ? 'Ranking the grounded actions for this ticket.' : busy ? 'Awaiting the execution result from the action service.' : 'Proposal is ready for review. No action has run.'}
           detail={proposal ? `${proposal.device_ref} · ${proposal.kind === 'read_only' ? 'read-only' : 'changes device state'}` : undefined} />}

        {plan && !proposal && !execution && !(live && (live.phase === 'executing' || live.phase === 'verifying')) && (
          <div className="agent-plan">
            <p className="agent-plan__summary">{plan.summary || 'Recommended next actions, grounded in the cited procedure.'}</p>

            {devices.length > 1 && (
              <Label className="field agent-plan__device">
                <span>Target device</span>
                <Select
                  value={plan.device_id}
                  onValueChange={(value) => void buildPlan(value)}
                  disabled={planning || busy}
                  aria-label="Target device"
                >
                  {devices.map((device) => (
                    <SelectItem key={device.id} value={device.id}>
                      {device.device_ref} ({device.device_type})
                    </SelectItem>
                  ))}
                </Select>
              </Label>
            )}

            {hasSuggestions ? (
              <ol className="agent-plan__list">
                {plan.suggestions.map((suggestion, index) => (
                  <li key={suggestion.tool_name} className="agent-plan__card">
                    <div className="agent-plan__head">
                      <span className="agent-plan__rank">{(() => { const Icon = toolMeta(suggestion.tool_name).icon; return index === 0 ? <Icon size={15} weight="bold" aria-label="Top choice" /> : index + 1 })()}</span>
                      <div>
                        <p className="agent-plan__title">{suggestion.title}</p>
                        <p className="agent-plan__target-name">{suggestion.device_ref} · {suggestion.device_type}</p>
                      </div>
                      <span className={`risk-badge risk-badge--${suggestion.risk}`}>{RISK_LABEL[suggestion.risk]}</span>
                    </div>
                    <p className="agent-plan__rationale">{suggestion.rationale}</p>
                    {suggestion.reasoning && <div className="agent-plan__reasoning">
                      <span className={`agent-plan__trigger is-${suggestion.reasoning.trigger}`}>
                        {suggestion.reasoning.trigger === 'request' ? 'You asked' : suggestion.reasoning.trigger === 'telemetry' ? 'Telemetry' : 'Model plan'}
                      </span>
                      {suggestion.reasoning.expected && <span><b>Expected:</b> {suggestion.reasoning.expected}</span>}
                      {suggestion.kind === 'stateful' && suggestion.reasoning.rollback && <span><b>Rollback:</b> {suggestion.reasoning.rollback}</span>}
                    </div>}
                    {suggestion.steps.length > 0 && (
                      <div className="agent-plan__steps">
                        <p className="agent-plan__steps-label">
                          {suggestion.kind === 'read_only' ? 'Check steps' : 'Configuration plan'}
                        </p>
                        <ol>
                          {suggestion.steps.map((step) => <li key={step}>{step}</li>)}
                        </ol>
                      </div>
                    )}
                    <div className="agent-plan__meta">
                      <span className="agent-plan__kind">
                        {suggestion.kind === 'read_only' ? 'Read-only check' : 'Changes device state'}
                      </span>
                      <span className="agent-plan__confidence">Confidence {Math.round(suggestion.confidence * 100)}%</span>
                    </div>
                    <Button
                      className="process-button"
                      type="button"
                      onClick={() => void prepare(suggestion)}
                      disabled={busy}
                    >
                      {proposing === suggestion.tool_name ? 'Preparing…' : suggestion.kind === 'read_only' ? 'Run this check' : 'Prepare this action'}
                    </Button>
                  </li>
                ))}
              </ol>
            ) : (
              <p className="muted-note">
                The agent could not ground an action on {devices.find((device) => device.id === plan.device_id)?.device_ref ?? 'this device'}.
                Try another target device or ask about the observed symptoms.
              </p>
            )}

            {rejected && <p className="muted-note">Previous action rejected. Pick another ranked action above.</p>}
            <div className="agent-plan__actions">
              <Button type="button" variant="quiet" disabled={planning || busy} onClick={() => void buildPlan()}>
                Rebuild plan
              </Button>
              <Button type="button" variant="quiet" disabled={busy} onClick={() => { setPlan(null); setError('') }}>
                Clear plan
              </Button>
            </div>
          </div>
        )}

        {awaitingApproval && proposal && (
          <>
            <ActionProposal proposal={proposal} onSelectDevice={onSelectDevice} />
            <Confirmation approval={{ id: proposal.id }} state="approval-requested" className="action-confirmation">
              <ConfirmationTitle>
                <ConfirmationRequest>
                  <span className="confirmation-request-text">
                    {!proposal.requires_confirmation
                      ? 'This check reads device status and does not change settings.'
                      : 'This action changes device state. Review the target and parameters before it runs.'}
                  </span>
                </ConfirmationRequest>
                <ConfirmationAccepted>
                  <Check size={16} className="action-approved-icon" aria-hidden="true" />
                  <span>You approved this simulated action</span>
                </ConfirmationAccepted>
                <ConfirmationRejected>
                  <X size={16} className="action-rejected-icon" aria-hidden="true" />
                  <span>You rejected this simulated action</span>
                </ConfirmationRejected>
              </ConfirmationTitle>
              <ConfirmationActions>
                <ConfirmationAction variant="outline" onClick={reject} disabled={busy}>
                  Reject
                </ConfirmationAction>
                <ConfirmationAction onClick={() => void confirm()} disabled={busy}>
                  {busy ? 'Awaiting result…' : 'Approve and run'}
                </ConfirmationAction>
              </ConfirmationActions>
            </Confirmation>
          </>
        )}

        {execution && proposal && proposal.requires_confirmation && <ActionProposal proposal={proposal} recorded onSelectDevice={onSelectDevice} />}
        {execution && <ToolExecutionResult key={execution.id} execution={execution} onSelectDevice={onSelectDevice}
          readOnly={proposal?.kind === 'read_only'} expandResult={!live || live.phase !== 'succeeded'}
          runAnotherLabel={execution.status === 'failed' ? 'Retry with a new plan' : undefined}
          onRunAnother={execution.status === 'failed' ? () => { setAttempts((current) => [...current, { proposal, execution }]); setPlan(null); setExecution(null); setProposal(null); setError('') } : reset} />}
        {unknownAttempts.map((attempt) => <ToolCall key={attempt.id} title={attempt.tool_name} status="unknown" target={attempt.device_ref} correlationId={attempt.id}><p>The request ended before its outcome was confirmed. Review audit history before preparing another action.</p></ToolCall>)}
        {attempts.map((attempt) => <section key={attempt.execution.id} aria-label="Previous action attempt">
          {attempt.proposal?.requires_confirmation && <ActionProposal proposal={attempt.proposal} recorded onSelectDevice={onSelectDevice} />}
          <ToolExecutionResult execution={attempt.execution} onSelectDevice={onSelectDevice} />
        </section>)}
      </ToolCallTimeline></CardContent>
    </Card>
  )
}
