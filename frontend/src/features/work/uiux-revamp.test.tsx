import { useState } from 'react'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { expect, it } from 'vitest'
import { Tabs } from '../../components/ui/tabs'
import { AssistantEvidenceSummary } from '../assistant/AssistantEvidenceSummary'
import type { AssistantAnswer } from '../../lib/api/assistant'

function SessionTabs() {
  const [tab, setTab] = useState('overview')
  return <Tabs label="Workspace" value={tab} onValueChange={setTab} tabs={[{ id: 'overview', label: 'Overview', content: <p>Topology</p> }, { id: 'chat', label: 'Investigation', content: <input aria-label="Draft" /> }]} />
}
it('supports arrow/Home/End navigation and preserves hidden chat drafts', async () => {
  const user = userEvent.setup()
  render(<SessionTabs />)
  screen.getByRole('tab', { name: 'Overview' }).focus()
  await user.keyboard('{ArrowRight}')
  expect(screen.getByRole('tab', { name: 'Investigation' })).toHaveFocus()
  await user.type(screen.getByRole('textbox', { name: 'Draft' }), 'Pending investigation')
  await user.click(screen.getByRole('tab', { name: 'Overview' }))
  expect(screen.queryByRole('textbox')).not.toBeInTheDocument()
  await user.keyboard('{End}')
  expect(screen.getByRole('textbox')).toHaveValue('Pending investigation')
  await user.keyboard('{Home}')
  expect(screen.getByRole('tab', { name: 'Overview' })).toHaveAttribute('aria-selected', 'true')
})
it('withholds recommendations without matching citation references', () => {
  const answer: AssistantAnswer = { session_id: 's', answer: 'Check service.', uncertainty: '', has_evidence: true, citations: [], next_best_action: { remediation: 'Reset', suggestion: 'Buy equipment', evidence: ['missing'], suggestion_evidence: ['missing'], dispatch_required: false } }
  render(<AssistantEvidenceSummary answer={answer} observed="Service down" />)
  expect(screen.queryByText('Buy equipment')).not.toBeInTheDocument()
  expect(screen.getByText('No product recommendation is supported by the current evidence.')).toBeInTheDocument()
})
it('shows a returned recommendation when its evidence matches an actual source', () => {
  const answer: AssistantAnswer = { session_id: 's', answer: 'Check service.', uncertainty: '', has_evidence: true, citations: [{ chunk_id: 'c', document_id: 'd', document_title: 'Service guide', section: 'Equipment', source_type: 'procedure', content: 'Recorded recommendation', score: 1 }], next_best_action: { remediation: 'Check cable', suggestion: 'Consider a mesh access point', evidence: ['c'], suggestion_evidence: ['c'], dispatch_required: false } }
  render(<AssistantEvidenceSummary answer={answer} />)
  expect(screen.getByText('Consider a mesh access point')).toBeInTheDocument()
  expect(screen.getByText('Check cable')).toBeInTheDocument()
})
it('renders the summarize.py problem, solution and product recommendation when present', () => {
  const answer: AssistantAnswer = {
    session_id: 's', answer: 'raw assessment', uncertainty: '', has_evidence: true,
    citations: [{ chunk_id: 'c', document_id: 'd', document_title: 'Service guide', section: 'Equipment', source_type: 'procedure', content: 'Recorded recommendation', score: 1 }],
    next_best_action: null,
    summary: { problem: 'Two devices have weak signal.', solution: 'Add a mesh node.', product_recommendation: 'Add a mesh node.', actions: ['mesh'] },
  }
  render(<AssistantEvidenceSummary answer={answer} observed="Service down" />)
  expect(screen.getByText('Two devices have weak signal.')).toBeInTheDocument()
  expect(screen.getAllByText('Add a mesh node.').length).toBeGreaterThan(0)
  expect(screen.getByText('Service down')).toBeInTheDocument()
})
