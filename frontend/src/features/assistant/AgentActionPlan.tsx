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
}

const RISK_LABEL: Record<AgentPlanSuggestion['risk'], string> = {
  low: 'Low risk',
  medium: 'Needs approval',
  high: 'High impact',
}

export function AgentActionPlan(props: AgentActionPlanProps) {
  return <ActionPlanSession key={`${props.ticketId}:${props.token}:${props.question}`} {...props} />
}

function ActionPlanSession({ ticketId, token, question, devices, onSelectDevice, onActionProgress, onActionStart, initialState, onStateChange, onUnconfirmed, onRefresh }: AgentActionPlanProps) {
  const active = useRef(true)
  const started = useRef(false)
  useEffect(() => { active.current = true; return () => { active.current = false } }, [])
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
    try {
      const result = await fetchAgentPlan(ticketId, { question, deviceId: overrideDeviceId || deviceId || undefined }, token)
      if (!active.current) return
      setPlan(result)
      if (result.device_id) {
        setDeviceId(result.device_id)
      }
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
    } finally {
      if (active.current) setPlanning(false)
    }
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
    try {
      const created = await proposeAgentTool(
        ticketId,
        { question, deviceId: suggestion.device_id, toolName: suggestion.tool_name, parameters: suggestion.parameters },
        token,
      )
      if (!active.current) return
      setProposal(created)
      const outcome = executionFromProposal(created)
      setExecution(outcome)
      if (outcome) {
        report?.({ id: 'action', label: 'Action', state: outcome.status === 'succeeded' ? 'complete' : 'blocked', detail: outcome.message }, outcome)
      } else {
        report?.({ id: 'action', label: 'Action', state: 'current', detail: 'Proposal ready for review' })
      }
    } catch (caught) {
      if (!active.current) return
      report?.({ id: 'action', label: 'Action', state: 'blocked', detail: 'Proposal request failed' })
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
    try {
       const result = await confirmTool(ticketId, proposal.id, proposal.confirmation_id, token)
       if (!active.current) return
      if (!active.current) return
      setExecution(result)
      onUnconfirmed?.('')
       setProposal(proposal)
       onRefresh?.()
      report?.({ id: 'action', label: 'Action', state: result.status === 'succeeded' ? 'complete' : 'blocked', detail: result.message }, result)
    } catch (caught) {
      if (!active.current) return
      report?.({ id: 'action', label: 'Action', state: 'blocked', detail: 'Outcome not confirmed. Check audit history before creating a new proposal.' })
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

        {plan && !proposal && !execution && (
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
                      <span className="agent-plan__rank">{index + 1}</span>
                      <div>
                        <p className="agent-plan__title">{suggestion.title}</p>
                        <p className="agent-plan__target-name">{suggestion.device_ref} · {suggestion.device_type}</p>
                      </div>
                      <span className={`risk-badge risk-badge--${suggestion.risk}`}>{RISK_LABEL[suggestion.risk]}</span>
                    </div>
                    <p className="agent-plan__rationale">{suggestion.rationale}</p>
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
