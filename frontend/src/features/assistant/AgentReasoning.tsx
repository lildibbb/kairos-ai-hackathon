import { BookOpen, Brain, Eye, Target, WarningCircle, XCircle } from '@phosphor-icons/react'
import type { AgentPlan } from '../../lib/api/tools'

const KIND = {
  observe: { icon: Eye, label: 'Observed' },
  recall: { icon: BookOpen, label: 'Recalled' },
  intent: { icon: Brain, label: 'Understood' },
  decide: { icon: Target, label: 'Decided' },
} as const

/** The agent's chain of thought for a plan: telemetry, knowledge, intent, decision, rejected options. */
export function AgentReasoning({ plan }: { plan: AgentPlan }) {
  if (plan.reasoning.length === 0) return null
  return <section className="agent-reasoning" aria-label="Agent reasoning">
    <header><Brain size={15} weight="duotone" aria-hidden="true" /><strong>Agent reasoning</strong><span>{plan.reasoning.length} steps</span></header>
    <ol className="agent-reasoning__chain">
      {plan.reasoning.map((line, index) => {
        const kind = KIND[line.kind as keyof typeof KIND] ?? KIND.observe
        const Icon = line.level === 'warn' ? WarningCircle : kind.icon
        return <li key={`${line.kind}-${index}`} className={`agent-reasoning__line is-${line.kind} is-${line.level}`} style={{ animationDelay: `${index * 140}ms` }}>
          <span className="agent-reasoning__icon" aria-hidden="true"><Icon size={13} weight={line.level === 'warn' ? 'fill' : 'bold'} /></span>
          <span className="agent-reasoning__kind">{kind.label}</span>
          <span className="agent-reasoning__text">{line.text}</span>
        </li>
      })}
    </ol>
    {plan.alternatives.length > 0 && <details className="agent-reasoning__alternatives">
      <summary>Considered and ruled out ({plan.alternatives.length})</summary>
      <ul>{plan.alternatives.map((item) => <li key={item.tool_name}>
        <XCircle size={13} aria-hidden="true" /><code>{item.tool_name}</code><span>{item.reason}</span>
      </li>)}</ul>
    </details>}
  </section>
}
