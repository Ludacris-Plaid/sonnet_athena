# RealtyAI

Backend for **Athena**, an AI operating partner for realtors: unified inbox
(email/SMS) with draft replies, a trust ladder that grants Athena more
autonomy over time, property analysis/comps, neighborhood scoring, semantic
memory, and a multi-tenant SaaS shell with invite-code gated signup.

## What's real vs. stubbed in this scaffold

**Real / working:**
- FastAPI app, all routes, Postgres models, JWT auth, invite codes
- DeepSeek LLM integration (`app/services/llm_service.py`) — real API calls
- Local embedding + FAISS vector memory (`app/memory/vector_store.py`)
- Trust ladder scoring logic (`app/services/trust_service.py`)
- Demo listings data generator so the whole pipeline runs end-to-end today

**Stubbed, by design, pending your credentials:**
- `app/scrapers/reso_client.py` — real MLS/RESO Web API integration. You need
  an IDX/VOW data license from your local MLS board. Do **not** replace this
  with a Zillow scraper; Zillow's ToS prohibits scraping and it exposes every
  customer of this platform to legal risk.
- Gmail/Twilio webhook receivers — `POST /inbox/receive` simulates what those
  webhooks will call once wired up.
- Stripe billing — `Organization.tokens_used_this_period` is tracked but not
  yet wired to Stripe metered billing.

## Quick start

```bash
git clone <your-repo>
cd realtyai
chmod +x init.sh
./init.sh
```

Then:
```bash
source venv/bin/activate
uvicorn app.main:app --reload
```

Visit `http://localhost:8000/docs` for interactive API docs.

Create your first admin (platform owner) user:
```bash
python scripts/create_admin.py you@company.com "Your Name" "a-strong-password"
```

## CLI

```bash
python -m cli.main seed-demo-org
python -m cli.main run-ingestion --city Edmonton --state AB --org-id <uuid-from-above>
python -m cli.main analyze-property <property-id>
```

## Hermes Agent — the "central brain" delegation layer

Researched before building, since "Hermes agent" needed verification: it's
[Hermes Agent](https://github.com/NousResearch/hermes-agent) by Nous
Research, an MIT-licensed, model-agnostic autonomous agent framework
(launched Feb 2026), with persistent memory, tool use, and sandboxed
execution. Important architectural fact from their own docs, which shaped
how this is wired in: Hermes' API Server mode is **"an agent runtime, not a
pure LLM proxy"** — every request spins up a full tool-using agent
server-side and can take minutes, not milliseconds.

That means Hermes is **not** a drop-in replacement for DeepSeek across the
platform — using it for every chat/voice turn would make the product feel
broken (voice specifically cannot tolerate multi-minute latency; the
compliance gate there already assumes near-real-time). Instead:

- **DeepSeek (`llm_service.py`) stays the fast path** for chat, voice,
  content generation, compliance screening, everything latency-sensitive —
  unchanged.
- **Hermes (`app/services/hermes_agent_service.py`) is the delegated deep-work
  path** — wired into the chat orchestrator as a new `deep_research` intent
  (`app/prompts/chat_router.py`) and a dedicated `POST /agent/delegate`
  endpoint for an explicit "Go Deep" action, separate from normal chat so it
  gets its own loading state in the UI (`frontend/app/dashboard.html`).

**Setup:** Hermes runs as its own separate service — it has no published
PyPI wheel, so it can't be added to `requirements.txt`. Install it on its
own host per Nous Research's docs, enable `API_SERVER_ENABLED` /
`API_SERVER_KEY` in Hermes' own config, then point `HERMES_API_BASE_URL` /
`HERMES_API_KEY` at it in `.env`. Full steps in the docstring at the top of
`hermes_agent_service.py`. Until configured, `deep_research` requests get a
clear "not connected yet" message instead of failing silently.

## Meridian-inspired additions (with an honest caveat)

You linked `github.com/codejunkie99/meridian-company-os` — it 404'd on
direct fetch when this was built (likely renamed, made private, or removed
since being search-indexed), so **nothing here is a port of its actual
code**, which was never seen. What's built instead is a fresh
implementation of the general pattern the indexed description conveyed (a
command-driven operator chat surface with a pending-approvals view):

- **`app/services/command_parser_service.py`** — deterministic parsing of
  structured shorthand ("assign client X to Y", "budget report", "sync crm
  followupboss") ahead of the LLM intent classifier in
  `orchestrator_service.py`, so routine ops are fast/free/reliable instead
  of round-tripping through an LLM call every time. Falls through to normal
  LLM routing for anything that doesn't match. Tested against both matching
  and non-matching input before shipping.
- **`app/services/approvals_service.py`** — aggregates everything currently
  waiting on a human (draft replies, unread compliance flags, failed CRM
  syncs) into one list, `GET /agent/approvals`, surfaced as a banner right
  on the dashboard. Deliberately built as a read-only view over existing
  tables rather than a new parallel "approval" model, since each item type
  already has its own real state.

If you get access to the actual Meridian repo later and want something
specific ported for real, that's a very different (and better-grounded)
task than this.

## Admin Dashboard — full CRUD, financial stats, and the admin's own Athena

**Separate login** (`frontend/admin/login.html`) — distinct URL, distinct
dark "control room" styling from the customer-facing app, and critically:
after Supabase auth succeeds, it calls `GET /admin/me` and signs the user
back out immediately if that fails. A valid session alone never grants
admin UI access — `is_admin` is checked server-side on every load via
`admin-nav.js`, not assumed client-side.

**User CRUD** (`app/services/admin_service.py`, `frontend/admin/users.html`)
— view/search/filter every user across every org, edit name/admin-flag,
and three real status states instead of one boolean: `active` →
`suspended` (temporary, reversible) → `banned` ("boot," most severe). Every
status change requires a reason (recorded, not just logged silently), and
you can't suspend/ban/demote yourself — a real guard against locking
yourself out.

**Financial/usage stats** (`GET /admin/stats/*`, Chart.js graphs on
`dashboard.html`) — estimated MRR (from `PLAN_PRICING_USD`, adjust to your
real Stripe prices), estimated DeepSeek token cost and gross margin (from
`DEEPSEEK_COST_PER_1M_TOKENS_USD`, a configurable placeholder — update it
to your actual negotiated rate), signup trend, message volume trend, user
status breakdown, revenue by plan tier. All real queries against real
data, not mocked.

**The admin's own Athena — "god mode with guardrails," and how the
guardrails actually work** (`app/services/admin_agent_service.py`,
`frontend/admin/athena.html`): this is the part worth understanding before
extending it. The model has NO raw database/SQL access — every capability
is a specific, individually-validated Python function
(`app/services/admin_service.py`). More importantly, **the confirmation
flow is server-enforced, not a prompt instruction the model could skip**:
the first call to a destructive tool (suspend, ban, plan change,
deactivate) returns a `confirmation_token` and does NOT act; the model
must call the same tool again with that exact token to execute. A model
(or a prompt-injected instruction) cannot bypass this by just deciding to
"confirm" on the first pass, since it has no way to know the token in
advance — it only exists after the server has already decided to ask. This
was tested with 5 explicit adversarial cases during development
(fabricated token, replayed token, expired token — all correctly
rejected). Known limitation: pending confirmations are held in-memory
(`_PENDING_CONFIRMATIONS`), fine for one process, needs Redis/DB if you
scale to multiple API instances.

**Audit log** (`app/models/admin_audit.py`, `frontend/admin/audit-log.html`)
— every mutating admin action, whether from a UI button or the agent,
writes here through the same `admin_service.log_admin_action()` call. One
code path, so there's no way for an admin action to happen without being
logged.

## CRM Integrations — bringing in a realtor's existing system

Researched before building this, because the real estate CRM market is
genuinely fragmented: **most brokerage-bundled CRMs (kvCORE/BoldTrail,
BoomTown, Sierra Interactive) don't expose a usable public API at all** —
they're sold as closed ecosystems. The CRMs that *do* have real, documented
APIs tend to be the portable ones agents pay for themselves so their
contacts travel if they switch brokerages: **Follow Up Boss** and
**HubSpot** are the two built here for real.

**Architecture** (`app/crm_connectors/`) — an adapter pattern, same shape as
the `ListingsSource` abstraction already in the codebase, so the rest of the
system never needs to know which CRM it's talking to:
- `base.py` — the `CRMConnector` interface (`test_connection`,
  `list_contacts`, `create_or_update_contact`, `parse_webhook_event`)
- `followupboss.py` — real, HTTP Basic auth with an API key, `/v1/people` +
  `/v1/events` (new leads go through `/events` per FUB's own documented
  best practice, so the account's automations actually fire), real webhook
  parsing (`peopleCreated`/`peopleUpdated`)
- `hubspot.py` — real, Private App Bearer token (not OAuth — OAuth is only
  needed for a public Marketplace app serving many accounts, which this
  doesn't need), `/crm/v3/objects/contacts`
- `csv_connector.py` — the honest fallback for everyone else. Not a live
  sync, explicitly labeled as one-time. Tested against realistic export
  data (varied column naming, blank rows) before shipping.

**Sync** (`app/services/crm_sync_service.py`) — matches records by
`(external_provider, external_id)` stored on `Client`, never by name/email
alone, so two different people with a common name don't silently merge.
Supports import-only, export-only, or two-way, per connection.

**Credentials are encrypted at rest**
(`app/services/crm_credential_service.py`, Fernet, key derived from
`SECRET_KEY`) — but read the docstring in that file. This is a floor, not a
ceiling: for production handling real customer CRM credentials, use an
actual secrets manager (Supabase Vault, AWS Secrets Manager) instead of
relying on app-level encryption alone.

**Webhooks** (`POST /crm/webhook/{connection_id}/{webhook_secret}`) — the
per-connection secret in the URL is the base verification layer; providers
that support HMAC signatures get a second check via
`verify_webhook_signature()`. Follow Up Boss webhooks work with a Private
App-equivalent setup; HubSpot webhooks require a public Marketplace app
(not available to Private App tokens) — noted directly in
`hubspot.py`'s docstring, since it's a real limitation, not an oversight.

**Frontend:** `frontend/app/crm-integrations.html` — connect a provider,
trigger manual sync, see sync history, or drop in a CSV.

## Compliance flags now alert, not just log

Closes the gap flagged earlier: a compliance-flagged message used to just
sit on the `Message` row with nobody notified. Now it raises a real
`AlertEvent` (`app/services/compliance_alert_service.py`), wired into all
three places a message can go out flagged:

- `voice_conversation_service.handle_voice_turn` (in-app voice)
- `routes_voice_telephony.handle_speech` (real phone calls)
- `inbox_service.send_reply` (email/SMS)

Modeled as an always-on **system alert rule**
(`AlertRuleType.COMPLIANCE_FLAG`, auto-provisioned per user on first use)
rather than a separate notification path — this means the existing
`GET /alerts/events`, unread counts, and any future delivery channel
(SMS/push/daily briefing) all pick up compliance flags for free, with no
compliance-specific code anywhere except the one place that raises the
event. Voice flags are marked `severity="critical"` (no human saw it before
it happened); email/SMS flags are `"warning"` (a human already chose to
send it anyway) — same distinction the compliance gate itself draws between
blocking voice vs. informing email/SMS.

**New:** `frontend/app/alerts.html` — this didn't have a frontend page
before now. Filterable (All / Unread / Compliance), with a live unread-count
badge on the sidebar nav item (`GET /alerts/events/unread-count`, a
lightweight endpoint that doesn't fetch the full event list just for a
number).

**Not built:** actual push/SMS delivery when an alert fires — it's real-time
in the sense that the event exists immediately and the badge updates on
next page load, but nobody's phone buzzes yet. That's the natural next step
if in-app-only isn't fast enough for how you want to use this.

**On purchase agreements and listing agreements specifically:** these
document types don't exist here on purpose, even though they were
explicitly requested. Both are contracts that, in most US states and
Canadian provinces, must be on a specific state/board-mandated form (Texas
requires TREC-promulgated forms by regulation; Ontario requires OREA forms;
California uses CAR forms) — an AI-generated version isn't just "needs a
lawyer to check it," it may not be a form the licensee is legally permitted
to use at all. What's built instead: `listing_agreement_prep` and
`purchase_offer_prep`, deal-points *worksheets* that capture negotiated
terms in plain English for handing to a broker/TC who drafts the actual
document on the correct form. The prompt (`DEAL_POINTS_CAVEAT` in
`document_prompts.py`) explicitly forbids signature lines or binding
"agrees to" language — if you edit that prompt, keep that constraint, since
it's the entire reason this is safe to include and a full contract type
wouldn't be.

## Content Studio & Documents

**Content Studio** (`app/services/content_generation_service.py`,
`frontend/app/content-studio.html`) — pick a property, pick one or more
content types (MLS description, Instagram caption, Facebook post, "Just
Listed" email, open house flyer copy, price drop announcement, virtual tour
script), generate all of them at once, grounded strictly in that property's
actual data (the prompt explicitly forbids inventing facts). Every piece is
auto-screened with the fast keyword compliance check before being returned —
not optional here, since marketing copy is the highest-risk surface for fair
housing issues in the whole platform.

**Documents** (`app/services/document_service.py`, `app/models/document.py`,
`frontend/app/documents.html`) — import (PDF/DOCX/TXT/MD, text extracted via
`document_extraction_service.py`) or generate from scratch, get a full
LLM-backed compliance score (the deeper two-pass review, not just the fast
keyword scan — documents warrant it), and one-click "Auto-rework" that
rewrites the document to resolve every flagged issue while preserving intent
and any unflagged facts.

**Deliberate scope limit, worth preserving as you extend this:**
`DocumentType` includes marketing materials, guides, checklists, and
disclosure *drafts* — never purchase agreements, listing agreements, or
other binding contracts. Binding real estate contracts need
jurisdiction-specific, board-approved standard forms and a lawyer's review;
an AI-generated "contract" presented as ready to sign is a liability, not a
convenience. The `disclosure_draft` type is explicitly prompted to open with
a bold notice that it's a non-binding starting point requiring legal review
— don't remove that when customizing the prompt.

Storage for uploaded files is pluggable local/Supabase, same pattern as
voice (`app/services/file_storage_service.py`, kept separate from
`voice_service.py` to avoid touching that already-verified path).

**One real gap:** the Documents page doesn't yet support saving free-text
edits made directly in the textarea — the textarea is read-only, and content
changes flow through "Auto-rework" (an LLM rewrite pass) rather than a
direct save endpoint. Adding `PATCH /documents/{id}` for direct edits is the
natural next step if hand-editing turns out to be a common workflow.

## Compliance is now wired in, not standalone

Three enforcement points, each with a different strictness level matched to
how much human review already exists at that point:

**Listings** (`property_service.ingest_listings`) — every listing
description gets a fast, no-LLM keyword scan automatically at ingest time.
Results land on `Property.compliance_risk`/`compliance_flags` and show as a
badge in `frontend/app/properties.html`. This is the cheap first pass only —
`POST /properties/{id}/compliance-check` runs the full LLM-backed review on
demand for a specific listing before you publish it externally.

**Inbox drafts** (`inbox_service.generate_drafts` / `send_reply`) —
informational only, since a human already reviews and chooses which draft
to send. Flagged drafts show an inline warning in `frontend/app/inbox.html`;
the check runs again at send time in case the draft was hand-edited into
something risky.

**Voice — a hard gate, not a warning** (`voice_conversation_service.py`):
voice replies send autonomously with no human approval step in the loop, so
this is the one place compliance checking blocks rather than informs. A
high-severity flag replaces the reply with a generic deflection
(`COMPLIANCE_FALLBACK_REPLY`) before it's ever synthesized to audio — the
LLM's original (flagged) text is never spoken, but the flag is still
recorded on the `Message` row for the agent to review afterward. This
applies to both in-app voice and real phone calls (Twilio), since both
route through the same `generate_spoken_reply()`.

## Compliance — US + Canada (read this before selling it as a feature)

**Important framing note:** this is a compliance-**assistance** layer, not
a compliance guarantee. Don't market it as "totally legally compliant" —
real estate law is jurisdiction-specific and changes constantly. The AML
reference data in this system covers a US federal rule (FinCEN's
Residential Real Estate Rule) that was vacated by a federal court weeks
after taking effect and is now under appeal — that's a live example of why
static "compliance" claims don't hold up. Sell it as "catches obvious
issues fast and points you to what to verify," which is genuinely valuable
and honest.

**What's built** (`app/services/compliance_service.py`,
`app/api/routes_compliance.py`, `frontend/app/compliance.html`):
- **Fair housing screening** — two-pass: a deterministic keyword scanner
  (`app/services/compliance_data.py`, tested for both true positives and
  false-positive avoidance) plus an LLM contextual review that sees the
  keyword hits and can catch subtler phrasing or correct false positives.
  Covers US federal Fair Housing Act classes and commonly-protected Canadian
  provincial human rights grounds.
- **Disclosure reference** — general, non-exhaustive pointers for several
  US states and Canadian provinces. Illustrative starting points, not a
  substitute for checking current local requirements.
- **AML overview** — FINTRAC obligations for Canada (active, enforced) and
  the contested FinCEN rule for the US (explicitly flagged as contested).

**Compliance MCP Server** (`mcp_server/`) — the same logic, packaged two
ways since you specifically wanted this usable with DeepSeek:
1. **`server.py`** — a real MCP server (stdio transport) for Claude
   Desktop/Code, using the `mcp` Python SDK.
2. **`deepseek_bridge.py`** — since DeepSeek doesn't speak MCP but its API
   is OpenAI-compatible tool-calling, this exposes the identical four tools
   as OpenAI-style function schemas, with a working dispatch loop
   (`chat_with_tools()`) you can run standalone or import into
   `orchestrator_service.py` to give the in-app chat/voice assistant direct
   tool access mid-conversation.

Both are self-contained (`mcp_server/compliance_logic.py` +
`compliance_data.py` don't import from the main `app/` package) so the
compliance server can be deployed independently. See `mcp_server/README.md`
for setup.

## Supabase backend — what changed

**Database:** `DATABASE_URL` now points at Supabase's Postgres connection
string instead of local Postgres. Every SQLAlchemy model and service is
unchanged — Postgres is Postgres.

**Auth — the real change:** Supabase Auth now owns signup/login/passwords
entirely, running client-side via `supabase-js`
(`frontend/shared/supabase-client.js`). This backend never sees a password;
`app/core/supabase_auth.py` only *verifies* the JWT Supabase already issued
(via JWKS by default — no shared secret to manage — with a legacy HS256
fallback if your project still uses one). `app/models/org.py`'s `User` is
now a lighter profile row: `id` is the same UUID as Supabase's
`auth.users.id`, no password field. `POST /auth/complete-signup` is the one
backend auth call left — it redeems the invite code and creates the
org/profile right after a Supabase account exists (`app/api/routes_auth.py`).

**Bootstrap:** `scripts/create_admin.py` now creates the Supabase auth user
too (via the service-role admin API), not just the local profile row.

**RLS:** `scripts/supabase_rls.sql` — read the comment at the top of that
file before assuming it does anything. As long as your FastAPI backend
connects with the standard Supabase connection string, these policies
don't restrict *its* queries (RLS doesn't apply to the role connecting as
table owner) — your existing `org_id` filtering in every service is still
the real enforcement. RLS becomes load-bearing once the frontend queries
Supabase directly for something (e.g. Realtime subscriptions on
`messages`/`alert_events` for live inbox/alert updates without polling —
a natural next feature once you're on Supabase).

**Storage:** voice audio caching (`app/services/voice_service.py`) is now
pluggable — `VOICE_STORAGE_BACKEND=local` (default, disk) or `=supabase`
(Supabase Storage, needed once you run more than one API instance, since
local disk isn't shared across them).

**Setup:** `.env` needs `SUPABASE_URL`, `SUPABASE_ANON_KEY`,
`SUPABASE_SERVICE_ROLE_KEY` (backend-only secret, never send to the
frontend), and each frontend page's `<head>` needs
`window.SUPABASE_URL`/`window.SUPABASE_ANON_KEY` set (search for
`YOUR_PROJECT.supabase.co` across `frontend/` — every page has a `// TODO`
marking where to fill these in).

## Voice — Athena as a spoken presence

Two ways to talk to Athena, both landing in the same conversation history
and memory as email/SMS/chat:

**In-app voice** (`frontend/app/voice.html`, `POST /voice/converse`) — tap
the mic, talk, Athena replies out loud. Records via `MediaRecorder` in the
browser, posts the audio to the backend, gets back a transcript + reply text
+ synthesized audio to play. Every turn is logged as a `Message` with
`channel=voice`, so it feeds the same memory recall as everything else —
this is what makes "Athena remembers what you told her on a call" actually
true rather than a gimmick.

**Phone calls** (`app/api/routes_voice_telephony.py`) — a real Twilio Voice
integration. Point a Twilio number's webhook at
`POST /voice/telephony/incoming-call` and clients can call and have an
actual spoken conversation. Uses Twilio's own speech recognition
(`<Gather input="speech">`) rather than streaming raw audio ourselves —
simpler, lower latency, and what Twilio Voice is built for. One clearly
marked TODO in that file: routing an inbound call to the right org/user is
stubbed to "first admin user" until you provision per-org Twilio numbers or
build an IVR selector.

**Providers** (`app/services/voice_service.py`) — pluggable, same pattern as
`llm_service.py`. STT defaults to OpenAI Whisper; TTS defaults to OpenAI's
TTS API but ElevenLabs is a drop-in swap (`TTS_PROVIDER=elevenlabs`) and
generally sounds warmer/less robotic, which matters for the "friend" framing
specifically. DeepSeek doesn't offer voice endpoints, so this is the one
place in the platform that intentionally uses a different vendor — contained
entirely to this module.

**Persona** (`app/prompts/voice_persona.py`) — spoken replies are short,
markdown-free, conversational, and explicitly scoped: warm and personable,
never romantic, never a therapist substitute. Athena is a colleague who's
very good at real estate admin, not a companion app — worth keeping that
line intact as you iterate on the persona.

**Setup:** set `STT_PROVIDER` / `TTS_PROVIDER` and the matching API key
(`OPENAI_API_KEY`, or `ELEVENLABS_API_KEY` + `ELEVENLABS_VOICE_ID`) in `.env`.
For phone calls, also set the `TWILIO_*` vars and `PUBLIC_BASE_URL` (must be
a real, internet-reachable URL — use `ngrok` in dev).

## What's new: the differentiators

Beyond the core inbox/CRM/CMA loop, this adds five features that turn Athena
from "a nice assistant" into something with a real data moat:

**Chat orchestrator** (`app/services/orchestrator_service.py`, `POST /chat`)
— classifies intent (client lookup, opportunities, CMA, negotiation, etc.)
and routes to the right existing service. Deliberately a plain dispatch
table, not a black-box agent chain, so it's easy to debug and extend — the
seam is clearly marked if you want to swap in CrewAI or LangGraph later.

**Opportunity Engine** (`app/services/opportunity_service.py`,
`GET /opportunities?city=`) — scores every active listing 0–100 on
price-per-sqft vs. peers, days-on-market pressure, and *real* price cuts
(tracked via the new `PriceHistory` table, populated by upsert-aware
ingestion). No owner-equity or OSINT signals — same inputs any realtor
already uses for a CMA, just run across every listing automatically.

**Buyer-Matching engine** (`app/services/matching_service.py`,
`GET /matching/clients/{id}/properties`, `GET /matching/properties/{id}/clients`)
— bidirectional matching on stored client criteria (budget, city). Answers
both "what should I show this client" and "who should I tell about this
new listing."

**Portfolio/Investment Simulator** (`app/services/portfolio_simulator.py`,
`POST /portfolio/simulate`) — real amortization math (cap rate,
cash-on-cash, multi-year cash flow + equity projection), computed
deterministically in Python, not hallucinated by the LLM. Verified against
hand-checked numbers during build.

**Real-Time Alerts** (`app/models/alert.py`, `app/services/alert_service.py`,
`/alerts/rules`, `/alerts/events`) — rules (price drop %, long days-on-market,
new listing matches a client) evaluate automatically every time you ingest
listings, and log events you can surface as notifications.

**Negotiation Assistant** (`app/services/negotiation_service.py`,
`POST /negotiation/{property_id}`) — suggests an opening offer + one
negotiation lever, grounded in comps and real price-drop history, with an
explicit confidence level based on data availability. Never speculates
about the seller's personal situation.

## Frontend

Vanilla HTML/CSS/JS, no build step — deliberately, so it's easy to serve as
static files behind any reverse proxy and easy for a non-frontend tool to
edit further.

```
frontend/
  landing/index.html     marketing site, pricing tiers, demo request form
  app/login.html         login
  app/signup.html        invite-code gated signup
  app/dashboard.html     "Chat with Athena" — the main screen from your screenshots
  app/inbox.html         unified inbox, wired to POST /inbox/receive and /inbox/{id}/reply
  app/trust.html         trust ladder visualization per action type
  app/properties.html    listings + one-click CMA
  admin/dashboard.html   platform admin: org usage/margin, invite code generator
  shared/                tokens.css (design system), api.js (fetch client), app-shell.css
```

**Local dev:** serve the `frontend/` directory with any static server, e.g.
`npx serve frontend` or `python -m http.server` from inside `frontend/`, then
set `window.REALTYAI_API_BASE` (in each page's `<head>`, before `api.js`
loads) to wherever `uvicorn` is running — defaults to `http://localhost:8000`.

**Production layout on `realty.indicationsmedia.com`:** route `/` to
`landing/index.html`, `/app/*` to the `app/` directory, `/admin/*` to
`admin/`, and `/api/*` (or a separate `api.realty.indicationsmedia.com`
subdomain) to the FastAPI service. Update `REALTYAI_API_BASE` accordingly.

**Not yet built:**
- `dashboard.html`'s chat box calls a placeholder `sendToAthena()` — there's
  no general-purpose `/chat` endpoint in the API yet. The backend already has
  the pieces (analysis_service, property_service, memory_service); what's
  missing is an orchestration layer that classifies intent and routes to the
  right one. That's the natural next backend addition — a `POST /chat` route,
  ideally backed by CrewAI or LangGraph for multi-step reasoning.
- The demo-request form on the landing page doesn't post anywhere yet — wire
  it to an email service or a simple `/leads` endpoint.
- No mobile nav collapse on the app shell sidebar yet.

## Core concepts

- **Trust ladder** (`app/models/trust.py`, `app/services/trust_service.py`):
  every user starts at `draft_only` for every action type. Sending a draft
  unedited nudges the score up; edits nudge it up slightly; rejections drop
  it sharply. Crossing configurable thresholds (`.env`) unlocks
  `limited_autonomy` then `full_autonomy`, per action type, per user.

- **Unified inbox** (`app/models/message.py`, `app/services/inbox_service.py`):
  every channel normalizes into one `Message` table. `POST /inbox/receive`
  generates 4 tone-varied drafts automatically and reports whether Athena is
  currently allowed to send that action type autonomously.

- **Memory** (`app/memory/vector_store.py`, `app/services/memory_service.py`):
  FAISS-backed semantic store with the same `add`/`search` shape as mem0, so
  it's a drop-in swap for the real `mem0` SDK later.

- **Multi-tenancy & billing** (`app/models/org.py`): every row scopes to
  `org_id`. Invite codes gate signup and set the initial plan tier
  (light/medium/heavy). Meter DeepSeek `total_tokens` from every
  `LLMResponse` against `Organization.tokens_used_this_period` for billing.
