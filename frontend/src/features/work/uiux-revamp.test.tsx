import { useState } from 'react'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, expect, it, vi } from 'vitest'
import { Tabs } from '../../components/ui/tabs'
import { AssistantEvidenceSummary } from '../assistant/AssistantEvidenceSummary'

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
const summaryPayload = {
  ticket_id: 't1',
  problem: 'The router CPU usage is high at 86%. 2 of 8 wireless devices have a weak WiFi signal.',
  solution: 'Reboot the router to clear the high CPU usage. Add a mesh node or repeater to fix the weak WiFi coverage.',
  product_recommendation: 'Mesh WiFi node to extend coverage because 2 of 8 wireless devices have a weak WiFi signal.',
  actions: ['mesh', 'reboot'],
  facts: ['Recommended action: reboot the router - CPU usage or CPU temperature is high.'],
  citations: [],
  order_options: [
    { action: 'mesh', label: 'Add mesh Wi-Fi coverage', recommended: true, products: [{ code: 'MESH-AX-1', name: 'Mesh Wi-Fi 6 node (1 unit)', description: 'One node.', monthly_price_myr: 15, one_time_price_myr: null }] },
    { action: 'reboot', label: 'Remote router reboot', recommended: true, products: [{ code: 'WO-REBOOT', name: 'Remote router reboot work order', description: 'Reboot.', monthly_price_myr: null, one_time_price_myr: 0 }] },
  ],
  plan_name: 'Unifi 500Mbps', model: 'gemma', generated_at: null, cached: false,
}

function mockSummaryApi() {
  const calls: { url: string; init?: RequestInit }[] = []
  vi.stubGlobal('fetch', vi.fn(async (url: string, init?: RequestInit) => {
    calls.push({ url, init })
    if (url.endsWith('/summary')) return new Response(JSON.stringify(summaryPayload))
    if (url.endsWith('/orders') && init?.method === 'POST') {
      return new Response(JSON.stringify({ id: 'o1', ticket_id: 't1', action: 'mesh', product_code: 'MESH-AX-1', product_name: 'Mesh Wi-Fi 6 node (1 unit)', monthly_price_myr: 15, one_time_price_myr: null, notes: null, status: 'submitted', email_status: 'sent', email_recipient: 'demo@example.com', email_error: null, created_at: null }), { status: 201 })
    }
    return new Response('[]')
  }))
  return calls
}

afterEach(() => { vi.unstubAllGlobals() })

it('renders the summarize.py problem, proposed solution and product recommendation', async () => {
  mockSummaryApi()
  render(<AssistantEvidenceSummary ticketId="t1" token="tok" observed="CPE_REBOOT_LOOP reported for Root" />)
  expect(await screen.findByText(summaryPayload.solution)).toBeInTheDocument()
  expect(screen.getByText(summaryPayload.problem)).toBeInTheDocument()
  expect(screen.getByText(summaryPayload.product_recommendation)).toBeInTheDocument()
  expect(screen.queryByText(/No specific remediation/)).not.toBeInTheDocument()
  expect(screen.getByText('CPE_REBOOT_LOOP reported for Root')).toBeInTheDocument()
})

it('submits the selected order action and reports the e-mail confirmation', async () => {
  const user = userEvent.setup()
  const calls = mockSummaryApi()
  render(<AssistantEvidenceSummary ticketId="t1" token="tok" />)
  await user.click(await screen.findByRole('button', { name: /Submit order/ }))
  expect(await screen.findByText('Order submitted: Mesh Wi-Fi 6 node (1 unit)')).toBeInTheDocument()
  expect(screen.getByText(/Confirmation e-mailed to demo@example.com/)).toBeInTheDocument()
  const post = calls.find((call) => call.init?.method === 'POST')
  expect(JSON.parse(String(post?.init?.body))).toEqual({ action: 'mesh', product_code: 'MESH-AX-1', notes: null })
})
