// Fictional accounts only; credentials remain in memory, never in output or screenshots.
const assert = require('node:assert/strict')
const { execFileSync } = require('node:child_process')
const { mkdirSync } = require('node:fs')
const path = require('node:path')
const { chromium } = require(process.argv[2] || 'playwright')

const repo = path.resolve(__dirname, '../..')
const output = path.resolve(__dirname, '../.local')
const url = process.argv[3] || 'http://127.0.0.1:5173'
const python = [
  'import json', 'from sqlalchemy import select', 'from app.db.session import SessionLocal',
  'from app.domain.models import User, Role, CustomerAccount, Customer',
  'from app.auth.tokens import create_access_token', 'session=SessionLocal()',
  "user=session.scalar(select(User).join(Role).join(CustomerAccount, CustomerAccount.user_id==User.id).join(Customer, Customer.id==CustomerAccount.customer_id).where(User.email=='customer@demo.invalid', User.is_demo.is_(True), User.is_active.is_(True), Role.name=='customer', Customer.is_demo.is_(True)))",
  "operator=session.scalar(select(User).join(Role).where(User.email=='operator@demo.invalid', User.is_demo.is_(True), User.is_active.is_(True), Role.name=='operator'))",
  "assert user is not None and operator is not None, 'Existing fictional customer/operator accounts are required'",
  "token, expiry=create_access_token(user.id, 'customer')", "admin_token, admin_expiry=create_access_token(operator.id, 'operator')",
  "print(json.dumps({'customer':{'accessToken':token,'expiresAt':expiry.timestamp()*1000,'userId':user.id,'role':'customer'},'operator':{'accessToken':admin_token,'expiresAt':admin_expiry.timestamp()*1000,'userId':operator.id,'role':'operator'}}))",
  'session.close()',
].join('; ')

async function main() {
  mkdirSync(output, { recursive: true })
  const auth = JSON.parse(execFileSync('docker', ['compose', 'exec', '-T', 'api', 'python', '-c', python], { cwd: repo, encoding: 'utf8' }))
  const browser = await chromium.launch({ headless: true, channel: process.argv[4] || undefined })
  const pending = new Map()
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 } })
  try {
    await context.addInitScript((session) => window.sessionStorage.setItem('field-force-auth-session', JSON.stringify(session)), auth.customer)
    const page = await context.newPage()
    page.setDefaultTimeout(90000)
    const errors = []
    page.on('pageerror', (error) => errors.push(error.message))
    await page.goto(`${url}/portal`)
    await page.getByRole('heading', { name: 'Hi, how can we help?' }).waitFor()
    let latest
    let lastPayload
    async function receive(trigger) {
      const response = page.waitForResponse((r) => r.url().endsWith('/portal/me/chat/messages') && r.request().method() === 'POST')
      await trigger()
      const r = await response
      assert.equal(r.status(), 200, `Chat request failed: ${await r.text()}`)
      latest = await r.json()
      lastPayload = r.request().postDataJSON()
      for (const field of ['findings', 'agent_trace', 'router_action_details', 'workflow']) assert(!(field in latest), `${field} leaked`)
      if (latest.router_action?.status === 'pending') pending.set(latest.router_action.id, latest.conversation_id)
      else if (latest.router_action) pending.delete(latest.router_action.id)
      await page.getByText(latest.answer, { exact: true }).last().waitFor()
      return latest
    }
    const say = (message) => receive(async () => {
      await page.getByLabel('Your message').fill(message)
      await page.getByRole('button', { name: 'Send message' }).click()
    })
    const click = (label) => receive(() => page.getByRole('button', { name: label, exact: true }).click())
    const inspect = async (conversationId) => {
      const r = await context.request.get(`${url}/admin/customer-reports/${conversationId}`, { headers: { Authorization: `Bearer ${auth.operator.accessToken}` } })
      assert.equal(r.status(), 200)
      return r.json()
    }
    await say('Please restart my router')
    assert.equal(latest.status, 'action_confirmation')
    await page.getByRole('button', { name: 'Confirm action', exact: true }).waitFor()
    await page.screenshot({ path: path.join(output, 'customer-agent-reboot-confirmation.png'), fullPage: true })
    await click('Cancel action')
    assert.equal(latest.status, 'action_cancelled')
    await page.getByRole('button', { name: 'New conversation', exact: true }).click()

    await say('Please restart my router')
    assert.equal(latest.status, 'action_confirmation')
    await click('Confirm action')
    assert.equal(latest.status, 'action_completed')
    assert.equal(latest.router_action.status, 'succeeded')
    assert.equal(lastPayload.action_id, latest.router_action.id)
    const conversationId = latest.conversation_id
    const reboot = await inspect(conversationId)
    const done = reboot.turns.at(-1).response
    assert.equal(done.router_action_details.after.reboot_count, done.router_action_details.before.reboot_count + 1)
    const replay = await context.request.post(`${url}/portal/me/chat/messages`, {
      headers: { Authorization: `Bearer ${auth.customer.accessToken}` }, data: lastPayload,
    })
    assert.equal(replay.status(), 200)
    const repeated = await inspect(conversationId)
    assert.equal(repeated.turns.at(-1).response.router_action_details.after.reboot_count, done.router_action_details.after.reboot_count)
    await page.reload()
    await page.getByRole('button', { name: "It's working now", exact: true }).waitFor()
    for (const [width, height] of [[1440, 900], [1280, 800]]) {
      await page.setViewportSize({ width, height })
      const layout = await page.evaluate(() => ({ width: document.documentElement.scrollWidth, viewport: innerWidth,
        composer: document.querySelector('.portal-composer').getBoundingClientRect().bottom, height: innerHeight }))
      assert(layout.width <= layout.viewport + 1 && layout.composer <= layout.height + 1, 'Action controls overflow the desktop layout')
      await page.screenshot({ path: path.join(output, `customer-agent-reboot-${width}.png`), fullPage: true })
    }
    await click("It's working now")
    assert.equal(latest.status, 'resolved')
    await page.getByRole('button', { name: 'New conversation', exact: true }).click()

    await say('Please reconfigure my IPTV VLAN')
    assert.equal(latest.router_action.kind, 'restore_vlan')
    await click('Confirm action')
    assert.equal(latest.status, 'action_completed')
    const vlanId = latest.conversation_id
    const vlan = await inspect(vlanId)
    const vlanResult = vlan.turns.at(-1).response
    assert.equal(vlanResult.router_action_details.before.service_vlans.IPTV, 601, 'Stage the fictional VLAN mismatch before running this showcase test')
    assert.equal(vlanResult.router_action_details.after.service_vlans.IPTV, 600)
    await page.screenshot({ path: path.join(output, 'customer-agent-vlan-completed.png'), fullPage: true })
    await click('Still not working')
    assert.equal(latest.follow_up.id, 'submit_report')
    await click('Arrange technician review')
    assert.equal(latest.status, 'report_created')
    const denied = await context.request.get(`${url}/admin/customer-reports/${vlanId}`, { headers: { Authorization: `Bearer ${auth.customer.accessToken}` } })
    assert.equal(denied.status(), 403)

    const adminContext = await browser.newContext({ viewport: { width: 1440, height: 900 } })
    await adminContext.addInitScript((session) => window.sessionStorage.setItem('field-force-auth-session', JSON.stringify(session)), auth.operator)
    const admin = await adminContext.newPage()
    await admin.goto(`${url}/admin/check`)
    await admin.getByRole('button', { name: `Inspect SYN-00042-0002, ${vlanId}`, exact: true }).click()
    await admin.getByRole('heading', { name: 'Router Action Audit' }).waitFor()
    await admin.locator('.checker-agent details').last().locator('summary').click()
    await admin.screenshot({ path: path.join(output, 'customer-agent-checker-audit.png'), fullPage: true })
    assert.equal(errors.length, 0, errors.join('\n'))
    const all = [...reboot.turns, ...vlan.turns]
    const modes = [...new Set(all.map((turn) => turn.response.orchestration))]
    assert(modes.includes('agent_hosted'), 'Hosted model did not complete any validated agent plan')
    console.log(JSON.stringify({ result: 'passed', plannerModes: modes, rebootReplay: 'once',
      vlanBefore: vlanResult.router_action_details.before.service_vlans.IPTV,
      vlanAfter: vlanResult.router_action_details.after.service_vlans.IPTV,
      screenshots: output, desktopViewports: ['1440x900', '1280x800'] }))
    await adminContext.close()
  } finally {
    for (const [actionId, conversationId] of pending) {
      await context.request.post(`${url}/portal/me/chat/messages`, { headers: { Authorization: `Bearer ${auth.customer.accessToken}` },
        data: { message: 'Cancel action', answer_choice: 'cancel_router_action', action_id: actionId, conversation_id: conversationId, request_id: crypto.randomUUID() },
      }).catch(() => {})
    }
    await browser.close()
  }
}
main().catch((error) => { console.error(error.message); process.exitCode = 1 })
