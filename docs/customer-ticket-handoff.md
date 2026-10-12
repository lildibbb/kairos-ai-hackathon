# Customer Ticket Handoff

Customer chat escalation writes a `customer_trouble_tickets` report. Once it has
an assigned technician and a customer device, the same transaction creates a
processed customer-origin `network_events` entry and a linked `tickets` row.
`customer_trouble_tickets.ticket_id` identifies that staff ticket.

The technician's `/work` queue uses `/tickets/mine`, which returns only that
technician's assignments. Customer reports show their customer-visible `TT-...`
reference in the queue and can be found using it. The internal `INC-...` reference
is retained. The queue refreshes every 30 seconds while visible, on focus, and
through its refresh button. Background errors keep the previous list visible.

Operators' `/operations` screen lists unprocessed network events; customer reports
are already processed and therefore do not enter that intake feed. Queued reports
remain unassigned until a technician is selected, for example through an eligible
appointment booking. Chat retries and backfills do not create duplicate reports
or staff tickets. Customer reports without an attachable device remain unlinked.

## Existing Reports

Apply the current Alembic migrations before running the repair:

```bash
alembic upgrade head
python -m app.backfill_customer_reports
python -m app.backfill_customer_reports --apply
```

The first backfill prints counts and rolls back its transaction. `--apply` commits
the links. Only assigned reports with no staff link are considered. The repair
uses the same household lock as chat and retains the original report reference,
customer, technician, and conversation. Repeating it creates no additional rows.

## Older Database Layout

The local database previously used revision `0009_customer_agent_actions`, with
separate 1536- and 1024-dimensional embedding columns. That revision is from a
different migration history, so a normal upgrade cannot resolve it.

Back up the database and validate this upgrade on a restored copy first:

```bash
python -m app.upgrade_legacy_customer_database
python -m app.upgrade_legacy_customer_database --apply
python -m app.backfill_customer_reports --apply
```

This compatibility tool accepts only that older revision. It adds missing tables,
columns, and constraints, validates the resulting schema and appointment overlap
constraint, then records the current migration head in the same transaction.
Unsupported changes fail and roll back. The command without `--apply` also rolls
back after validation.

It preserves the original vectors by renaming the 1536-dimensional column to
`embedding_1536_legacy` and the existing 1024-dimensional column to `embedding`.
It does not resize, clear, or regenerate embeddings. Existing embedding provenance
columns and indexes are retained. This tool is not a migration adapter for the
separate merged project's `0007_customer_portal_merge` database.

## Local Runtime

Run the API and frontend from this checkout. Reusing a container built from
another project folder can leave a correctly saved customer report invisible in
the staff queue. Both portals must proxy their APIs to the same intended backend.

The verified older database contained 20 customers, 80 services, 80 devices,
20 staff tickets, four customer reports, and 14 knowledge chunks. Its repaired
copy contained 24 staff tickets, with all four reports linked; original record
counts and both embedding fingerprints were preserved. A second backfill linked
zero additional reports.
