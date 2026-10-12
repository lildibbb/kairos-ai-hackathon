# Dummy data, PostgreSQL, DBeaver and pgvector

## What each component does

- PostgreSQL stores customer, service, device, ticket and measurement records.
- pgvector is an extension inside the same PostgreSQL database. It stores and searches the numeric embeddings used to retrieve troubleshooting documents.
- DBeaver is a desktop database client. It connects to PostgreSQL so you can inspect tables and run queries.
- The backend queries customer records and retrieves knowledge from that database. No separate vector database or pgvector password is needed.

The repository already uses the `pgvector/pgvector:pg16` Docker image. The first
Alembic migration enables the extension and creates `knowledge_chunks.embedding`
as `vector(1536)`.

## PostgreSQL credentials

Your existing root `.env` supplies these settings:

| Setting | Purpose |
| --- | --- |
| `POSTGRES_DB` | Database name |
| `POSTGRES_USER` | Local database username |
| `POSTGRES_PASSWORD` | Local database password |
| `POSTGRES_PORT` | PostgreSQL port published on your computer |
| `DATABASE_URL` | Backend connection string, using host `db` inside Docker |
| `HOST_DATABASE_URL` | Optional connection string for tools running on your computer, using `localhost` |

For a fresh Docker database, Compose passes the first three values to PostgreSQL
and its startup process creates the database and user. DBeaver does not need to
create them first. The username/password in `DATABASE_URL` must match.

Examples of the two connection-string formats, with placeholders:

```text
DATABASE_URL=postgresql+psycopg://YOUR_USER:YOUR_PASSWORD@db:5432/YOUR_DATABASE
HOST_DATABASE_URL=postgresql+psycopg://YOUR_USER:YOUR_PASSWORD@localhost:YOUR_HOST_PORT/YOUR_DATABASE
```

The backend connects to container port 5432 even if the published host port is
different. Passwords containing URL-reserved characters need URL encoding in
connection strings; DBeaver's password field takes the actual password.

Changing `.env` does not change a password in an already-initialised database
volume. Keep your working credentials or deliberately change the database role
password and matching application settings. Do not delete the volume to fix a
password mismatch if you need its contents.

## Connect with DBeaver

1. Select **New Database Connection**, then **PostgreSQL**.
2. Enter host `localhost` and the port from `POSTGRES_PORT` (normally `5432`).
3. Enter the database, username and password from the matching `POSTGRES_*` values.
4. Click **Test Connection**, then **Finish**. Allow the PostgreSQL JDBC driver download if prompted.
5. Expand **Schemas > public > Tables**. Refresh the connection after migrations.

Use DBeaver's separate connection fields rather than pasting the Python
`postgresql+psycopg` URL into a JDBC URL field.

## Generated dataset

The bundled file is `backend/seed/generated/workforce.json`. Generation is
deterministic with seed 42, has a fixed reference time of 2026-10-12 09:00 in
Asia/Kuala_Lumpur, and requires no model API key. These are fixtures, not live
measurements. Names, addresses, serials, SSIDs and locally administered MACs are
fictional; no equipment/service passwords are included.

| Table | Rows | Contents |
| --- | ---: | --- |
| `customers` | 20 | Fictional households and addresses |
| `services` | 80 | Granite/access, Internet (HSI), voice (VoBB), IPTV |
| `network_devices` | 80 | Dedicated demo access node, ONU, router and laptop per household |
| `topology_edges` | 60 | Fibre, Ethernet and wireless links |
| `wifi_radios` | 40 | Separate 2.4 and 5 GHz radio configurations |
| `wifi_networks` | 40 | SSID/BSSID records linked to radios |
| `device_measurements` | 180 | ONU, wired router and wireless client measurements |
| `wifi_client_measurements` | 60 | Per-client RSSI, SNR, link rate and retry measurements |
| `service_measurements` | 180 | Internet, voice and IPTV operational observations |
| `network_events` | 20 | Fictional customer reports, marked processed |
| `tickets` | 20 | Open work assigned to the demo technician |

The eight scenarios are healthy/recovered service, weak Wi-Fi, interference,
speed-profile mismatch, optical loss, voice registration failure, IPTV multicast
failure and stale telemetry. Three observations per device/service show a
baseline and subsequent conditions. Stale cases have delayed observations.
There are no fabricated successful repair results.

`evaluation_cases` remains in the JSON fixture, outside the imported database
tables. It records expected scenarios/actions for future evaluation. Do not feed
it into the assistant's context as observed customer data.

Service speed profiles use the existing `services.details` JSON field. Equipment
inventory uses `network_devices.details`. Wi-Fi configuration and measurement
history have separate tables. Subscription `status="active"` is distinct from
the timestamped operational status; a subscribed service may be down.

Human-readable ticket numbers, CTT references and the reported complaint are in
the source report's `network_events.payload`. The existing ticket UUID remains
the application's ticket identifier. `assigned_technician_email` in the export
is resolved to `tickets.assigned_technician_id` during import.

The current application already displays assigned synthetic tickets and service
details. Its existing chat does not yet query the new measurement tables, and
its device actions remain simulated. Speed synchronisation and customer-facing
chat are future features; the fixture does not implement them.

## Generate and import

Run from the repository root with Docker Desktop running and your existing
`.env` configured:

```powershell
docker compose up -d db
docker compose build api
docker compose run --rm api alembic upgrade head
docker compose run --rm -e DEMO_SEED_ENABLED=true api python -m app.seed.workforce_data ingest
docker compose run --rm api python -m app.ai.ingestion
docker compose run --rm api python -m app.seed.workforce_data index-knowledge
docker compose up -d api
```

The importer adds records and preserves existing rows, including ticket status
and device settings changed during a demo. Running it again inserts no duplicate
records. A conflicting identity fails and rolls back the import. Existing demo
accounts are preserved; missing operator/technician accounts are created with
the README's demo credentials. This does not call the older strict demo seed,
which requires its original event to remain pending.

The first indexing command indexes the original procedures. The second adds a
separate synthetic troubleshooting document with eight sections. Both fill
missing embeddings and reuse matching model vectors. The local embedding provider
is deterministic for testing and uses 1536 dimensions. Hosted Qwen uses a separate
1024-dimensional column; follow [the Qwen migration guide](qwen-embedding-migration.md)
before switching providers.

To generate another file without Docker or a database:

```powershell
cd backend
python -m app.seed.workforce_data generate --customers 20 --seed 42
```

The output path can be changed with `--output`. When changing the bundled file,
rebuild the API image before importing. A different seed creates a separate
set of records; the same seed preserves existing identities. Customer counts
from 1 to 500 are supported.

## Inspect in DBeaver

These queries only read data:

```sql
SELECT customer_ref, name, address
FROM customers
WHERE customer_ref LIKE 'SYN-%'
ORDER BY customer_ref;

SELECT c.customer_ref, s.service_type,
       s.details ->> 'subscribed_download_mbps' AS subscribed_mbps,
       s.details ->> 'provisioned_download_mbps' AS provisioned_mbps
FROM services s
JOIN customers c ON c.id = s.customer_id
WHERE c.customer_ref LIKE 'SYN-%' AND s.service_type = 'HSI'
ORDER BY c.customer_ref;

SELECT c.customer_ref, r.band_ghz, r.channel, r.channel_width_mhz, w.ssid
FROM wifi_networks w
JOIN wifi_radios r ON r.id = w.radio_id
JOIN network_devices d ON d.id = r.device_id
JOIN customers c ON c.id = d.customer_id
ORDER BY c.customer_ref, r.band_ghz;

SELECT d.device_ref, m.observed_at, m.quality, m.operational_status,
       m.download_mbps, m.optical_rx_dbm, m.los_alarm
FROM device_measurements m
JOIN network_devices d ON d.id = m.device_id
ORDER BY d.device_ref, m.observed_at;

SELECT extname, extversion FROM pg_extension WHERE extname = 'vector';
SELECT id, section, vector_dims(embedding) AS dimensions
FROM knowledge_chunks WHERE embedding IS NOT NULL;
```

## References

- [PostgreSQL Docker image configuration](https://hub.docker.com/_/postgres)
- [pgvector: vectors alongside relational data](https://github.com/pgvector/pgvector)
- [DBeaver connection setup](https://dbeaver.com/docs/dbeaver/Create-Connection/)
