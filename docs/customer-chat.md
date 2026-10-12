# Customer chatbot diagnostics

The optional model-directed agent and customer-confirmed simulated router actions
are documented in [Customer agent showcase](customer-agent-showcase.md). The
original guided path remains available with `CUSTOMER_CHAT_MODE=guided`.

## Try it

Open the running frontend and sign in with your existing demo customer login.
Customers land on `/portal`; staff still land on their existing workspaces. Enter:

> My internet is slow, I want to make a report.

The response shows a plain-language outcome and asks one follow-up question.
Customers do not receive internal readings, database identity fields, diagnostic
findings, model metadata or retrieval details in chat responses. Use the answer
choices or reply in your own words.
The assessment refreshes from the database on every turn. Previous replies remain
in conversation history; changing a customer's account link does not give access
to an old household's conversation.

This version can create a LOCAL customer trouble ticket and assign an eligible
technician from an explicitly configured area. It can reserve an appointment from
published local technician windows. It does not send a ticket to a real
Unifi workforce system, reboot physical equipment, change live settings or run a
live network test. Agent mode can perform explicitly labelled, isolated action
simulations. See [Customer portal](customer-portal.md) for routing,
the desktop UI and the separate read-only checker.
Missing readings and matching profiles never imply that everything is healthy.

## Technician escalation and appointments

The escalation reply now explains the reason before showing the trouble-ticket
reference. A customer-reported red or blinking LOS light is described as a
possible fibre issue requiring an on-site check, not a confirmed root cause.
Persistent problems after troubleshooting require technician investigation
without assuming an on-site visit is already arranged. Without permission to
submit a report, the bot asks first; after creation, it confirms the receipt.
Saved ticket replies and retries use the same wording without rewriting audit
snapshots. A ticket assignment is not an appointment confirmation.

Appointment booking is implemented for published, fixed visit windows:

1. Show visit windows for eligible technicians in the customer's configured area,
   accounting for imported shifts, leave, reserved windows and travel buffer. Display times in
   `Asia/Kuala_Lumpur`; store timezone-aware timestamps.
2. Let the customer select and confirm a window. Viewing a window does not reserve
   it, and the chatbot must not invent available times.
3. In one short database transaction, lock the existing slot or technician row,
   recheck availability, record the appointment and update the ticket's final
   technician assignment. Confirm to the customer only after commit.
4. If the last capacity was just booked, return a slot-unavailable conflict and
   offer refreshed alternatives. Keep the trouble ticket open. Retries reuse a
   booking request ID; cancellation and rescheduling release capacity atomically.

The new tables are `technician_shifts` (working periods and
unavailability), `appointment_slots` (technician, start/end and travel buffer), and
`appointments` (ticket, slot, status and unique retry ID). Permit only one active
booking per technician slot and one active appointment per ticket. Windows for
the same technician must not overlap, including across service areas. If windows
can vary, non-overlapping technician time ranges are enforced with a PostgreSQL
exclusion constraint, including the reserved travel buffer.

With one available technician, two customers may see the same window, but only
one booking transaction can reserve it. The other customer gets different times.
If another eligible technician is free, both can use that window with different
technicians. Existing ticket assignment should be provisional until booking;
any approved reassignment must agree with the appointment's technician. Combine
workload from this portal, the existing staff tickets and any external workforce
schedule before exposing real availability.

Coverage and bandwidth assessments, optional official sales links, booking APIs,
the seven new tables and test instructions are explained in
[Customer support workflows](customer-support-workflows.md).

PostgreSQL supports [row locking](https://www.postgresql.org/docs/16/explicit-locking.html#LOCKING-ROWS)
and [non-overlapping range constraints](https://www.postgresql.org/docs/16/rangetypes.html#RANGETYPES-CONSTRAINT).
These controls belong in the backend and database, not the model prompt.

## How it works

```text
Customer message + authenticated login
  -> account-scoped diagnostics from PostgreSQL
  -> bounded symptom interpretation (Gemma or local guided fallback)
  -> fixed-category troubleshooting retrieval (Qwen + pgvector)
  -> backend checks the scoped readings for possible fault indicators
  -> optional model-directed tool loop and backend-authorized outcome
  -> hosted model writes a contextual reply from approved facts and recent dialogue
  -> customer-safe result + follow-up or local trouble-ticket receipt
  -> save the conversation turn in PostgreSQL
```

Gemma interprets the customer's reported service issue, connection type, device
scope, attempted checks, and explicit improvement/failure feedback. Its response
must match a strict enum-only JSON schema. The backend owns findings, status,
question eligibility, consent and execution. A separate hosted response writer
adapts the explanation to the customer's wording and recent conversation; it
cannot create new findings or execute actions. Generated prose is validated,
with approved wording as the offline/error fallback. Action, ticket and appointment
facts remain server-rendered. Recent customer messages (at most six), prior reported
symptoms and the last question are supplied to the model. Database addresses,
names, equipment secrets, device IDs and SSIDs are not sent to it. User messages
can themselves contain personal information; use synthetic reports during testing.
Credential-shaped assignments are redacted before model calls and persistence,
but this is not a general-purpose personal-data detector.

Qwen receives a fixed troubleshooting query for the interpreted category, not the
customer's private message. Retrieved references stay in the internal snapshot;
they are not proof of a fault or model instructions.
This version's diagnostic checks and questions are backend-defined, not generated
from the retrieved procedures. Customer-facing approved procedures should be
curated before expanding remediation advice.

The checks cover stored optical LOS, WAN-down status, repeated disconnects,
weak Wi-Fi, retry rates, speed-profile mismatches, voice registration and IPTV
stream/multicast problems. The Wi-Fi cutoffs (RSSI below -70 dBm, retries at least
20%) and disconnect cutoff (three in 24 hours) are demo heuristics, not operator-
approved universal thresholds. Wired complaints do not blame Wi-Fi measurements.
Every measurement finding carries freshness/quality and its observation time.
Simulation and stale measurements require live verification, not a confirmed
root-cause claim. Inventory configuration is labelled separately from live evidence.

If the chat gateway fails or returns malformed output, guided checks still work
and `mode=fallback` is recorded for the checker. If embedding fails,
`knowledge_status=unavailable` is recorded internally and guided checks continue. A successful demo
response is not proof of production readiness or real-time network health.

## API and conversation storage

In Swagger, authorize using the customer login, then call:

```http
POST /portal/me/chat/messages
Content-Type: application/json

{"message": "My internet is slow, I want to make a report."}
```

To continue, reuse the returned `conversation_id` and supply a NEW `request_id`
(UUID) per message. `request_id` is generated if omitted, but retries should reuse
the SAME ID. For a displayed answer choice, send `answer_choice` with its exact
value; the backend checks it against the prior question. No customer ID or client-
supplied conversation history is accepted.

```json
{
  "message": "Every device",
  "conversation_id": "COPY-THE-RETURNED-UUID-HERE",
  "request_id": "GENERATE-A-NEW-UUID-HERE",
  "answer_choice": "all_devices"
}
```

`GET /portal/me/chat/conversations/{conversation_id}` returns an owned transcript.
Conversations are limited to 30 turns. The browser stores only the active
conversation ID per user in session storage and reloads the transcript from the
server; the access token stays in the existing auth-session mechanism.

Migration `0006_customer_chat` adds two tables, leaving the staff assistant tables
unchanged:

| Table | Purpose |
| --- | --- |
| `customer_chat_conversations` | Links a conversation to both the login and household |
| `customer_chat_turns` | Ordered customer messages and validated response snapshots, with retry IDs |

Customer and staff roles remain separated. Another customer cannot read or resume
a conversation even if its UUID is known. Conversation locking and uniqueness
constraints prevent competing turns from silently overwriting one another.

## Configuration and deployment

`CUSTOMER_CHAT_PROVIDER=local` is the safe default. `hosted` uses the configured
Gemma alias through the existing model gateway. This is independent of
`MODEL_PROVIDER`, which still controls the staff assistant. Qwen embedding settings
are shared with existing knowledge retrieval. Keep model keys on the backend.

```powershell
docker compose build api
docker compose run --rm api alembic upgrade head
docker compose up -d api
cd frontend
npm ci
npm run dev -- --host 127.0.0.1
```

The Vite proxy forwards `/portal/me/...` to FastAPI while keeping the `/portal`
HTML page in the frontend. The temporary `MODEL_TLS_VERIFY=false` override remains
development-only. Non-demo customer chat is blocked when either hosted provider
would use unverified TLS. Restore certificate verification and rotate the key
exposed in screenshots before using real customer data.

## Files

| File | Purpose |
| --- | --- |
| `backend/app/domain/customer_chat_schemas.py` | Bounded request, interpretation, finding and response formats |
| `backend/app/services/customer_chat.py` | Scoped history, diagnostic rules, model fallback and follow-up flow |
| `backend/app/api/customer_portal.py` | Authenticated message and transcript endpoints |
| `backend/app/domain/models.py`, migration `0006_customer_chat.py` | Two customer conversation tables |
| `backend/app/config.py` | Separate customer chat provider setting |
| `frontend/src/features/portal/CustomerChatPage.tsx` | Desktop customer conversation, quick replies and report receipt |
| `frontend/src/lib/api/customerChat.ts` | Authenticated requests and response validation |
| `frontend/src/app/App.tsx`, `features/auth/ProtectedRoute.tsx` | Customer-only route and sign-in destination |
| `frontend/vite.config.ts`, `src/styles.css` | API proxy and desktop-first portal/checker layouts |
| Backend/frontend customer-chat tests | Isolation, history, retries, evidence and gateway failure cases |
| `frontend/scripts/customer-chat-smoke.cjs` | Optional Playwright smoke test using an existing demo login and short-lived token |

The original verification on 2026-10-12 exercised the hosted Gemma/Qwen flow and
history reload. The updated smoke test exercises self-help and local routing on
desktop. Test screenshots and local
server logs are ignored under `frontend/.local/`. The smoke script needs Playwright
(or its module path as argument 2), a running frontend (URL as argument 3), and an
installed browser (optional channel, such as `msedge`, as argument 4). It adds a
synthetic conversations and a local trouble ticket to the database but makes no equipment changes.

The existing locked frontend dependencies report 15 npm audit vulnerabilities.
They were not upgraded as part of this scoped feature; review them before deploying
the portal beyond local development. Rate limits, transcript retention and approved
operator diagnostic policies are also required before production use.
