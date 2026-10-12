# Customer diagnosis, sales options and appointments

## Try the flow

Open http://127.0.0.1:5173/portal and sign in with your existing customer account.
The staff-only checking screen is http://127.0.0.1:5173/admin/check.

1. Describe the issue. The server checks only the household linked to that login.
2. Answer the follow-up questions. Customer messages never receive raw database
   readings, equipment identifiers, addresses or internal assessment snapshots.
3. A Wi-Fi connection improving near the router suggests coverage. Try placement
   checks first, then optionally select **Learn about mesh**.
   This remains a possible location-related coverage issue even if only one
   device was reported. Compare another device in the same spot before assuming
   it affects the household or considering mesh. The wording follows the recorded
   assessment; it does not claim that every device has a weak measured signal.
4. A busy household is not automatically a capacity problem. Several recent,
   good-quality traffic windows must show saturation, and the customer must report
   improvement after pausing heavy traffic, before **Compare plans** is offered.
5. Sales are optional. **Keep troubleshooting**, **Find a Unifi Store**, and
   **Request a technician** remain available. A requested visit is not presented
   as proof of a fault.
6. A qualifying escalation creates/reuses a TT and routes it to the configured
   area. The appointment picker then displays published technician visit windows.
7. Select a date and window and confirm. A competing reservation returns a conflict
   and refreshed alternatives, not a false confirmation. Rescheduling replaces
   the old reservation atomically; cancellation leaves the TT open.

Stored profile mismatches, current WAN/LOS faults and Wi-Fi radio congestion take
precedence over sales recommendations. Stale or simulated telemetry cannot prove
current saturation or justify an automatic plan recommendation. Thresholds remain
conservative project heuristics requiring operator approval for production.

## Tables

Migration `0008_customer_support` adds seven tables without replacing the existing
customer, device, ticket, transcript or embedding records.

| Table | What it stores | Why it is separate |
| --- | --- | --- |
| `wan_usage_samples` | Router traffic rate, active-device count and measurement window | Traffic changes over time; several windows are needed, not one inventory field |
| `wifi_radio_measurements` | Radio channel utilization with time, source and quality | Separates radio congestion from subscription capacity |
| `product_offers` | Verified mesh/plan descriptions, links, optional prices, eligibility and validity | Promotions expire and vary by eligibility; they must not come from model memory |
| `store_locations` | Verified store details by postcode | Prepared for an approved store feed; no store list is fabricated or seeded |
| `technician_shifts` | Working periods and unavailable periods | Being assigned to an area does not imply being free at any time |
| `appointment_slots` | Published physical technician windows, including travel buffer | The same technician cannot have overlapping windows, even across areas |
| `appointments` | Customer TT, reserved slot, status and retry ID | One active visit per TT and one active reservation per physical slot |

Existing `customer_trouble_tickets` remains separate from legacy event-driven
`tickets`. Both need a unified integration contract with the teammate's staff
portal before operational deployment. Booking updates the TT's final technician
assignment to match the reserved slot and writes an audit event.

## Changed files

| File | Purpose |
| --- | --- |
| `backend/app/services/customer_triage.py` | Evidence-based coverage, capacity, profile and radio assessment |
| `backend/app/services/customer_diagnostics.py`, `domain/diagnostic_schemas.py` | Read new telemetry within the authenticated household scope |
| `backend/app/services/customer_sales.py` | Filter current, verified offers and allowlisted official HTTPS links |
| `backend/app/services/customer_chat.py`, `domain/customer_chat_schemas.py` | Follow-up choices, optional sales and technician escalation; internal evidence stays private |
| `backend/app/services/customer_appointments.py`, `domain/appointment_schemas.py` | Ownership, calendar eligibility, locking, retry IDs, booking/rescheduling/cancellation |
| `backend/app/api/customer_portal.py` | Customer-only appointment endpoints alongside existing chat |
| `backend/app/api/customer_reports.py` | Read-only checker includes the current committed appointment |
| `backend/app/domain/models.py`, migration `0008_customer_support.py` | Seven tables and database conflict constraints |
| `backend/app/seed/customer_support.py`, `seed/workforce_data.py` | Opt-in, append-only fictional windows and explicitly simulated traffic/radio samples |
| `frontend/src/features/portal/AppointmentPicker.tsx` | Date/window selection, confirmation, retries, rescheduling and cancellation |
| `frontend/src/features/portal/CustomerChatPage.tsx`, `ReportCheckerPage.tsx` | Official offer links and customer/checker booking status |
| `frontend/src/lib/api/customerAppointments.ts`, `customerChat.ts`, `customerReports.ts` | Validated API responses and authenticated requests |
| `frontend/src/styles.css` | Desktop sales and appointment layouts |
| Backend/frontend tests and `frontend/scripts/customer-chat-smoke.cjs` | Evidence, privacy, conflict, retry, history and browser checks |

## Apply and run

From the repository root:

```powershell
docker compose build api
docker compose run --rm api alembic upgrade head
docker compose up -d api
```

For the existing fictional workforce dataset only, opt in to published fixture
windows and separate historical telemetry:

```powershell
docker compose run --rm -e DEMO_SEED_ENABLED=true api python -m app.seed.customer_support --evidence
```

This inserts missing rows only. It never resets passwords, replaces customer
mappings, overwrites bookings or changes old readings to look fresh. Synthetic
measurements stay `quality=simulated`; they deliberately do not trigger live
capacity conclusions. Rerun without `--evidence` to add new future fixture dates.
Keep `DEMO_SEED_ENABLED=false` in normal configuration.

```powershell
cd frontend
npm run dev -- --host 127.0.0.1
```

Existing PostgreSQL and Qwen/pgvector credentials remain unchanged. No new model
or vector dimension is required for these workflows. Use the trusted company CA
and restore TLS verification before processing real customer data.

## Conflict safety and tests

The backend locks the household/TT and physical technicians in a stable order,
rechecks shift and reservation availability, then commits before confirmation.
Database partial unique indexes prevent multiple active reservations per slot/TT.
PostgreSQL `btree_gist` and an exclusion constraint prevent overlapping published
windows, including their travel buffers. Viewing availability holds no reservation.
API callers must retry an uncertain booking with the same `request_id` and payload.
Changes/cancellations within two hours of the visit require support assistance.

The normal backend suite uses isolated SQLite fixtures. Actual PostgreSQL locking
and exclusion tests are opt-in, create a random `appointment_test_*` schema and
remove only that schema afterward. Run them against the migrated local database:

```powershell
docker compose run --rm -e APPOINTMENT_POSTGRES_TESTS=1 -e CUSTOMER_CHAT_PROVIDER=local -e EMBEDDING_PROVIDER=local -e MODEL_TLS_VERIFY=true -v "${PWD}/backend/tests:/app/tests:ro" api pytest -q /app/tests/test_customer_appointments_postgres.py
```

Wait for a one-off test container to exit before using `docker compose exec` or
running the browser smoke test. Frontend tests/build:

```powershell
cd frontend
npm test -- --run
npm run build
```

## Remaining operational integrations

Appointments are database reservations, not confirmed visits in Unifi's external
workforce system. Before exposing real availability, import all existing workforce
jobs, legacy staff-ticket commitments, leave and travel rules into the calendar;
integrate booking delivery/acknowledgement, notifications and reconciliation.
There is no invented availability when no published eligible windows exist.

Sales currently hand off to official Unifi pages. No purchases or subscription
changes happen here. Populate `product_offers` from an approved current feed to
show specific offers; uncertain eligibility hides prices/contract terms. The
store action opens the official locator, not a claimed nearest store. Accurate
nearest-store results require an approved location feed and distance lookup;
postcode matching alone does not establish proximity.

Production still needs portal SSO, live telemetry/outage integration, approved
diagnostic policies, rate limits, retention rules, monitoring and staff integration.
The customer chatbot does not reboot equipment or change router settings.
