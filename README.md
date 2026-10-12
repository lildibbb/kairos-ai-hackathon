# Field Force Incident Assistant

An authenticated field-operations app that turns one processed network event into an assigned
ticket, then helps the assigned technician diagnose it with retrieval-grounded answers and
permission-checked device actions.

**Status:** 24-hour hackathon MVP. All customer, device, and credential data is synthetic demo data.
No live TMF/NTT/OSS or real device integration is included.

## What it does

1. An operator processes a seeded network event. The backend creates and assigns exactly one ticket
   (idempotent: reprocessing returns the existing ticket).
2. The assigned technician opens the ticket and sees the customer service context (Granite, HSI,
   VoBB, address) and the customer topology path.
3. The technician reveals a sensitive ONU credential only through a deliberate, audited action.
4. The technician asks the assistant a question. Answers are grounded in retrieved knowledge and
   the authorized ticket context, and every citation is validated against the retrieved chunks.
5. The assistant can propose an allowlisted device action (status check, router reboot, bounded
   config change). State-changing actions run only after explicit approval, and every run is
   recorded in an audit timeline.

The assistant chat is built from AI Elements components vendored into `frontend/src/components/ai`
(Conversation, ChainOfThought, Confirmation, Plan, Edge) on top of shadcn/ui primitives in
`frontend/src/components/ui`. The service topology draws active links with an animated traveling
marker and interrupted links as dashed segments. The demo seed ships 7 curated field procedures and
10 realistic incidents across two customers covering optical, HSI, VoBB, IPTV, Wi-Fi, CPE, and DNS.

The agent can reason over the retrieved procedure and rank grounded actions, or select a single one.
`POST /tickets/{ticket_id}/tools/agent-plan` with `{ "question": "...", "device_id": "..." }` returns up
to four ranked suggestions (tool, rationale, configuration steps, risk tier, confidence, evidence);
`device_id` is optional and, when omitted, the backend targets the device the request is about (for
example a Wi-Fi channel change selects the router). To prepare the chosen suggestion, call
`POST /tickets/{ticket_id}/tools/agent-propose` with
`{ "question": "...", "device_id": "...", "tool_name": "...", "parameters": {...} }`; omitting
`tool_name` lets the model make the single selection instead. The backend checks the assigned ticket,
retrieved procedure, device/customer scope, tool allowlist, and typed arguments. A selected read-only
check runs immediately; state-changing actions are returned as proposals and require the separate
`/confirm` call. Evidence chunk IDs are recorded in the audit event.

In the assistant, a request that reads like a change (for example "configure the router to change the
channel to 44") triggers the plan automatically: the agent picks the target device, resolves the
requested value (5 GHz channel 44), and shows the ordered configuration steps before anything is
prepared. Selecting a suggestion highlights the target on the topology, and approving the action
animates the change on the target node.

The catalog spans read-only diagnostics (`get_device_status`, `list_connected_clients`,
`run_speed_test`, `run_optical_diagnostics`) and state-changing actions across Wi-Fi, optical, service,
and network policy (`reboot_router`, `reboot_ont`, `refresh_ont_registration`, `reset_optical_port`,
`update_config`, `set_wifi_ssid`, `set_wifi_channel`, `flush_dns_cache`, `restart_service`,
`block_client`, `set_dhcp_reservation`). Each tool declares a category and risk tier
(`low`/`medium`/`high`) that the UI surfaces alongside the ranked plan.

Event intake supports an optional authenticated SSE run stream. Create an event run, connect to its
event stream, then process the event with the returned `run_id`:

```text
POST /events/runs
GET  /events/runs/{run_id}/events
POST /events/{event_id}/process?run_id={run_id}
GET  /events/runs/{run_id}
```

The stream emits `processing`, then `ticket_created` or `failed`. Reconnect with the
`Last-Event-ID` header to replay events after the last received event. Run state is held in API
process memory for this single-process MVP; a restart clears run history.

Ticket troubleshooting also exposes an authenticated WebSocket endpoint:

```text
WS /tickets/{ticket_id}/assistant/stream?token={access_token}
```

Send `{"question":"..."}` after the `ready` frame. The server sends `retrieval_started`, then an
`answer` frame containing the same validated citations and recommendations as the HTTP endpoint,
followed by `complete`. The HTTP `POST /tickets/{ticket_id}/assistant/messages` remains available
for clients that do not support WebSockets. The current chat provider returns complete structured
answers, so this stream reports retrieval progress and the final answer rather than token deltas.

## Architecture

- **Frontend:** React + TypeScript + Vite, Tailwind, Radix primitives, TanStack Query-ready API layer.
- **Backend:** FastAPI + Pydantic + SQLAlchemy 2 + Alembic.
- **Data:** PostgreSQL with the `pgvector` extension for both relational records and knowledge
  embeddings. PostgreSQL is required (see "Database notes" below).
- **AI:** provider-port design. Defaults to a deterministic local embedding + chat provider so the
  demo runs without external API keys; hosted OpenAI-compatible providers are selectable by setting.

## Prerequisites

- Docker Desktop (for PostgreSQL + the API).
- Node.js 20+ and npm (for the frontend dev server).

## Setup

```bash
cp .env.example .env
```

Edit `.env` if a port is already in use. To run the demo with the built-in sample data, set:

```
DEMO_SEED_ENABLED=true
```

All example values are local-only placeholders. Do not reuse them anywhere shared.

## Model providers

The chatbot, retrieval (RAG), and agent all run through provider boundaries selected by environment
variables. By default `MODEL_PROVIDER`, `REASONING_PROVIDER`, and `EMBEDDING_PROVIDER` are `local`,
which uses key-free deterministic providers so the demo runs offline. To use real models, set those
three variables to `hosted` and provide the OpenAI-compatible endpoint settings
(`MODEL_BASE_URL`, `MODEL_API_KEY`, `MODEL_NAME`, `REASONING_MODEL_NAME`, `EMBEDDING_MODEL`). The
`.env.example` already contains the hosted GIGX values; paste the real `MODEL_API_KEY` into `.env`.
GIGX presents a private CA certificate, so set `MODEL_CA_BUNDLE=/path/to/ca.pem` if you have the CA,
or `MODEL_TLS_VERIFY=false` for this trusted internal dev endpoint. Confirm the exact model IDs with
`GET {MODEL_BASE_URL}/models`; they must match `MODEL_NAME`, `REASONING_MODEL_NAME`, and
`EMBEDDING_MODEL`.

The embedding dimension must match the hosted model's output size. GIGX
`qwen3-embedding-0.6b` returns up to 1024 dimensions, so `EMBEDDING_DIMENSIONS=1024`. If you
switch to a different embedding model, confirm its size with
`docker compose run --rm api python -m app.integrations.embeddings`, set `EMBEDDING_DIMENSIONS`,
and add a migration that resizes `knowledge_chunks.embedding`.

## Run the backend (Docker Compose)

```bash
docker compose up -d db
docker compose run --rm api alembic upgrade head
docker compose run --rm api python -m app.seed.demo_data        # requires DEMO_SEED_ENABLED=true
docker compose run --rm api python -m app.ai.ingestion --reembed  # fills knowledge embeddings
docker compose up -d api
```

Pass `--reembed` whenever the embedding provider or model changes: vectors from different models are
not comparable in one index, so stored vectors must be regenerated. Without it, ingestion only fills
chunks that have no embedding yet. Ingestion also embeds the derived entity fact sheets (router,
optical, VoBB, IPTV, and TMFORCE ticket fields) so the assistant can cite live device and service
data alongside curated procedures.

Device, service, and ticket fields live in two layers: typed values in `entity_facts` for exact
display and one embeddable `entity_fact_sheets` row per fact group for retrieval. Sensitive fields
(VoBB/IPTV passwords) are marked `is_sensitive`, never enter the embedded content, and are revealed
only through the audited credential endpoints (`/tickets/{ticket_id}/devices/{device_id}/credential`
and `/tickets/{ticket_id}/services/{service_id}/credential`). `GET /tickets/{ticket_id}/facts`
returns the redacted fact list for the UI.

The API is then available at `http://localhost:8000` (health: `GET /health`, docs: `/docs`).

## Run the frontend

```bash
cd frontend
npm install
npm run dev
```

The dev server proxies `/auth`, `/events`, `/tickets`, and `/audit` to `http://localhost:8000`
(override with `VITE_API_PROXY_TARGET`).

## Demo accounts (synthetic)

| Role | Email | Password |
|---|---|---|
| Operator | `operator@demo.invalid` | `Demo-Operator-Only-2026!` |
| Technician | `technician@demo.invalid` | `Demo-Technician-Only-2026!` |

These accounts exist only when `DEMO_SEED_ENABLED=true`. They are demo-only and must never be
enabled in a shared or production environment.

## Demo walkthrough

1. Sign in as the operator and open **Event intake**. Process the seeded ONU-offline event.
2. Confirm the created ticket and its assignment.
3. Sign out and sign in as the technician. Open **My work** and the assigned ticket.
4. Review the service details and the customer topology path.
5. Deliberately reveal the ONU credential (this writes an audit entry).
6. Ask the assistant why the service is down and what to check before dispatch; review the cited
   evidence and the next-best-action panel.
7. Open **Run a device action**, prepare a router reboot (or a bounded config change), and approve it.
8. Open **View audit history** to see the event, credential reveal, proposal, and execution.

## Test and build commands

```bash
# Backend
cd backend
python -m pytest

# Frontend
cd frontend
npm test -- --run
npm run build
```

## Database notes

The app connects using `DATABASE_URL`. DBeaver is a database client, not a provider, and phpMyAdmin
targets MySQL/MariaDB, so neither makes a non-PostgreSQL database compatible with this schema. The
MVP targets PostgreSQL because relational records and `pgvector` embeddings live in one database.
The embedding dimension is fixed by a migration (currently 1024 for the GIGX model); changing it
requires a new migration.

## Security notes

- Authorization is enforced server-side on every customer, ticket, topology, credential-reveal, and
  tool endpoint. Assignment scope is checked in the service layer, not only the UI.
- Credentials are revealed only inside an authorized assigned-work context and are never written to
  the assistant transcript, ticket narrative, or audit payloads.
- The assistant may propose tools, but the backend validates role, assignment, device, parameters,
  and confirmation before anything executes. Replayed confirmations are idempotent.
- No secrets are committed. Real customer data and real credentials must never be used with this
  demo.

## Out of scope

Live TMF/NTT/device integration, broad event taxonomy, configurable routing, production identity
federation, and real network configuration changes.

## Customer portal

Authenticated customers sign in at `/portal/sign-in` and reach a self-service workspace: grounded
troubleshooting chat, live diagnostics, appointment booking, and a bounded model-directed agent with
confirmed router reboot / VLAN restore simulations. Staff enter the customer operations view from
`/admin/sign-in` → `/admin/check`. See [Customer portal](docs/customer-portal.md),
[Customer chat](docs/customer-chat.md), [Customer diagnostics](docs/customer-diagnostics.md), and
[Customer agent showcase](docs/customer-agent-showcase.md) for the walkthroughs and safety
boundaries.
