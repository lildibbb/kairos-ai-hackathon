# Customer Agent And Router Action Showcase

## What Was Added

The customer chatbot can now use a model-directed tool loop rather than only a
fixed question sequence. The chat model selects a permitted tool, receives its
observation, and selects another tool or a customer-facing outcome. A separate
hosted response writer then turns approved findings and the recent conversation
into contextual customer prose. Authorized action/ticket/appointment facts stay
in server-rendered receipts; approved templates remain the offline/error fallback.

The gateway uses a validated JSON action protocol over the existing chat
completion API. Native provider function calling is not required or assumed.
The embedding model remains responsible only for knowledge retrieval.

The loop exposes scoped diagnostics, troubleshooting retrieval, verified sales
options, isolated router state, action proposals, confirmed execution, and ticket
creation. It can choose different eligible follow-up questions. Booking remains
in the existing customer slot picker, with database conflict protection; the agent
cannot invent appointment availability or silently select a time for a customer.

## Files

| File | Purpose |
| --- | --- |
| `backend/app/services/customer_agent.py` | Validated model-selected tool loop, observations, six-step default budget, soft 45-second loop budget, and guided fallback. |
| `backend/app/services/customer_router_actions.py` | Fictional-household simulator, ownership checks, expiring confirmation, cancellation, replay protection, and action auditing. No device-management client or hardware commands exist here. |
| `backend/app/services/customer_chat.py` | Connects the agent to conversation history, grounded advice, sales, trouble tickets, action confirmation, and customer improvement feedback. |
| `backend/app/services/customer_response.py` | Writes contextual replies from approved facts, recognizes free-text troubleshooting feedback, rejects unsupported detail/transaction claims, and falls back to approved wording. |
| `backend/app/domain/customer_chat_schemas.py` | Typed public action receipts, bound action confirmation requests, and private agent trace fields. |
| `backend/app/domain/models.py` | Adds isolated action and simulated state models. |
| `backend/migrations/versions/0009_customer_agent_actions.py` | Creates the two new tables without replacing existing data. |
| `backend/app/config.py` | Agent-mode and development/test-only simulation switches. |
| `backend/app/api/customer_portal.py`, `backend/app/integrations/model_provider.py` | Limits customer-agent model HTTP calls to 15 seconds each, supplies a 1024-token response budget, and rejects empty answers; preserves the existing staff provider interface. |
| `backend/app/seed/customer_router.py` | Explicitly stages a fictional VLAN mismatch for a repeatable showcase. |
| `frontend/src/lib/api/customerChat.ts`, `frontend/src/features/portal/CustomerChatPage.tsx`, `frontend/src/styles.css` | Public action parsing, action-ID-bound confirmation, simulation status, improvement choices, and action styling. |
| `frontend/src/lib/api/customerReports.ts`, `frontend/src/features/portal/ReportCheckerPage.tsx` | Staff-only tool trace, planner mode, and simulated before/after action audit. |
| `backend/tests/test_customer_agent.py`, `backend/tests/test_customer_agent_postgres.py`, `frontend/src/features/portal/CustomerChatPage.test.tsx` | Agent selection, scope, confirmation, failure, retry, telemetry isolation, concurrency, and UI tests. |
| `frontend/scripts/customer-agent-smoke.cjs` | Browser verification using existing fictional accounts: cancellation, replay-safe reboot, VLAN restoration, improvement feedback, escalation, admin trace, and desktop layout. |
| `.env` | Enables the agent and isolated router simulator locally; provider credentials are unchanged. |

## Tables

- `customer_router_states`: simulated reboot count and VLAN map for a synthetic
  router. These are not live network readings or provisioning records.
- `customer_router_actions`: action target, customer/user/conversation scope,
  requested operation, confirmation expiry, completion status, and before/after
  simulated state. The model cannot supply arbitrary device IDs or VLAN numbers.
- Existing `customer_chat_turns`: stores selected tools, planner mode, and the
  customer's improvement response alongside the conversation snapshot.
- Existing `audit_events`: records proposal, execution, and cancellation with
  `simulation=true`. No hidden model reasoning is stored.

## Local Configuration

```dotenv
CUSTOMER_CHAT_MODE=agent
CUSTOMER_CHAT_PROVIDER=hosted
CUSTOMER_AGENT_MAX_STEPS=6
CUSTOMER_ROUTER_SIMULATION_ENABLED=true
APP_ENVIRONMENT=development
```

Keep normal `DEMO_SEED_ENABLED=false`. Use a one-off override only when staging
fictional data. Enabling router simulation in production is rejected. Real users,
real households, non-synthetic routers, and ambiguous router targets are denied.
Existing TLS and staff-role protections are not relaxed by agent mode.

The checker distinguishes:

- `agent_hosted`: the hosted model selected validated tools and the outcome.
- `agent_local`: the deterministic offline runner selected tools. This is not
  evidence of autonomous model reasoning.
- `agent_fallback`: invalid, unavailable, repetitive, or budget-exhausted model
  decisions caused a guided fallback.
- `guided`: the previous workflow, selected with `CUSTOMER_CHAT_MODE=guided`.

Keep the company VPN connected for hosted chat and embeddings. An HTTP timeout
also applies to each model request; the soft loop deadline is checked between
tools, not a hard cancellation of an already-running network request.

The checker's existing `Interpretation` value describes symptom extraction. It
is separate from `Agent Execution`, which describes model-directed planning.
For example, local symptom extraction can be used while the hosted model still
successfully selects the tools.

`Reply: hosted` means the separate response writer produced validated prose.
`Reply: fallback` means its output was unavailable or rejected; `static` means
the offline provider is configured. Reply mode is independent of agent planning.
Generated text is saved in `customer_chat_turns.response`; no new tables or
database migration are needed for contextual replies. Retries reuse that text.
Receipt restoration preserves the generated introduction while refreshing the
actual ticket and appointment state.

For example, "I don't think it is working after changing device" now records a
failed check and an attempted device comparison. The next reply acknowledges it
and moves to further investigation rather than repeating the same comparison.
The model can also interpret other ways of reporting failed checks; it cannot
turn that feedback into ticket consent or router-action confirmation.

## Judge Walkthrough

Use the existing fictional customer login at `/portal/sign-in`. Start a new
conversation for each example.

1. Say **Please restart my router**. The agent checks diagnostics and action
   capability, then proposes a restart. No action runs yet.
2. Click **Confirm action**. The isolated reboot count increases once; the chat
   asks whether the service improved. Free-text "yes" is not authorization.
3. Click **It's working now** to finish, or **Still not working** to continue
   toward technician review and the existing appointment picker.
4. In a new conversation, say **Please reconfigure my IPTV VLAN** and confirm.
   The backend restores the fictional approved IPTV profile; the model cannot
   choose the VLAN value.
5. Open `/admin/check` with the existing operator login. Inspect the
   conversation's agent trace and Router Action Audit. A selected execution tool
   alone is not proof of execution; check the succeeded action and its audit.

To demonstrate a visible VLAN change before step 4, explicitly stage a mismatch:

```powershell
docker compose run --rm -e DEMO_SEED_ENABLED=true api python -m app.seed.customer_router --customer-ref SYN-00042-0002 --service IPTV --vlan 601
```

The simulator then restores IPTV `601 -> 600`. These are fictional showcase
values, not verified Unifi provisioning values. The staging command refuses a
pending action and does not reset passwords, telemetry, customer inventory, or
prior action records. Repeated execution without staging can be a no-op restore
because the simulated profile already matches.

## Safety And Limitations

Confirmation is scoped to the latest action and conversation, expires after ten
minutes, and is bound to an action ID. Household locking and request IDs prevent
concurrent retries from executing twice. Repeating an action has a short cooldown.
Reported or recorded optical loss blocks router remediation. Simulated action
completion never proves that a physical connection recovered; customer feedback
is collected separately. Customer responses do not include internal measurements,
raw action state, tool traces, credentials, or staff identities.

The response writer gets approved customer-safe explanations, limited recent
messages, and already-attempted checks, not raw measurements or account identity.
It returns a bounded JSON draft with references to allowed fact IDs. Validation
rejects unknown references, numbers/links/secrets, unsupported transaction claims,
unsafe equipment instructions, obvious certainty/upsell errors, and repeated
device-comparison instructions. This is defense in depth, not a proof that every
possible model sentence is semantically correct. Production still needs a
grounding/language evaluation set and monitoring of rejected and accepted replies.
An empty or invalid response draft gets at most one prose-only repair attempt;
HTTP/network errors immediately use fallback wording. This never reruns tools,
ticket creation, or router execution. Rejected text and provider error details
are not copied into the repair prompt.

The customer interface labels individual router actions as simulations, without
turning the whole support portal into a development banner. Do not present these
actions to judges as commands sent to actual Unifi equipment. Production remote
management, authoritative provisioning profiles, reliable recovery/rollback,
staff approval for VLAN changes, and real post-change monitoring are separate
integration work.

## Verification

The backend regression suite passed 274 tests. Four PostgreSQL-only checks are
skipped in that in-memory run and are executed separately against disposable
schemas. The frontend passed 36 tests and its production build.
All four separate PostgreSQL concurrency checks passed.

The completed browser run verified cancellation, customer-confirmed reboot,
same-request replay, history restoration, IPTV VLAN `601 -> 600`, customer
improvement feedback, ticket escalation, customer denial from the admin API,
and the read-only admin tool/action audit. Every plan in that successful browser
run used `agent_hosted`. Desktop screenshots were checked at 1440x900 and
1280x800 with no horizontal overflow or off-screen composer.

The contextual-response browser check also verified the longer failed-check
message, near-router coverage advice, Malay replies, no raw evidence or response
metadata in the public API, and unchanged generated text after retries/reloads.
These three response cases used `response_mode=hosted`.

Browser screenshots are under the ignored `frontend/.local/` directory. To rerun
the showcase test, stage the fictional mismatch first and provide your Playwright
module directory if Playwright is not installed locally:

```powershell
node frontend/scripts/customer-agent-smoke.cjs "C:/Users/sjiaj/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright" "http://127.0.0.1:5173" msedge
```

Only existing fictional customer/operator accounts are used. Test credentials
stay in memory; the test does not reset passwords or operate physical equipment.

To verify contextual responses without staging a router change:

```powershell
node frontend/scripts/customer-response-smoke.cjs "C:/Users/sjiaj/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright" "http://127.0.0.1:5173" msedge
```

This strict hosted smoke check requires generated replies for each language/case.
The company gateway has intermittently returned unusable responses during repeat
runs, which can make this check fail even though the workflow safely returns
approved fallback text. Check `Reply` and private data warnings in the checker;
a fallback must not be presented as a successful hosted generation.
