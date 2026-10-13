import { useCallback, useEffect, useState } from 'react'
import { ArrowClockwise } from '@phosphor-icons/react'
import { Button } from '../../components/ui/button'
import { OperationStatusLabel } from '../../components/ai/status'
import { TicketsApiError } from '../../lib/api/tickets'
import { fetchTicketSummary, type TicketSummary } from '../../lib/api/ticketSummary'
import { ProductRecommendations } from './ProductRecommendations'
import { EvidenceCitation } from './EvidenceCitation'

const ACTION_CHIP: Record<string, string> = { mesh: 'Mesh', speed: 'Speed upgrade', reboot: 'Reboot' }

type SummaryProps = {
  ticketId: string
  token: string
  observed?: string
  onInvestigate?: () => void
  /** 'external' when the page renders product cards in their own full-width section. */
  ordersPlacement?: 'inline' | 'external'
  onSummary?: (summary: TicketSummary | undefined) => void
}

export function AssistantEvidenceSummary({ ticketId, token, observed, onInvestigate, ordersPlacement = 'inline', onSummary }: SummaryProps) {
  const [summary, setSummary] = useState<TicketSummary>()
  const [state, setState] = useState<'loading' | 'ready' | 'error'>('loading')
  const [error, setError] = useState('')

  const load = useCallback(async (refresh = false, signal?: AbortSignal) => {
    setState('loading')
    setError('')
    try {
      const loaded = await fetchTicketSummary(ticketId, token, { refresh, signal })
      setSummary(loaded)
      onSummary?.(loaded)
      setState('ready')
    } catch (caught) {
      if (caught instanceof DOMException && caught.name === 'AbortError') return
      setError(caught instanceof TicketsApiError ? caught.message : 'The AI summary could not be generated.')
      setState('error')
    }
  // onSummary is a page callback; reloading on its identity would refetch every render.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ticketId, token])

  useEffect(() => {
    const controller = new AbortController()
    void load(false, controller.signal)
    return () => controller.abort()
  }, [load])

  return <section className="assistant-evidence-summary" aria-label="AI summary and recommendations" aria-busy={state === 'loading'}>
    <header>
      <div><p className="section-label">Next best action</p><h3>AI summary</h3></div>
      <div className="summary-header-actions">
        <OperationStatusLabel status={state === 'loading' ? 'searching' : state === 'error' ? 'failed' : 'completed'} />
        <button type="button" className="summary-refresh" onClick={() => void load(true)} disabled={state === 'loading'} aria-label="Regenerate AI summary" title="Regenerate">
          <ArrowClockwise size={15} aria-hidden="true" className={state === 'loading' ? 'is-spinning' : undefined} />
        </button>
      </div>
    </header>
    {observed && <div className="summary-observed"><h4>Observed</h4><p>{observed}</p></div>}

    {state === 'loading' && !summary && <div className="summary-loading" role="status">
      <span className="summary-loading__bar" /><span className="summary-loading__bar" /><span className="summary-loading__bar" />
      <p>Reading device and router health, searching the knowledge base…</p>
    </div>}
    {state === 'error' && <div><p className="form-error" role="alert">{error}</p><Button type="button" className="process-button" onClick={() => void load()}>Retry summary</Button></div>}

    {summary && <div className={state === 'loading' ? 'summary-body is-refreshing' : 'summary-body'}>
      <div className="summary-assessment"><h4>Assessment</h4><p>{summary.problem}</p></div>
      <div className="summary-recommendations">
        <section>
          <h4>Proposed solution</h4>
          <p>{summary.solution || 'No action is needed based on the device and router health.'}</p>
          {summary.actions.length > 0 && <ul className="summary-action-chips" aria-label="Recommended order actions">
            {summary.actions.map((action) => <li key={action} className={`summary-chip summary-chip--${action}`}>{ACTION_CHIP[action] ?? action}</li>)}
          </ul>}
        </section>
        <section>
          <h4>Product recommendation</h4>
          {ordersPlacement === 'external' || summary.order_options.length === 0
            ? <p>{summary.product_recommendation || 'No product is recommended for this ticket.'}{summary.order_options.length > 0 && <> <a className="inline-link" href="#product-recommendation">See product options</a></>}</p>
            : <ProductRecommendations key={`${summary.ticket_id}:${summary.actions.join(',')}`} ticketId={ticketId} token={token} summary={summary} layout="inline" />}
        </section>
      </div>
      {summary.facts.length > 0 && <details className="summary-facts"><summary>Device and router health ({summary.facts.length} facts)</summary><ul>{summary.facts.map((fact) => <li key={fact} className={fact.startsWith('Recommended action') ? 'is-flag' : undefined}>{fact}</li>)}</ul></details>}
      {summary.citations.length > 0 && <details><summary>Knowledge sources ({summary.citations.length})</summary><ul className="citation-list">{summary.citations.map((citation, index) => <EvidenceCitation key={citation.chunk_id} citation={citation} index={index} />)}</ul></details>}
      <p className="summary-meta">{summary.cached ? 'Saved summary' : 'Generated now'}{summary.model ? ` · ${summary.model}` : ''}{summary.plan_name ? ` · Plan: ${summary.plan_name}` : ''}</p>
    </div>}
    {onInvestigate && <button type="button" className="process-button" onClick={onInvestigate}>Investigate with the agent</button>}
  </section>
}
