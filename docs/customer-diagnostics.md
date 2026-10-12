# Customer-scoped diagnostics: first implementation

This adds the read-only database lookup for a future customer chatbot. It does
not create a customer chat UI, call an AI model, diagnose a root cause, create a
ticket, assign a technician, or operate equipment.

## Environment and model settings

Keep your existing PostgreSQL credentials. Model credentials are separate.
The screenshot's model gateway uses these non-secret settings in the root `.env`:

```dotenv
MODEL_BASE_URL=https://gigx.nexa-dev.tm.com.my/llm/v1
MODEL_NAME=gemma-4-e2b-it
EMBEDDING_MODEL=qwen3-embedding-0.6b
MODEL_PROVIDER=local
EMBEDDING_PROVIDER=local
EMBEDDING_DIMENSIONS=1536
```

Put the complete gateway API key in `MODEL_API_KEY` locally; the existing hosted
chat and embedding adapters share that key and base URL. Do not commit it, paste
it into frontend code, or include it in screenshots. A masked key cannot be used.
The model identifiers above are the gateway aliases shown in your screenshot,
not the full upstream Hugging Face names.

Leave the provider switches on `local` for this diagnostic milestone. These
settings stage the model names but do not contact the gateway. When hosted chat
is intentionally enabled later, `MODEL_PROVIDER=hosted` selects the adapter, but
the gateway's response format and model tool support still need testing.

Hosted Qwen embeddings use the separate 1024-dimensional column added by migration
0005; local embeddings use the preserved 1536-dimensional column. Follow
[the Qwen migration guide](qwen-embedding-migration.md) to probe the gateway,
re-index and verify knowledge before enabling hosted retrieval. Do not mix vectors
from different models, even if dimensions match. Customer diagnostics do not
depend on either embedding provider.

Official references: [Qwen embedding model](https://huggingface.co/Qwen/Qwen3-Embedding-0.6B)
and [Gemma function calling](https://ai.google.dev/gemma/docs/capabilities/text/function-calling-gemma4).

Freshness defaults to 15 minutes. Optionally set `DIAGNOSTIC_MAX_AGE_SECONDS=900`
in `.env`; it must be positive. Do not increase it just to make old fixtures look live.

## How customer access works

```text
POST /auth/login -> signed customer token
GET /portal/me/diagnostics -> token's user_id
                         -> customer_accounts link
                         -> that household's services, devices and readings
```

The new `customer_accounts` table has two fields:

| Field | Purpose |
| --- | --- |
| `user_id` | Primary key, referencing the login in `users` |
| `customer_id` | References the household in `customers` |

One login is linked to one household in this MVP. Multiple customer logins can
be linked to the same household. Multiple installations per login are future
work and need explicit installation authorisation.

Only an active login with the `customer` role and an account link can read this
endpoint. There is no selectable customer ID or address parameter. Staff logins
are rejected here; the existing staff routes also reject the customer role.
There is no public endpoint that allows users to create or change account links.
Real account enrolment must be handled by a verified registration process.

## Apply and try it locally

Run from the repository root with Docker Desktop running. These steps preserve
existing data and add just the account-link table:

```powershell
docker compose build api
docker compose run --rm api alembic upgrade head
docker compose up -d api
```

Provision one fictional customer login. The selected household already exists
in the 20-household fixture and represents weak Wi-Fi:

```powershell
docker compose run --rm -e DEMO_SEED_ENABLED=true api python -m app.seed.customer_account --customer-ref SYN-00042-0002 --email customer@demo.invalid
```

The command prompts for a password of at least 12 characters without displaying
it. For automation, it can read `DEMO_CUSTOMER_PASSWORD` from the environment.
It hashes the password, creates the customer role/login and account link, and
refuses non-demo households. Running it again preserves an existing matching
login and password; it never silently reassigns an account or resets a password.
If the selected fixture household is missing, import the workforce dataset first
using [the dummy-data guide](dummy-data-and-postgres.md).

Open [FastAPI Swagger](http://localhost:8000/docs), click **Authorize**, and enter
`customer@demo.invalid` plus your chosen password. Leave optional client ID and
client secret blank. Then expand `GET /portal/me/diagnostics`, click **Try it out**,
and **Execute**. Alternatively, use PowerShell:

```powershell
$credential = Get-Credential -UserName 'customer@demo.invalid' -Message 'Local demo customer login'
$login = Invoke-RestMethod -Method Post -Uri 'http://localhost:8000/auth/login' -Body @{
    username = $credential.UserName
    password = $credential.GetNetworkCredential().Password
}
$diagnostics = Invoke-RestMethod -Uri 'http://localhost:8000/portal/me/diagnostics' -Headers @{
    Authorization = "Bearer $($login.access_token)"
}
$diagnostics | ConvertTo-Json -Depth 10
```

## Response contents

| Response field | Database source and meaning |
| --- | --- |
| Customer reference/name/address | Linked `customers` row |
| `services` | Own subscriptions; only numeric speed-profile fields from `services.details` |
| `devices` | Own inventory; latest `device_measurements` snapshot per device |
| `wifi_networks` | Own router radio configuration and SSIDs |
| `wifi_clients` | Latest client reading, only if both client and Wi-Fi network belong to the household |
| Service `latest_measurement` | Latest `service_measurements` reading, including voice/IPTV state |
| `warnings` | Missing, stale, simulated, incomplete or temporally invalid evidence |
| `requires_follow_up` | Always true for this data-collection milestone; not a fault classifier |

Each observation includes when it was measured (`observed_at`), when it arrived
(`ingested_at`), its age, source, quality, and `freshness`. Freshness means its
timestamp meets the configured age limit, not that the service is healthy.
The latest observation is chosen by measured time, then ingestion time, then ID
for deterministic ties. Unknown values remain `null`; they are not turned into
zeros or inferred healthy states. A recent bad Wi-Fi association is flagged,
not replaced with an older valid association.

Device inventory status and subscription status are explicitly separate from
timestamped operational status. Old or invalid snapshots remain visible as
evidence with warnings; there is no silent fallback to a healthy earlier row.
The fixed October 12 fixtures will naturally become stale. No live checks ran.
The response excludes raw equipment/service JSON, passwords and staff ticket
information. The endpoint performs SELECTs only and calls no external model.

## Files added or changed

| File | Purpose |
| --- | --- |
| `backend/app/api/customer_portal.py` | FastAPI endpoint and account-link error response |
| `backend/app/services/customer_diagnostics.py` | Authorised lookup, latest observations, numeric allowlist and warnings |
| `backend/app/domain/diagnostic_schemas.py` | Typed response fields; prevents exporting raw credential-bearing JSON |
| `backend/app/domain/models.py` | New `CustomerAccount` database model |
| `backend/migrations/versions/0004_customer_accounts.py` | Creates the account-link table without changing existing rows |
| `backend/app/auth/tokens.py` | Accepts signed customer-role tokens, without granting staff permissions |
| `backend/app/main.py` | Registers the customer portal router |
| `backend/app/config.py` | Adds a validated freshness setting |
| `backend/app/seed/customer_account.py` | Guarded, explicit demo-login provisioning |
| `backend/tests/test_customer_diagnostics.py` | Authentication, isolation, evidence quality and provisioning tests |
| `docs/customer-diagnostics.md` | This setup and explanation guide |
| `README.md` | Link to this guide |

The [customer chatbot](customer-chat.md) now consumes this diagnostic response and
asks focused follow-up questions. Ticket confirmation, zone-based dispatch and
real equipment actions remain separate milestones. The environment example above
describes the original diagnostic-only milestone; see the Qwen and customer-chat
guides for the current hosted settings.
