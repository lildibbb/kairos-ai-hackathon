import { Streamdown } from 'streamdown'
import type { AssistantAnswer } from '../../lib/api/assistant'
import { OperationStatusLabel } from '../../components/ai/status'
import { EvidenceCitation } from './EvidenceCitation'

export function AssistantEvidenceSummary({ answer, observed, onInvestigate }: { answer?: AssistantAnswer; observed?: string; onInvestigate?: () => void }) {
  const supported = Boolean(answer?.has_evidence && answer.citations.length)
  const supports = (references: string[] = []) => supported && references.some((reference) => answer?.citations.some((citation) => citation.chunk_id === reference))
  const summary = answer?.summary
  const assessment = summary?.problem?.trim() || answer?.answer
  const proposed = summary?.solution?.trim() || (supports(answer?.next_best_action?.evidence) ? answer?.next_best_action?.remediation : undefined)
  const product = summary?.product_recommendation?.trim() || (supports(answer?.next_best_action?.suggestion_evidence) ? answer?.next_best_action?.suggestion : undefined)
  return <section className="assistant-evidence-summary" aria-label="AI summary and recommendations">
    <header><div><p className="section-label">Evidence and next steps</p><h3>AI summary</h3></div><OperationStatusLabel status={answer ? answer.has_evidence ? 'completed' : 'no-evidence' : 'queued'} /></header>
    {observed && <div className="summary-observed"><h4>Observed</h4><p>{observed}</p></div>}
    {answer ? <><div className="summary-assessment"><h4>Assistant assessment</h4><Streamdown mode="static">{assessment}</Streamdown></div>{answer.uncertainty && <p className="assistant-uncertainty">{answer.uncertainty}</p>}</> : <p className="muted-note">No assistant assessment yet. Investigate this ticket to generate a summary from its evidence.</p>}
    <div className="summary-recommendations"><section><h4>Proposed solution</h4><p>{proposed || 'No evidence-backed solution has been returned yet.'}</p>{proposed && answer?.next_best_action?.dispatch_required && <p>On-site dispatch required.</p>}</section>
    <section><h4>Product recommendation</h4><p>{product || 'No product recommendation is supported by the current evidence.'}</p></section></div>
    {answer && answer.citations.length > 0 && <details><summary>Sources supporting this assessment ({answer.citations.length})</summary><ul className="citation-list">{answer.citations.map((citation, index) => <EvidenceCitation key={citation.chunk_id} citation={citation} index={index} />)}</ul></details>}
    {onInvestigate && <button type="button" className="process-button" onClick={onInvestigate}>{answer ? 'Continue investigation' : 'Open investigation'}</button>}
  </section>
}
