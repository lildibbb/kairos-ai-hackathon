// Existing fictional accounts only; authentication stays in memory.
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
  'from app.auth.tokens import create_access_token', 's=SessionLocal()',
  "user=s.scalar(select(User).join(Role).join(CustomerAccount, CustomerAccount.user_id==User.id).join(Customer, Customer.id==CustomerAccount.customer_id).where(User.email=='customer@demo.invalid', User.is_demo.is_(True), User.is_active.is_(True), Role.name=='customer', Customer.is_demo.is_(True)))",
  "admin=s.scalar(select(User).join(Role).where(User.email=='operator@demo.invalid', User.is_demo.is_(True), Role.name=='operator'))",
  'assert user is not None and admin is not None',
  "token, expiry=create_access_token(user.id, 'customer')", "admin_token, _=create_access_token(admin.id, 'operator')",
  "print(json.dumps({'session':{'accessToken':token,'expiresAt':expiry.timestamp()*1000,'userId':user.id,'role':'customer'},'adminToken':admin_token}))", 's.close()',
].join('; ')

async function main() {
  mkdirSync(output, { recursive: true })
  const auth = JSON.parse(execFileSync('docker', ['compose', 'exec', '-T', 'api', 'python', '-c', python], { cwd: repo, encoding: 'utf8' }))
  const browser = await chromium.launch({ headless: true, channel: process.argv[4] || undefined })
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 } })
  const pending = new Map()
  try {
    await context.addInitScript((session) => window.sessionStorage.setItem('field-force-auth-session', JSON.stringify(session)), auth.session)
    const page = await context.newPage()
    page.setDefaultTimeout(120000)
    const errors = []
    page.on('pageerror', (error) => errors.push(error.message))
    await page.goto(`${url}/portal`)
    await page.getByRole('heading', { name: 'Hi, how can we help?' }).waitFor()
    let latest
    let payload
    async function receive(trigger) {
      const response = page.waitForResponse((r) => r.url().endsWith('/portal/me/chat/messages') && r.request().method() === 'POST')
      await trigger()
      const r = await response
      assert.equal(r.status(), 200)
      latest = await r.json()
      if (latest.router_action?.status === 'pending') pending.set(latest.router_action.id, latest.conversation_id)
      else if (latest.router_action) pending.delete(latest.router_action.id)
      payload = r.request().postDataJSON()
      for (const field of ['findings', 'response_mode', 'response_prefix', 'agent_trace', 'workflow']) assert(!(field in latest))
      await page.getByText(latest.answer, { exact: true }).last().waitFor()
      return latest
    }
    const say = (text) => receive(async () => {
      await page.getByLabel('Your message').fill(text)
      await page.getByRole('button', { name: 'Send message' }).click()
    })
    const inspect = async () => {
      const r = await context.request.get(`${url}/admin/customer-reports/${latest.conversation_id}`, { headers: { Authorization: `Bearer ${auth.adminToken}` } })
      assert.equal(r.status(), 200)
      return (await r.json()).turns.at(-1).response
    }
    await say('My internet is slow on every device using Ethernet. What could be wrong?')
    assert.equal(latest.follow_up.id, 'self_help')
    const firstAnswer = latest.answer
    await say("I don't think it is working after changing device, what do you think is the issue?")
    assert.equal(latest.follow_up.id, 'submit_report')
    assert.equal(latest.report, null)
    assert.notEqual(latest.answer, firstAnswer)
    assert(!/compare another device/i.test(latest.answer))
    const failed = await inspect()
    assert.equal(failed.workflow.self_help, 'failed')
    assert(failed.workflow.checks_tried.includes('another_device'))
    assert.equal(failed.response_mode, 'hosted', 'Hosted response writer did not produce a validated reply')
    const answer = latest.answer
    const replay = await context.request.post(`${url}/portal/me/chat/messages`, { headers: { Authorization: `Bearer ${auth.session.accessToken}` }, data: payload })
    assert.equal(replay.status(), 200)
    assert.equal((await replay.json()).answer, answer)
    await page.reload()
    await page.getByText(answer, { exact: true }).waitFor()
    for (const [width, height] of [[1440, 900], [1280, 800]]) {
      await page.setViewportSize({ width, height })
      const layout = await page.evaluate(() => ({ width: document.documentElement.scrollWidth, viewport: innerWidth,
        composer: document.querySelector('.portal-composer').getBoundingClientRect().bottom, height: innerHeight }))
      assert(layout.width <= layout.viewport + 1 && layout.composer <= layout.height + 1)
      await page.screenshot({ path: path.join(output, `customer-response-persistent-${width}.png`), fullPage: true })
    }
    await page.getByRole('button', { name: 'New conversation', exact: true }).click()
    await say('My Wi-Fi is slow on every device, especially in the bedroom.')
    assert.equal(latest.follow_up.id, 'near_router')
    await receive(() => page.getByRole('button', { name: 'It improves', exact: true }).click())
    const coverage = await inspect()
    assert.equal(coverage.assessment.category, 'coverage')
    assert.equal(coverage.response_mode, 'hosted')
    const coverageAnswer = latest.answer
    assert(/coverage|signal|router/i.test(coverageAnswer))
    await page.reload()
    await page.getByText(coverageAnswer, { exact: true }).waitFor()
    await page.screenshot({ path: path.join(output, 'customer-response-coverage.png'), fullPage: true })
    await page.getByRole('button', { name: 'New conversation', exact: true }).click()
    await say('Internet saya lambat sangat. Boleh bantu saya semak?')
    const malay = await inspect()
    assert.equal(malay.response_mode, 'hosted')
    assert(/saya|anda|boleh|sambungan|peranti/i.test(latest.answer))
    await page.screenshot({ path: path.join(output, 'customer-response-malay.png'), fullPage: true })
    assert.equal(errors.length, 0, errors.join('\n'))
    console.log(JSON.stringify({ result: 'passed', replyModes: [failed.response_mode, coverage.response_mode, malay.response_mode],
      persistentIssueReply: answer, coverageReply: coverageAnswer, malayReply: latest.answer,
      replayAndHistory: 'preserved', desktopViewports: ['1440x900', '1280x800'], screenshots: output }))
  } finally {
    for (const [actionId, conversationId] of pending) {
      await context.request.post(`${url}/portal/me/chat/messages`, { headers: { Authorization: `Bearer ${auth.session.accessToken}` },
        data: { message: 'Cancel action', conversation_id: conversationId, request_id: require('node:crypto').randomUUID(),
          answer_choice: 'cancel_router_action', action_id: actionId } }).catch(() => {})
    }
    await context.close()
    await browser.close()
  }
}

main().catch((error) => { console.error(error.message); process.exitCode = 1 })
