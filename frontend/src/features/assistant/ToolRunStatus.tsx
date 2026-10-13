import { useEffect, useRef, useState } from 'react'
import { CheckCircle, CircleNotch, Circle, WarningCircle } from '@phosphor-icons/react'
import type { AgentPhase } from '../../lib/assistant/agent-activity'
import type { ToolReasoning, ToolResult, TraceStep } from '../../lib/api/tools'
import { toolMeta } from './tool-meta'
import { ToolResultView } from './ToolResultView'

type StepState = 'done' | 'active' | 'pending' | 'failed'

const ORDER: AgentPhase[] = ['planning', 'awaiting', 'executing', 'verifying', 'succeeded']

function stepState(step: AgentPhase, phase: AgentPhase): StepState {
  if (phase === 'failed') return step === 'succeeded' ? 'failed' : 'done'
  const current = ORDER.indexOf(phase)
  const index = ORDER.indexOf(step)
  if (index < current || phase === 'succeeded') return 'done'
  return index === current ? 'active' : 'pending'
}

const PHASE_PILL: Partial<Record<AgentPhase, string>> = {
  planning: 'Preparing', awaiting: 'Needs approval', executing: 'Running', verifying: 'Verifying', succeeded: 'Done', failed: 'Failed',
}

function useElapsed(running: boolean, startedAt: number) {
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    if (!running) return
    const timer = setInterval(() => setNow(Date.now()), 100)
    return () => clearInterval(timer)
  }, [running])
  return Math.max(0, (running ? now : Math.max(now, startedAt)) - startedAt)
}

export type ToolRunStatusProps = {
  toolName?: string
  signature: string
  target: string
  stateful: boolean
  phase: AgentPhase
  message?: string
  reasoning?: ToolReasoning
  /** Trace steps already replayed. */
  trace?: TraceStep[]
  /** The step currently streaming. */
  activeStep?: TraceStep
  progress?: number
  result?: ToolResult | null
  startedAt?: number
}

/** Live tool call: why it was chosen, each streamed device step, then the structured result. */
export function ToolRunStatus({ toolName = '', signature, target, stateful, phase, message, reasoning, trace = [], activeStep, progress, result, startedAt }: ToolRunStatusProps) {
  const [started] = useState(() => startedAt ?? Date.now())
  const running = phase === 'executing' || phase === 'verifying' || phase === 'planning'
  const elapsed = useElapsed(running, started)
  const meta = toolMeta(toolName)
  const ref = useRef<HTMLElement>(null)
  // Keep the live call in view as it moves through approval, execution and result.
  useEffect(() => {
    ref.current?.scrollIntoView?.({ block: 'nearest', behavior: 'smooth' })
  }, [phase, trace.length])
  const Icon = meta.icon
  const phases: { id: AgentPhase; label: string }[] = [
    { id: 'planning', label: `Selected tool for ${target}` },
    ...(stateful ? [{ id: 'awaiting' as const, label: 'Waiting for your approval' }] : []),
    { id: 'executing', label: stateful ? `Sending command to ${target}` : `Running check on ${target}` },
    { id: 'verifying', label: 'Verifying device state' },
    { id: 'succeeded', label: phase === 'failed' ? message ?? 'Action failed' : phase === 'succeeded' ? message ?? 'Completed' : 'Completed' },
  ]
  const showConsole = trace.length > 0 || Boolean(activeStep) || phase === 'executing'
  return <section ref={ref} className={`tool-run tool-run--${phase} tool-run--${meta.tone}`} aria-label="Tool call status" aria-live="polite">
    <header className="tool-run__header">
      <span className="tool-run__icon-tile" aria-hidden="true"><Icon size={18} weight="duotone" /></span>
      <div className="tool-run__title">
        <span className="tool-run__badge">Tool call</span>
        <strong>{meta.verb} · {target}</strong>
        <code className="tool-run__signature">{signature}</code>
      </div>
      <div className="tool-run__meta">
        <span className={`tool-run__pill is-${phase}`}>{PHASE_PILL[phase] ?? phase}</span>
        <span className="tool-run__timer tabular" aria-label="Elapsed time">{(elapsed / 1000).toFixed(1)}s</span>
      </div>
    </header>

    <ol className="tool-run__steps">
      {phases.map((step) => {
        const state = stepState(step.id, phase)
        return <li key={step.id} className={`tool-run__step is-${state}`}>
          <span className="tool-run__icon" aria-hidden="true">
            {state === 'done' ? <CheckCircle size={15} weight="fill" /> : state === 'active' ? <CircleNotch size={15} className="is-spinning" /> : state === 'failed' ? <WarningCircle size={15} weight="fill" /> : <Circle size={15} />}
          </span>
          <span>{step.label}</span>
        </li>
      })}
    </ol>

    {reasoning && (reasoning.why || reasoning.observations.length > 0) && <details className="tool-run__why" open={phase === 'awaiting' || phase === 'planning'}>
      <summary>Why this tool{reasoning.trigger === 'request' ? ' · you asked for it' : reasoning.trigger === 'telemetry' ? ' · telemetry triggered' : ''}</summary>
      {reasoning.observations.length > 0 && <ul className="tool-run__observations">{reasoning.observations.map((item) => <li key={item}>{item}</li>)}</ul>}
      <dl className="tool-run__reason-grid">
        {reasoning.why && <div><dt>Decision</dt><dd>{reasoning.why}</dd></div>}
        {reasoning.expected && <div><dt>Expected</dt><dd>{reasoning.expected}</dd></div>}
        {reasoning.risk && <div><dt>Impact</dt><dd>{reasoning.risk}</dd></div>}
        {reasoning.rollback && <div><dt>Rollback</dt><dd>{reasoning.rollback}</dd></div>}
      </dl>
      {reasoning.sources.length > 0 && <p className="tool-run__sources">Grounded in {reasoning.sources.join('; ')}</p>}
    </details>}

    {showConsole && <div className="tool-run__console" role="log" aria-label="Device telemetry stream">
      <p className="tool-run__console-head"><span /> {target} · simulated device session</p>
      <ol>
        {trace.map((step, index) => <li key={`${step.label}-${index}`} className={`is-${step.status}`}>
          <span className="tool-run__console-mark" aria-hidden="true">{step.status === 'warn' ? '!' : step.status === 'fail' ? '×' : '✓'}</span>
          <span className="tool-run__console-label">{step.label}</span>
          {step.detail && <span className="tool-run__console-detail">{step.detail}</span>}
        </li>)}
        {activeStep && <li className="is-active">
          <CircleNotch size={12} className="is-spinning tool-run__console-mark" aria-hidden="true" />
          <span className="tool-run__console-label">{activeStep.label}</span>
          {activeStep.detail && <span className="tool-run__console-detail">{activeStep.detail}</span>}
          <span className="tool-run__caret" aria-hidden="true" />
        </li>}
        {!activeStep && trace.length === 0 && phase === 'executing' && <li className="is-active">
          <CircleNotch size={12} className="is-spinning tool-run__console-mark" aria-hidden="true" />
          <span className="tool-run__console-label">Connecting to {target}</span><span className="tool-run__caret" aria-hidden="true" />
        </li>}
      </ol>
    </div>}

    {(phase === 'executing' || phase === 'verifying') && <div className={`tool-run__progress${progress === undefined ? ' is-indeterminate' : ''}`} aria-hidden="true">
      <span style={progress === undefined ? undefined : { width: `${Math.round(progress * 100)}%` }} />
    </div>}

    {phase === 'succeeded' && result && <div className="tool-run__result"><ToolResultView result={result} /></div>}
  </section>
}
