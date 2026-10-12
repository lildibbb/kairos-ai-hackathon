import { useEffect, useState } from 'react'
import { ArrowsClockwise, MagnifyingGlass, SignOut } from '@phosphor-icons/react'
import { Button } from '../../components/ui/button'
import { useAuth } from '../auth/AuthProvider'
import { inspectCustomerConversation, listCustomerReports, type CheckedConversation, type CheckedTurn } from '../../lib/api/customerReports'

const labels: Record<string, string> = { needs_more_information: 'In conversation', needs_live_check: 'In conversation', possible_issue: 'In conversation', self_help: 'Self-help', resolved: 'Resolved', report_created: 'Ticket recorded', sales_options: 'Sales information', action_confirmation: 'Action approval', action_completed: 'Checking improvement', action_cancelled: 'Action cancelled' }
const date = (value: string) => new Date(value).toLocaleString('en-MY', { timeZone: 'Asia/Kuala_Lumpur', dateStyle: 'medium', timeStyle: 'short' })

export function ReportCheckerPage() {
  const { session, signOut } = useAuth()
  const [rows, setRows] = useState<CheckedConversation[]>([])
  const [selected, setSelected] = useState<string>()
  const [turns, setTurns] = useState<CheckedTurn[]>([])
  const [revision, setRevision] = useState(0)
  const [busy, setBusy] = useState(true)
  const [loadingDetail, setLoadingDetail] = useState(false)
  const [error, setError] = useState('')
  const [filter, setFilter] = useState('all')
  const current = rows.find((row) => row.id === selected)
  const latest = turns[turns.length - 1]?.response

  useEffect(() => {
    if (!session) return
    const controller = new AbortController()
    setBusy(true); setError('')
    void listCustomerReports(session.accessToken, controller.signal).then((result) => {
      if (controller.signal.aborted) return
      setRows(result); setSelected((id) => result.some((row) => row.id === id) ? id : result[0]?.id)
    }).catch(() => { if (!controller.signal.aborted) setError('Reports could not be loaded. Check your session and retry.') })
      .finally(() => { if (!controller.signal.aborted) setBusy(false) })
    return () => controller.abort()
  }, [session, revision])

  useEffect(() => {
    setTurns([])
    if (!session || !selected) return
    const controller = new AbortController()
    setLoadingDetail(true)
    void inspectCustomerConversation(selected, session.accessToken, controller.signal).then((result) => {
      if (!controller.signal.aborted) setTurns(result)
    }).catch(() => { if (!controller.signal.aborted) setError('Conversation details could not be loaded.') })
      .finally(() => { if (!controller.signal.aborted) setLoadingDetail(false) })
    return () => controller.abort()
  }, [selected, session, revision])

  const filtered = rows.filter((row) => filter === 'all' || (filter === 'tickets' ? !!row.report : row.status === 'resolved'))
  return <main className="report-checker">
    <header className="checker-header"><div><p>READ ONLY</p><h1>Customer Report Checker</h1></div><div><Button variant="quiet" disabled={busy} onClick={() => setRevision((value) => value + 1)} title="Refresh reports" aria-label="Refresh reports"><ArrowsClockwise size={20} /></Button><Button variant="quiet" onClick={signOut} title="Sign out" aria-label="Sign out"><SignOut size={20} /></Button></div></header>
    <div className="checker-toolbar"><span>{rows.length} recent conversations</span><label>View <select value={filter} onChange={(event) => setFilter(event.target.value)}><option value="all">All conversations</option><option value="tickets">With trouble tickets</option><option value="resolved">Resolved</option></select></label></div>
    {error && <p className="checker-error" role="alert">{error}</p>}
    <div className="checker-layout">
      <section className="checker-list" aria-label="Customer conversations">
        {busy ? <p role="status">Loading reports...</p> : filtered.length === 0 ? <p>No conversations in this view.</p> : <table><thead><tr><th>Customer</th><th>Outcome</th><th>Report</th></tr></thead><tbody>{filtered.map((row) => <tr key={row.id} className={selected === row.id ? 'checker-selected' : ''}><td><button onClick={() => setSelected(row.id)} aria-label={`Inspect ${row.customer_ref}, ${row.id}`}><strong>{row.customer_name}</strong><span>{row.customer_ref}</span><small>{date(row.created_at)}</small></button></td><td>{labels[row.status] ?? row.status}<small>{row.turn_count} messages</small></td><td>{row.report ? <><strong>{row.report.status}</strong><small>{row.report.area ?? 'Area not configured'}</small></> : <span className="checker-muted">No ticket</span>}</td></tr>)}</tbody></table>}
      </section>
      <section className="checker-detail" aria-label="Report inspection">
        {!current ? <p><MagnifyingGlass size={20} /> Select a conversation.</p> : <>
          <h2>{current.customer_name}</h2><p className="checker-muted">{current.customer_ref} {current.is_demo ? '/ Synthetic household' : ''}</p>
          {current.report && <dl className="checker-routing"><dt>Reference</dt><dd>{current.report.reference}</dd><dt>Queue</dt><dd>{current.report.status}</dd><dt>Area</dt><dd>{current.report.area ?? 'Not configured'}</dd><dt>Technician</dt><dd>{current.report.technician ?? 'Unassigned'}</dd><dt>Reason</dt><dd>{current.report.reason.replace(/_/g, ' ')}</dd></dl>}
          {current.report?.appointment && <p>Appointment: {date(current.report.appointment.starts_at)} - {date(current.report.appointment.ends_at)}</p>}
          {latest?.assessment && <p>Assessment: {latest.assessment.category.replace(/_/g, ' ')}<br /><span className="checker-muted">{latest.assessment.evidence.join(', ')}</span></p>}
          {loadingDetail ? <p role="status">Loading conversation...</p> : <>
            {latest && <section className="checker-agent" aria-label="Agent execution"><h3>Agent Execution</h3><p>{latest.orchestration === 'agent_hosted' ? 'Model-directed tool selection' : latest.orchestration === 'agent_local' ? 'Deterministic offline runner' : latest.orchestration === 'agent_fallback' ? 'Guided fallback: model plan was unavailable or invalid' : 'Guided workflow'}</p><ol>{latest.agent_trace.map((step, index) => <li key={`${index}:${step.tool}`}><code>{step.tool}</code><span>{step.outcome}</span></li>)}</ol></section>}
            {turns.some((turn) => turn.response.router_action_details) && <section className="checker-agent" aria-label="Router action audit"><h3>Router Action Audit</h3><p className="checker-muted">Simulation only. Physical equipment and diagnostic measurements are unchanged.</p>{turns.filter((turn) => turn.response.router_action_details).map((turn) => <details key={turn.response.request_id}><summary>{turn.response.router_action?.label} / {turn.response.router_action?.status}</summary><pre>{JSON.stringify(turn.response.router_action_details, null, 2)}</pre></details>)}</section>}
            {latest && <div className="checker-diagnostics"><h3>Internal Check</h3><p className="checker-muted">Interpretation: {latest.mode} / Guidance: {latest.knowledge_status} / Reply: {latest.response_mode}</p>{latest.findings.map((finding, index) => <div key={`${finding.code}:${index}`}><strong>{finding.code.replace(/_/g, ' ')}</strong><span className="checker-evidence">{finding.evidence_status}</span><p>{finding.observation}</p><p>{finding.interpretation}</p></div>)}{latest.warnings.length > 0 && <details><summary>Data warnings ({latest.warnings.length})</summary>{latest.warnings.map((warning) => <p key={warning}>{warning}</p>)}</details>}</div>}
            <div className="checker-transcript"><h3>Conversation</h3>{turns.map((turn) => <div key={turn.response.request_id}><strong>Customer</strong><p>{turn.message}</p><strong>Assistant</strong><p>{turn.response.answer}</p>{turn.response.follow_up && <p>{turn.response.follow_up.question}</p>}</div>)}</div>
          </>}
        </>}
      </section>
    </div>
  </main>
}
