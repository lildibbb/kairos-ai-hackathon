// Run against the local demo only; no passwords or tokens are written to disk.
const assert = require('node:assert/strict')
const { execFileSync } = require('node:child_process')
const { mkdirSync } = require('node:fs')
const path = require('node:path')
const { chromium } = require(process.argv[2] || 'playwright')

const repo = path.resolve(__dirname, '../..')
const output = path.resolve(__dirname, '../.local')
const url = process.argv[3] || 'http://127.0.0.1:5173'
const python = [
  'import json',
  'from sqlalchemy import select',
  'from app.db.session import SessionLocal',
  'from app.domain.models import User, Role, CustomerAccount, Customer',
  'from app.auth.tokens import create_access_token',
  'session=SessionLocal()',
  "user=session.scalar(select(User).join(Role).join(CustomerAccount, CustomerAccount.user_id==User.id).join(Customer, Customer.id==CustomerAccount.customer_id).where(User.email=='customer@demo.invalid', User.is_demo.is_(True), User.is_active.is_(True), Role.name=='customer', Customer.is_demo.is_(True)))",
  "assert user is not None, 'An existing fictional demo customer login is required'",
  "operator=session.scalar(select(User).join(Role).where(User.email=='operator@demo.invalid', User.is_demo.is_(True), User.is_active.is_(True), Role.name=='operator'))",
  "assert operator is not None, 'An existing fictional demo operator login is required'",
  "token, expiry=create_access_token(user.id, 'customer')",
  "admin_token, admin_expiry=create_access_token(operator.id, 'operator')",
  "print(json.dumps({'customer':{'accessToken':token, 'expiresAt':expiry.timestamp()*1000, 'userId':user.id, 'role':'customer'}, 'operator':{'accessToken':admin_token, 'expiresAt':admin_expiry.timestamp()*1000, 'userId':operator.id, 'role':'operator'}}))",
  'session.close()',
].join('; ')

function assertCustomerCopy(answer) {
  assert(!/demo|prototype/i.test(answer.answer), 'Customer answer contains development wording')
  assert(!('is_demo' in answer), 'Internal data marker leaked to customer')
  assert(!('assessment' in answer), 'Internal assessment leaked to customer')
  if (answer.report) {
    assert(answer.report.reference.startsWith('TT-'), 'Customer ticket reference contains an internal prefix')
    assert(!('is_demo' in answer.report), 'Internal ticket marker leaked to customer')
  }
}

async function main() {
  mkdirSync(output, { recursive: true })
  const auth = JSON.parse(execFileSync('docker', ['compose', 'exec', '-T', 'api', 'python', '-c', python], { cwd: repo, encoding: 'utf8' }))
  const browser = await chromium.launch({ headless: true, channel: process.argv[4] || undefined })
  let cleanupBooking
  let bookingChecked = false
  try {
    const loginPage = await browser.newPage({ viewport: { width: 1440, height: 900 } })
    await loginPage.goto(`${url}/portal/sign-in`)
    await loginPage.getByRole('heading', { name: 'Welcome Back' }).waitFor()
    assert(!/demo|prototype/i.test(await loginPage.locator('body').innerText()))
    await loginPage.screenshot({ path: path.join(output, 'customer-sign-in-desktop.png'), fullPage: true })
    await loginPage.goto(`${url}/admin/sign-in`)
    await loginPage.getByRole('heading', { name: 'Report Checker' }).waitFor()
    assert(!/demo|prototype/i.test(await loginPage.locator('body').innerText()))
    await loginPage.screenshot({ path: path.join(output, 'checker-sign-in-desktop.png'), fullPage: true })
    await loginPage.close()
    const context = await browser.newContext({ viewport: { width: 1440, height: 900 } })
    await context.addInitScript((session) => { window.sessionStorage.setItem('field-force-auth-session', JSON.stringify(session)) }, auth.customer)
    const page = await context.newPage()
    const failures = []
    page.on('pageerror', (error) => failures.push(error.message))
    await page.goto(`${url}/portal`)
    await page.getByRole('heading', { name: 'Connection Support' }).waitFor()
    await page.getByRole('heading', { name: 'Hi, how can we help?' }).waitFor()
    assert(!/demo|prototype/i.test(await page.locator('body').innerText()))
    await page.screenshot({ path: path.join(output, 'customer-welcome-desktop.png'), fullPage: true })
    const logoLoaded = await page.locator('.portal-brand img').evaluate((img) => img.complete && img.naturalWidth > 0)
    assert(logoLoaded, 'Official logo asset failed to render')
    await page.getByLabel('Your message').fill('My internet is slow, I want to make a report.')
    const firstResponse = page.waitForResponse((response) => response.url().endsWith('/portal/me/chat/messages') && response.request().method() === 'POST')
    await page.getByRole('button', { name: 'Send message' }).click()
    const first = await (await firstResponse).json()
    assertCustomerCopy(first)
    assert.equal(first.status, 'needs_live_check')
    assert.equal(first.report, null)
    for (const field of ['findings', 'reported', 'warnings', 'mode', 'workflow']) assert(!(field in first), `Internal field leaked: ${field}`)
    assert.equal(first.follow_up.id, 'device_scope')
    let result = first
    for (const [label, nextQuestion] of [['Every device', 'connection'], ['Wi-Fi', 'near_router']]) {
      const response = page.waitForResponse((r) => r.url().endsWith('/portal/me/chat/messages') && r.request().method() === 'POST')
      await page.getByRole('button', { name: label, exact: true }).click()
      result = await (await response).json()
      assertCustomerCopy(result)
      assert.equal(result.conversation_id, first.conversation_id)
      assert.equal(result.follow_up.id, nextQuestion)
    }
    await page.getByRole('button', { name: 'It improves', exact: true }).waitFor()
    await page.screenshot({ path: path.join(output, 'customer-chat-desktop.png'), fullPage: true })
    await page.reload()
    await page.getByRole('button', { name: 'It improves', exact: true }).waitFor()
    assert.equal(await page.locator('.portal-user').count(), 3)
    const reply = async (label) => {
      const response = page.waitForResponse((r) => r.url().endsWith('/portal/me/chat/messages') && r.request().method() === 'POST')
      await page.getByRole('button', { name: label, exact: true }).click()
      const body = await (await response).json()
      assertCustomerCopy(body)
      await page.getByText(body.answer, { exact: true }).last().waitFor()
      return body
    }
    result = await reply('It improves')
    assert(result.answer.includes('mesh') && result.answer.includes('may help'))
    assert.equal(result.status, 'self_help')
    await page.screenshot({ path: path.join(output, 'customer-self-help-desktop.png'), fullPage: true })
    result = await reply('Learn about mesh')
    assert.equal(result.status, 'sales_options')
    assert(result.sales_options.length > 0)
    assert(result.sales_options.every((offer) => offer.monthly_price_myr === null && new URL(offer.official_url).hostname === 'unifi.com.my'))
    await page.getByRole('link', { name: 'View on Unifi' }).first().waitFor()
    await page.screenshot({ path: path.join(output, 'customer-mesh-options-desktop.png'), fullPage: true })
    result = await reply('Keep troubleshooting')
    assert.equal(result.status, 'self_help')
    result = await reply("It's working now")
    assert.equal(result.status, 'resolved')
    assert.equal(result.report, null)
    await page.getByRole('button', { name: 'New conversation', exact: true }).click()
    let singleDevice = await reply('Slow internet')
    singleDevice = await reply('Only one device')
    singleDevice = await reply('Wi-Fi')
    singleDevice = await reply('It improves')
    assert.equal(singleDevice.status, 'self_help')
    assert(singleDevice.answer.includes('weak Wi-Fi coverage at the original location'))
    assert(singleDevice.answer.includes('Compare another device in the same spot'))
    assert(!singleDevice.answer.includes('This may be specific to that device'))
    await page.getByRole('button', { name: 'Learn about mesh', exact: true }).waitFor()
    await page.reload()
    await page.getByText(singleDevice.answer, { exact: true }).waitFor()
    await page.screenshot({ path: path.join(output, 'customer-single-device-coverage-desktop.png'), fullPage: true })
    await page.getByRole('button', { name: 'New conversation', exact: true }).click()
    let ticketResult = await reply('No connection')
    ticketResult = await reply('Every device')
    ticketResult = await reply('Ethernet cable')
    assert.equal(ticketResult.follow_up.id, 'router_lights')
    ticketResult = await reply('LOS is red or blinking')
    assert.equal(ticketResult.status, 'report_created')
    assert.equal(ticketResult.report.status, 'assigned')
    assert.equal(ticketResult.follow_up, null)
    assert(ticketResult.answer.includes('possible fibre connection issue'))
    assert(ticketResult.answer.includes('on-site technician check'))
    assert(ticketResult.answer.includes('Your trouble ticket has been created'))
    assert(ticketResult.report.ticket_id)
    assert(!/demo|prototype/i.test(await page.locator('body').innerText()))
    await page.reload()
    await page.getByText(ticketResult.answer, { exact: true }).waitFor()
    assert(!/demo|prototype/i.test(await page.locator('body').innerText()))
    await page.screenshot({ path: path.join(output, 'customer-ticket-desktop.png'), fullPage: true })
    const appointmentPath = `/portal/me/reports/${ticketResult.report.ticket_id}`
    const appointmentHeaders = { Authorization: `Bearer ${auth.customer.accessToken}` }
    const initialAvailability = await context.request.get(`${url}${appointmentPath}/appointment-slots`, { headers: appointmentHeaders })
    assert(initialAvailability.ok())
    const before = await initialAvailability.json()
    // Never cancel or reschedule an appointment that existed before this test.
    if (!before.appointment) {
      assert(before.slots.length > 1, 'Seed future support visit windows before running the booking smoke test')
      const picker = page.getByRole('region', { name: 'Technician appointment', exact: true })
      const bookingResponse = page.waitForResponse((r) => r.url().endsWith(`${appointmentPath}/appointments`) && r.request().method() === 'POST')
      await picker.getByRole('button', { name: 'Confirm appointment', exact: true }).click()
      const bookedResponse = await bookingResponse
      assert(bookedResponse.ok())
      const booked = await bookedResponse.json()
      cleanupBooking = { path: appointmentPath, id: booked.id }
      assert.equal(booked.status, 'confirmed')
      await picker.getByText('Confirmed', { exact: true }).waitFor()
      await page.reload()
      await page.getByText(/Your appointment is confirmed for/).waitFor()
      await picker.getByText('Confirmed', { exact: true }).waitFor()
      const rescheduleResponse = page.waitForResponse((r) => r.url().endsWith(`${appointmentPath}/appointments`) && r.request().method() === 'POST')
      await picker.getByRole('button', { name: 'Reschedule appointment', exact: true }).click()
      const changedResponse = await rescheduleResponse
      assert(changedResponse.ok())
      const changed = await changedResponse.json()
      assert.notEqual(changed.id, booked.id)
      assert.notEqual(changed.slot_id, booked.slot_id)
      cleanupBooking = { path: appointmentPath, id: changed.id }
      const malaysiaTime = (value) => new Date(value).toLocaleTimeString('en-GB', { timeZone: 'Asia/Kuala_Lumpur', hour: '2-digit', minute: '2-digit' })
      const changedTime = `${malaysiaTime(changed.starts_at)} to ${malaysiaTime(changed.ends_at)}`
      await page.waitForFunction((expected) => {
        const replies = document.querySelectorAll('.portal-assistant')
        return replies[replies.length - 1]?.textContent.includes(expected)
      }, changedTime)
      const reportCheck = await context.request.get(`${url}/admin/customer-reports`, { headers: { Authorization: `Bearer ${auth.operator.accessToken}` } })
      assert(reportCheck.ok())
      const checked = (await reportCheck.json()).find((row) => row.id === ticketResult.conversation_id)
      assert.equal(checked.report.appointment.id, changed.id, 'Checker must use the committed booking')
      await page.screenshot({ path: path.join(output, 'customer-appointment-desktop.png'), fullPage: true })
      const bookedCheckerContext = await browser.newContext({ viewport: { width: 1440, height: 900 } })
      await bookedCheckerContext.addInitScript((session) => { window.sessionStorage.setItem('field-force-auth-session', JSON.stringify(session)) }, auth.operator)
      const bookedChecker = await bookedCheckerContext.newPage()
      bookedChecker.on('pageerror', (error) => failures.push(error.message))
      await bookedChecker.goto(`${url}/admin/check`)
      await bookedChecker.getByRole('button', { name: `Inspect SYN-00042-0002, ${ticketResult.conversation_id}`, exact: true }).click()
      await bookedChecker.locator('.checker-detail').getByText(/^Appointment:/).waitFor()
      await bookedChecker.screenshot({ path: path.join(output, 'checker-confirmed-appointment-desktop.png'), fullPage: true })
      await bookedCheckerContext.close()
      page.once('dialog', (dialog) => dialog.accept())
      const cancelResponse = page.waitForResponse((r) => r.url().endsWith(`${appointmentPath}/appointments/${changed.id}`) && r.request().method() === 'DELETE')
      await picker.getByRole('button', { name: 'Cancel appointment', exact: true }).click()
      assert.equal((await (await cancelResponse).json()).status, 'cancelled')
      cleanupBooking = undefined
      await picker.getByText('Your appointment was cancelled. Your trouble ticket remains open.', { exact: true }).waitFor()
      await page.reload()
      await page.getByText(ticketResult.answer, { exact: true }).waitFor()
      const released = await context.request.get(`${url}${appointmentPath}/appointment-slots`, { headers: appointmentHeaders })
      const releasedBody = await released.json()
      assert.equal(releasedBody.appointment, null)
      assert(releasedBody.slots.some((slot) => slot.slot_id === changed.slot_id))
      bookingChecked = true
    }
    for (const [width, height] of [[1440, 900], [1280, 800]]) {
      await page.setViewportSize({ width, height })
      const dimensions = await page.evaluate(() => ({ width: window.innerWidth, scroll: document.documentElement.scrollWidth }))
      assert(dimensions.scroll <= dimensions.width + 1, `Horizontal overflow at ${width}px`)
      const box = await page.getByLabel('Your message').boundingBox()
      assert(box && box.y + box.height <= height, `Composer outside viewport at ${width}px`)
      await page.waitForFunction(() => {
        const log = document.querySelector('.portal-messages')
        return log && Math.abs(log.scrollHeight - log.clientHeight - log.scrollTop) < 2
      })
      await page.screenshot({ path: path.join(output, `customer-chat-desktop-${width}.png`), fullPage: true })
    }
    const denied = await page.evaluate(async (token) => (await fetch('/admin/customer-reports', { headers: { Authorization: `Bearer ${token}` } })).status, auth.customer.accessToken)
    assert.equal(denied, 403)
    const adminContext = await browser.newContext({ viewport: { width: 1440, height: 900 } })
    await adminContext.addInitScript((session) => { window.sessionStorage.setItem('field-force-auth-session', JSON.stringify(session)) }, auth.operator)
    const admin = await adminContext.newPage()
    admin.on('pageerror', (error) => failures.push(error.message))
    await admin.goto(`${url}/admin/check`)
    await admin.getByRole('heading', { name: 'Customer Report Checker' }).waitFor()
    await admin.getByRole('button', { name: `Inspect SYN-00042-0002, ${ticketResult.conversation_id}`, exact: true }).click()
    await admin.locator('.checker-routing').getByText(ticketResult.report.reference, { exact: false }).waitFor()
    await admin.locator('.checker-routing').getByText('Demo West', { exact: true }).waitFor()
    await admin.locator('.checker-diagnostics').getByText('hosted', { exact: false }).waitFor()
    await admin.screenshot({ path: path.join(output, 'customer-report-checker-desktop.png'), fullPage: true })
    const reports = await adminContext.request.get(`${url}/admin/customer-reports`, { headers: { Authorization: `Bearer ${auth.operator.accessToken}` } })
    let oldHistoriesChecked = 0
    for (const row of await reports.json()) {
      if (row.id === ticketResult.conversation_id || row.customer_ref !== 'SYN-00042-0002') continue
      const history = await context.request.get(`${url}/portal/me/chat/conversations/${row.id}`, { headers: { Authorization: `Bearer ${auth.customer.accessToken}` } })
      if (!history.ok()) continue
      for (const turn of (await history.json()).turns) assertCustomerCopy(turn.response)
      oldHistoriesChecked += 1
    }
    assert(oldHistoriesChecked > 0, 'No saved customer histories were checked')
    assert.deepEqual(failures, [])
    console.log(JSON.stringify({ success: true, self_help: result.status, official_mesh_options: true, booking_reschedule_cancel: bookingChecked, report_status: ticketResult.report.status, reference: ticketResult.report.reference, routing: 'Demo West', customer_checker_access: denied, old_histories_checked: oldHistoriesChecked, screenshots: output }))
  } finally {
    if (cleanupBooking) {
      await fetch(`${url}${cleanupBooking.path}/appointments/${cleanupBooking.id}`, { method: 'DELETE', headers: { Authorization: `Bearer ${auth.customer.accessToken}` } }).catch(() => {})
    }
    await browser.close()
  }
}

main().catch((error) => { console.error(error.message); process.exitCode = 1 })
