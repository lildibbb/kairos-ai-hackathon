# Customer support portal and test checker

## Open the prototype

- Customer: http://127.0.0.1:5173/portal (existing `customer@demo.invalid` login and your chosen password).
- Read-only checker: http://127.0.0.1:5173/admin/check.
- Checker demo login: `operator@demo.invalid`, password `Demo-Operator-Only-2026!`.
- Existing teammate/staff workflows still use `/sign-in`, `/operations`, `/work` and `/tickets/...`.

This is a local prototype, not the official Unifi portal. In production, the
official portal's verified customer session must be exchanged for an account-scoped
backend session. Customers should not type another customer's account ID to get
access. This prototype keeps its existing login until that SSO integration exists.
There is no anonymous access to customer readings or ticket creation.

## What happens

1. The customer describes a problem, or selects a service issue.
2. FastAPI looks up only that customer's services and readings. Gemma interprets
   the complaint; Qwen retrieves troubleshooting references. Neither model chooses
   a customer, changes equipment or assigns a technician.
3. The assistant asks about affected devices, Wi-Fi versus Ethernet, nearby-router
   results and (for outages/disconnections) the LOS light. Internal measurement
   findings remain on the server; customers see only advice and questions.
4. A Wi-Fi connection improving near the router suggests coverage may be involved.
   Try placement/device checks first. A compatible mesh system *may* help with
   multi-room coverage; weak RSSI alone does not prove a fault or require a purchase.
   A customer can choose mesh information or keep troubleshooting. Official links
   are shown without inventing prices or promising improvement. A price is shown
   only for a current, verified offer explicitly approved for existing customers.
5. If self-help resolves the issue, no TT is created. If the customer reports red
   LOS or a persistent problem after checks, the backend can create a TT for review.
   Fresh, good-quality optical LOS plus a reported whole-home outage is also an
   escalation condition. Stale/simulated measurements alone never trigger dispatch.
6. If the customer already asked to submit a report, an eligible escalation creates
   the ticket automatically. Otherwise the assistant asks permission first.
   Critical action eligibility uses explicit customer choices/replies, not model
   output. Appointment and root cause are not automatically confirmed.
7. The backend selects an active, available technician in the configured area with
   the fewest active LOCAL customer tickets. Missing area/technician means queued
   and unassigned. An open report for the same customer and issue category is reused
   across conversations. Retrying a message reuses its request ID.
8. If repeated fresh traffic measurements suggest saturation, ask whether pausing
   heavy traffic improves performance before suggesting an optional higher plan.
   Device count alone is insufficient. A profile mismatch or Wi-Fi radio congestion
   is not treated as a reason to buy a higher plan.
9. Customers can request technician support instead of sales. Once a TT exists,
   they can confirm, reschedule or cancel a published visit window in Malaysia
   time. The backend handles reservations and conflicts; the model cannot book
   arbitrary times. Cancelling a visit leaves the trouble ticket open.

This is bounded workflow automation, not unrestricted autonomous model access.
The local application has no live outage adapter, production workforce schedule,
staff ticket lifecycle, notification delivery, or remote router controls.

## Database tables

Migration `0007_customer_dispatch` adds four tables; existing rows are not replaced.

| Table | Purpose |
| --- | --- |
| `dispatch_areas` | Explicit teams/areas, e.g. fictional Demo West and Demo East |
| `customer_dispatch_areas` | Which area covers a customer's installation |
| `technician_dispatch_areas` | Which technician serves which area and whether available |
| `customer_trouble_tickets` | Customer-origin reports, reference, reason, status and assignment |

`customer_chat_conversations` and `customer_chat_turns` retain transcripts and
internal decision snapshots. A `customer_report_created` event is saved in
`audit_events`. The legacy `tickets` table requires a real network event, so it is
left unchanged. Customer reports are intentionally stored separately rather than
fabricating network events; they will **not yet appear in the teammate's staff
ticket list**. Agree on an API adapter/unified ticket interface with that teammate
before integrating these reports into the actual staff workflow.

Demo seeding maps known synthetic references `SYN-00042-0001` through `0010` to
Demo West and `0011` through `0020` to Demo East. These are not real KL/Selangor
boundaries. West uses the existing demo technician; East adds
`technician.east@demo.invalid` with the documented demo technician password.
It never resets existing passwords or overwrites existing customer mappings.
Production routing needs an approved installation-to-zone dataset and real
availability/capacity information, including any existing workforce workload.
The additional support tables, booking safety and configuration are documented in
[Customer support workflows](customer-support-workflows.md).

## APIs and checker

Customer-facing screens and chatbot replies use standard support wording, without
development banners or demo/prototype notices. Existing saved conversations are
formatted the same way when read or retried; stored snapshots are not rewritten.
Customer receipts show `TT-...`, while existing internal `DEMO-TT-...` references
and `is_demo` safety markers remain intact in the database/checker. The public chat
API excludes these markers. This presentation change does not establish live
workforce delivery or live telemetry. Appointment confirmation now comes only
from a committed local database reservation.

- `POST /portal/me/chat/messages`: minimized customer answer/question/receipt.
- `GET /portal/me/chat/conversations/{id}`: owned, minimized chat history.
- `GET /portal/me/reports/{id}/appointment-slots`: eligible windows and current booking.
- `POST /portal/me/reports/{id}/appointments`: confirm or atomically reschedule.
- `DELETE /portal/me/reports/{id}/appointments/{appointment_id}`: cancel a visit.
- `GET /admin/customer-reports`: latest 100 conversations and routing outcomes.
- `GET /admin/customer-reports/{id}`: internal transcript/findings for checking.

The checker is operator/supervisor-only, with no write routes, assignment editing,
reboot controls or customer credentials. Customers and technicians are denied by
the backend, not just hidden in the UI. The older `/portal/me/diagnostics` debug
endpoint still exists for authorized testing; the customer UI never calls it.
Old response snapshots are preserved, but their telemetry-bearing answer text is
not returned in customer history. Internal snapshots are available in the checker.

## Files changed or added

| File | Use |
| --- | --- |
| `backend/app/services/customer_chat.py` | Follow-up state, safe advice and escalation conditions |
| `backend/app/services/customer_dispatch.py` | Atomic local TT creation, area routing, duplicate prevention and audit event |
| `backend/app/domain/customer_chat_schemas.py` | Separate internal and customer-visible response formats |
| `backend/app/domain/models.py` | Four new routing/report models |
| `backend/migrations/versions/0007_customer_dispatch.py` | Additive PostgreSQL migration |
| `backend/app/seed/customer_dispatch.py` | Explicit opt-in fictional area/technician mappings |
| `backend/app/api/customer_portal.py` | Filters internal evidence out of customer chat endpoints |
| `backend/app/api/customer_reports.py`, `backend/app/main.py` | Role-protected read-only checker endpoints |
| `frontend/src/features/portal/CustomerChatPage.tsx` | Desktop customer chat, starter issues, quick replies and receipt |
| `frontend/src/features/portal/ReportCheckerPage.tsx` | Separate local checking screen |
| `frontend/src/features/portal/PortalSignInPage.tsx` | Customer/checker sign-in screens |
| `frontend/src/lib/api/customerChat.ts`, `customerReports.ts` | Validated customer/checker API clients |
| `frontend/src/app/App.tsx`, auth components, `vite.config.ts` | Routes and proxy support; existing staff routes retained |
| `frontend/src/styles.css` | Scoped desktop portal/checker styling, leaving staff styling intact |
| Backend/frontend tests and smoke script | Privacy, escalation, routing, duplicate and UI checks |

## Restart later

```powershell
docker compose build api
docker compose run --rm api alembic upgrade head
docker compose run --rm -e DEMO_SEED_ENABLED=true api python -m app.seed.customer_dispatch
docker compose run --rm -e DEMO_SEED_ENABLED=true api python -m app.seed.customer_support --evidence
docker compose up -d api
cd frontend
npm run dev -- --host 127.0.0.1
```

Demo seeding requires `DEMO_SEED_ENABLED=true` and the previously ingested workforce
dataset. Do not run demo seeding against a production database. Model credentials
stay on the backend. Restore trusted TLS and rotate the screenshot-exposed key
before using real customer data. The existing frontend dependency audit issues,
rate limits, abuse protection, retention policy, approved troubleshooting policy,
SSO and workforce integration must be addressed before public deployment.

`frontend/public/unifi.svg` is an unchanged local copy of the
[official public logo](https://unifi.com.my/themes/unifi/img/newest2022/unifi.svg),
used for branding demonstration. Production branding/hosting must follow the
company's approvals.

## Verified locally on 2026-10-12

- Backend: 218 tests passed, plus three opt-in PostgreSQL concurrency/exclusion
  checks; frontend: 34 tests passed; production build passed.
- Hosted Gemma/Qwen browser test: self-help resolved without a TT, then reported
  red LOS produced an assigned Demo West TT visible in the checker.
- Customer access to the checker returned 403; repeat issue reused the existing TT.
- Screenshots inspected at 1440x900 and 1280x800; chat input and latest reply remain visible.
- Existing 20 customers, 80 services, 80 devices and 20 legacy tickets were retained;
  all 14 1024-dimensional knowledge vectors and original 1536-vector fingerprint
  were unchanged. No equipment actions were executed.
- One synthetic customer TT and test conversations were intentionally added by
  the smoke test; screenshots remain ignored under `frontend/.local/`.
- Customer-facing wording verified on new turns, ticket receipts, both sign-in
  screens and saved histories. Internal data provenance and safety guards remain unchanged.
- Official mesh referral, continued troubleshooting, appointment confirmation,
  reload, rescheduling, cancellation and checker booking status were exercised
  in the browser. Chat receipts refresh immediately to the current appointment.
- Coverage wording is consistent for both one-device and all-device reports.
  Existing coverage history is formatted correctly without rewriting audit snapshots.
- Added 60 simulated traffic samples, 40 simulated radio measurements, two
  price-less official referrals, 10 fictional shifts and 30 future visit windows.
  Rerunning the seed added zero rows; PostgreSQL test schemas were removed.
