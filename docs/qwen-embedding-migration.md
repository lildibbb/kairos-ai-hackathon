# Qwen embeddings at 1024 dimensions

This changes knowledge embeddings, not the customer database. Customers, services,
devices, readings, account links and tickets are unaffected. Existing knowledge
text and original 1536-dimensional vectors remain in place.

## Storage and model identity

Migration 0005 adds columns to `knowledge_chunks`:

| Column | Purpose |
| --- | --- |
| `embedding` | Existing `vector(1536)`, retained without resizing or truncation |
| `embedding_profile` | Identity of the provider/model for a 1536-dimensional vector |
| `embedding_1024` | New `vector(1024)` for Qwen output |
| `embedding_1024_profile` | Identity of the provider/model for a 1024-dimensional vector |

Column sizes are fixed in the schema, independent of `.env`. Indexing selects a
column using the provider dimension. Retrieval only compares vectors tagged with
the same model profile. Missing Qwen vectors never fall back to old local vectors.
The old column remains available for returning to the local provider.

A hosted profile hashes the gateway URL, model alias, dimensions and query
instruction. It contains no API key. Key rotation does not force re-indexing;
changing the model/gateway/instruction does. Untagged old vectors cannot be assumed
compatible. Local indexing can recompute and compare original local vectors, then
tag verified matches without replacing their values. Unknown legacy vectors are
not silently relabelled or overwritten.

For Qwen, documents are embedded directly, while questions get a retrieval-task
instruction following the [official model card](https://huggingface.co/Qwen/Qwen3-Embedding-0.6B).
The adapter requires the exact vector length, finite numeric values and a nonzero
vector. It never pads or truncates vectors to fit the schema.

## Gateway access

The configured gateway is `https://gigx.nexa-dev.tm.com.my/llm/v1`. Initial checks
failed DNS resolution from both Windows and Docker. Connect the company VPN and
confirm the URL. Windows access alone does not guarantee Docker can resolve the
internal hostname; check VPN/Docker DNS support if needed. Do not guess an IP
address. After VPN connection, the current gateway failed certificate verification
in Windows and Docker. A verified company CA/certificate or a gateway with a trusted
certificate remains the recommended fix.

### Temporary development-only TLS override

For explicitly authorized development tests with synthetic data and a restricted
test key, root `.env` can contain:

```dotenv
APP_ENVIRONMENT=development
MODEL_TLS_VERIFY=false
```

`MODEL_TLS_VERIFY` defaults to `true`; `APP_ENVIRONMENT` defaults to `production`.
Startup/CLI settings reject `false` outside `development`. This setting affects
only hosted embedding and chat clients, not database TLS or other HTTP traffic.
The client logs a warning without credentials. Encryption remains, but the gateway
identity is not verified; a VPN does not remove this impersonation risk. Do not use
real customer data or production credentials while this override is enabled.
Rotate any key exposed in screenshots and keep its replacement only in `.env`.

After the certificate issue is fixed, set `MODEL_TLS_VERIFY=true` and restart the
API with `docker compose up -d api`. Restart is also required when enabling the
override on an already-running API. Docker Compose already passes root `.env` to
the API, so no Compose change is needed.

Keep the full API key in root `.env` as `MODEL_API_KEY`, never in frontend code or
Git. Set `EMBEDDING_MODEL=qwen3-embedding-0.6b`, the alias shown by your gateway.

## Prepare before activation

Run from the repository root. Temporary overrides affect only the one-off command,
not `.env` or the running API:

```powershell
docker compose build api
docker compose run --rm api alembic upgrade head
docker compose run --rm -e EMBEDDING_PROVIDER=hosted -e EMBEDDING_DIMENSIONS=1024 api python -m app.ai.ingestion --probe
```

The probe sends one generic question and performs no database writes. It must
report success at 1024 dimensions before proceeding. Next, regenerate embeddings
from all existing knowledge text, including the workforce troubleshooting document:

```powershell
docker compose run --rm -e EMBEDDING_PROVIDER=hosted -e EMBEDDING_DIMENSIONS=1024 api python -m app.ai.ingestion --embeddings-only
docker compose run --rm -e EMBEDDING_PROVIDER=hosted -e EMBEDDING_DIMENSIONS=1024 api python -m app.ai.ingestion --verify
```

The command commits only when the whole operation succeeds; a failed gateway call
rolls back that run. Repeating a successful run reuses matching model vectors.
Knowledge rows are not duplicated and the other vector column is untouched.
Verification checks every persisted chunk, originally 14 in this local corpus.

Document indexing sends knowledge text, not customer addresses or device records.
Search sends the search question to create its embedding, so use an approved
gateway for that content.

## Activate after verification

Change these two root `.env` settings only after verification succeeds:

```dotenv
EMBEDDING_PROVIDER=hosted
EMBEDDING_DIMENSIONS=1024
```

Keep the correct gateway, key and Qwen model alias. `MODEL_PROVIDER` controls chat
separately and need not change. Restart to reload environment settings:

```powershell
docker compose up -d api
```

Existing document commands still work with the active model for later additions:
`python -m app.ai.ingestion` and `python -m app.seed.workforce_data index-knowledge`.

## Inspect or return to local mode

The local development run on 2026-10-12 successfully probed the gateway, generated
and verified 14 real Qwen vectors at 1024 dimensions using the explicit temporary
TLS override. The original 1536-dimensional vectors were retained unchanged.
Embedding retrieval is configured as hosted; chat remains local. This is not a
production-ready certificate configuration.

Read-only SQL for DBeaver:

```sql
SELECT id, vector_dims(embedding) AS original_dimensions,
       vector_dims(embedding_1024) AS qwen_dimensions,
       embedding_1024_profile
FROM knowledge_chunks ORDER BY id;
```

To return to offline local retrieval, set `EMBEDDING_PROVIDER=local` and
`EMBEDDING_DIMENSIONS=1536`, then verify/tag the original local vectors:

```powershell
docker compose run --rm api python -m app.ai.ingestion --embeddings-only
docker compose run --rm api python -m app.ai.ingestion --verify
docker compose up -d api
```

Do not downgrade the migration simply to change providers: that removes the new
column and its data. This side-by-side transition temporarily uses more storage,
not less. Old vectors can be deliberately archived/removed later after testing.

## Changed files

| File | Purpose |
| --- | --- |
| `backend/migrations/versions/0005_embedding_1024.py` | Additive vector/provenance columns |
| `backend/app/domain/models.py` | Fixed 1536 and 1024 vector definitions |
| `backend/app/config.py` | Allows the two supported sizes |
| `backend/app/ai/embedding_space.py` | Storage selection and vector validation |
| `backend/app/ai/ports.py` | Model identity in provider/search interfaces |
| `backend/app/integrations/embeddings.py` | Qwen query instructions, response validation and safe errors |
| `backend/app/integrations/model_http.py`, `model_provider.py` | Scoped model TLS configuration with secure defaults and warnings |
| `backend/tests/test_model_tls.py` | Development guard, environment parsing and TLS client tests |
| `backend/app/ai/ingestion.py` | Model-aware indexing and probe/verify commands |
| `backend/app/ai/retrieval.py` | Searches matching model/dimension only |
| `backend/app/api/knowledge.py`, `assistant.py`, `tools.py` | Controlled gateway failure responses |
| `backend/tests/test_embedding_1024.py` | Preservation, model isolation and gateway-contract tests |
| `backend/tests/test_ingestion.py`, `test_seed.py` | Existing tests updated for model identity and sizes |
| Existing guides and `README.md` | Links to this migration guide |
