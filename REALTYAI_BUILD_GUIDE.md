# RealtyAI / Athena — Complete Project Specification & Build Guide

**Purpose of this document:** this is a complete technical handoff for an AI coding
agent (or a human developer) picking up this project to finish deployment,
debug issues, and continue development. It documents what the system is,
why it's built the way it is, every file's purpose, every API endpoint,
every environment variable, known bugs already fixed, known gaps still
open, and a step-by-step guide to standing it up from zero and diagnosing
problems when something breaks.

Read this whole document before making changes. Architectural decisions in
this codebase are frequently deliberate trade-offs with reasons documented
in code comments — several "obvious improvements" (e.g. "just use Zillow
scraping," "let voice replies send without a compliance check," "generate
purchase agreements from scratch") were considered and rejected for
specific legal/safety/reliability reasons explained inline. Read the
docstring/comment above a piece of code before "fixing" it.

---

## 1. What this project is

RealtyAI is a SaaS platform for licensed real estate agents, built around
"Athena," an AI assistant that:

- Reads and drafts replies across email, SMS, and voice (unified inbox)
- Runs comparative market analysis (CMAs) and scores investment opportunities
- Generates marketing content and business documents
- Screens everything it produces for US/Canada fair housing compliance
- Earns increasing autonomy over time via a "trust ladder" (starts
  draft-only, graduates to sending on its own as it proves reliable)
- Syncs with a realtor's existing CRM instead of replacing it
- Can delegate genuinely complex research tasks to a separate agent runtime
  (Hermes Agent)

**Business model:** three-tier subscription SaaS (Light/Medium/Heavy),
margin comes from the spread between subscription price and the DeepSeek
API token cost of running the AI features. Multi-tenant: every table is
scoped by `org_id`.

**Tech stack:** FastAPI (Python 3.11+) + PostgreSQL (via Supabase) +
SQLAlchemy 2.0 + vanilla HTML/CSS/JS frontend (no build step, no framework)
+ DeepSeek as the primary LLM + Supabase Auth for authentication.

---

## 2. Architecture philosophy (read this before changing patterns)

A few decisions repeat throughout the codebase. Understanding them will
help you extend it consistently instead of fighting the existing patterns:

### 2.1 Adapter pattern for anything with multiple real-world providers
Listings data (`app/scrapers/`), CRMs (`app/crm_connectors/`), voice
STT/TTS (`app/services/voice_service.py`) all use the same shape: an
abstract base class + a factory function that picks the right concrete
implementation from config. **Follow this pattern** if you add a new
external integration — don't hardcode a single provider into business
logic.

### 2.2 Fast path vs. deep path, never mixed
DeepSeek (`app/services/llm_service.py`) handles everything
latency-sensitive: chat replies, voice turns, content generation,
compliance screening. Hermes Agent (`app/services/hermes_agent_service.py`)
handles explicitly-delegated deep research (its API spins up a full
tool-using agent *per request* and can take minutes — using it for a chat
reply would make the product feel broken). **Never route a fast-path
interaction through Hermes.** If you're tempted to make Athena "smarter" by
routing more things through Hermes, don't — add a better prompt or a new
DeepSeek-backed service function instead.

### 2.3 Compliance enforcement strictness matches how much human review exists
This is the most important safety-relevant pattern in the codebase and it
is intentional, not inconsistent:
- **Listings** (ingest time): fast keyword-only scan, informational, stored
  on the property.
- **Inbox drafts**: informational warning, human chooses what to send.
- **Voice**: a **hard gate** — a flagged reply is replaced with a generic
  deflection before text-to-speech ever runs, because voice sends
  autonomously with zero human review in the loop.

If you add a new autonomous-send feature (anything that leaves the system
without a human clicking "send"), it needs the hard-gate treatment, not the
informational treatment. Copy the pattern in
`app/services/voice_conversation_service.py`'s `generate_spoken_reply()`.

### 2.4 Deliberately excluded features (do not re-add without re-reading why)
- **No Zillow/MLS scraping.** `app/scrapers/demo_source.py` generates
  synthetic data; `app/scrapers/reso_client.py` is a stub for a *licensed*
  MLS/RESO Web API feed. Scraping Zillow violates their ToS and creates
  legal exposure for every customer of this SaaS. If asked to "just scrape
  Zillow," don't — point to getting a real RESO/IDX license instead.
- **No AI-generated purchase agreements or listing agreements.** See
  `app/prompts/document_prompts.py`'s module docstring. These are binding
  contracts that in most US states/Canadian provinces must be on a
  specific mandated form; an AI-drafted version is a liability, not a
  convenience, and drafting binding legal terms for someone else can edge
  into unauthorized practice of law. `DocumentType` only includes
  deal-points *worksheets* (`listing_agreement_prep`,
  `purchase_offer_prep`) — internal prep docs explicitly labeled as not
  contracts, with signature lines and binding language forbidden by the
  prompt. Do not add a `purchase_agreement` document type.
- **"Total legal compliance" is never claimed anywhere in this codebase on
  purpose.** Every compliance-related response carries a disclaimer. The
  AML overview data (`app/services/compliance_data.py`) documents a US
  federal rule that was vacated by a court weeks after taking effect —
  literally proof that this space changes fast. Don't remove disclaimers
  to make copy punchier.

---

## 3. Complete file map

### 3.1 `app/core/` — foundational config and infrastructure
| File | Purpose |
|---|---|
| `config.py` | Single `Settings` object (pydantic-settings), loads from `.env`. Every configurable value in the app lives here — if you add a new integration, add its config here first. |
| `database.py` | SQLAlchemy engine/session setup. `init_db()` imports every model module so `Base.metadata.create_all()` sees all tables — **if you add a new model file, you MUST add its import here or the table will never be created.** |
| `security.py` | Just invite-code generation now (password hashing/JWT issuance moved to Supabase Auth). |
| `supabase_auth.py` | Verifies Supabase-issued JWTs via JWKS (or legacy HS256 shared secret if `SUPABASE_JWT_SECRET` is set). This is the ONLY place tokens are verified — `deps.py` calls into this. |

### 3.2 `app/models/` — SQLAlchemy ORM models (11 files, all registered in `init_db()`)
| File | Key tables | Notes |
|---|---|---|
| `org.py` | `Organization`, `User`, `InviteCode` | `User.id` = Supabase `auth.users.id` (NOT auto-generated — set explicitly at signup). No password field. |
| `client.py` | `Client` | A realtor's client (buyer/seller). Has `external_provider`/`external_id`/`last_synced_at` for CRM dedup matching. |
| `property.py` | `Property` | Has `compliance_risk`/`compliance_flags` populated automatically at ingest. |
| `neighborhood.py` | `Neighborhood` | Reference data, not org-scoped. |
| `comparable.py` | `Comparable` | Links subject property to comp properties with similarity score. |
| `price_history.py` | `PriceHistory` | One row per price change per property — powers the Opportunity Engine's real price-drop detection. |
| `message.py` | `Message` | Unified inbox — every email/SMS/voice/manual message, inbound or outbound, in one table. `channel` enum includes `voice`. Has `compliance_flagged`/`compliance_notes`. |
| `trust.py` | `TrustScore`, `TrustEvent` | The trust ladder. Score 0-100 per (user, action_type), thresholds in config determine `AutomationLevel`. |
| `alert.py` | `AlertRule`, `AlertEvent` | Includes `AlertRuleType.COMPLIANCE_FLAG` — an always-on system rule auto-provisioned per user, NOT user-created. `AlertEvent.severity` distinguishes voice (`critical`) from email/SMS (`warning`) compliance flags. |
| `document.py` | `Document` | `DocumentType` enum — see section 2.4 above for what's deliberately excluded. |
| `crm_connection.py` | `CRMConnection`, `CRMSyncLog` | Credentials stored ENCRYPTED (`encrypted_credentials` column) — never plaintext. |

### 3.3 `app/services/` — all business logic lives here, not in routes
Routes should be thin — parse request, call a service function, return
result. If you find yourself writing real logic inside a route function in
`app/api/`, move it to a service.

Key services and their one-sentence purpose:
- `llm_service.py` — DeepSeek API wrapper. Every LLM call in the fast path goes through this.
- `hermes_agent_service.py` — Hermes Agent delegation. See section 5.
- `embedding_service.py` / `memory_service.py` / `app/memory/vector_store.py` — semantic memory (FAISS + local sentence-transformers embeddings), mem0-SDK-compatible interface so it's a drop-in swap later.
- `property_service.py` — listing ingestion (upsert-aware, records price history, auto-screens compliance).
- `analysis_service.py` — CMA / property analysis, deterministic value estimate + LLM narrative.
- `opportunity_service.py` — deal-scoring engine (price position + DOM pressure + real price drops).
- `matching_service.py` — bidirectional client↔property matching.
- `portfolio_simulator.py` — pure-Python investment math (cap rate, cash-on-cash, multi-year projection). No LLM involved — verified numerically correct during development, see section 8.
- `negotiation_service.py` — LLM-backed negotiation strategy suggestions grounded in comps + price history.
- `inbox_service.py` — draft generation (4 tones) + send, wired to trust ladder AND compliance (informational).
- `trust_service.py` — the trust ladder scoring logic.
- `voice_service.py` — STT/TTS provider abstraction (OpenAI/ElevenLabs), pluggable local/Supabase audio storage.
- `voice_conversation_service.py` — full voice turn orchestration, contains the compliance hard-gate.
- `orchestrator_service.py` — chat intent classification + routing (the `/chat` endpoint's brain). Contains the command-parser fast path before falling back to LLM classification.
- `alert_service.py` / `compliance_alert_service.py` — alert rule evaluation and compliance-to-alert wiring.
- `approvals_service.py` — read-only aggregator of everything awaiting human review across Message/AlertEvent/CRMSyncLog.
- `compliance_service.py` / `compliance_data.py` — fair housing screening (keyword scan + LLM contextual pass), disclosure reference, AML overview.
- `content_generation_service.py` — marketing content generation (7 types), auto-screened.
- `document_service.py` / `document_extraction_service.py` — document upload/generate/rework/score.
- `crm_sync_service.py` / `crm_credential_service.py` / `csv_import_service.py` — CRM integration sync logic and encrypted credential storage.
- `file_storage_service.py` — generic pluggable file storage (local/Supabase), used by documents.
- `command_parser_service.py` / `command_execution_service.py` — deterministic slash-command parsing for the chat interface (fast path before LLM classification).

### 3.4 `app/crm_connectors/` — CRM adapter implementations
- `base.py` — `CRMConnector` abstract interface.
- `followupboss.py` — real, working implementation. HTTP Basic auth (API key as username). Uses `/v1/events` (not `/v1/people` directly) for new leads specifically because Follow Up Boss's own docs say this triggers the account's automations.
- `hubspot.py` — real, working implementation. Private App Bearer token (not OAuth — OAuth is only needed for public Marketplace apps). Webhooks do NOT work with Private App tokens — this is a real HubSpot platform limitation, not a bug. HubSpot sync is pull-based only.
- `csv_connector.py` — fallback for the majority of CRMs (kvCORE/BoldTrail, BoomTown, Sierra) that don't expose a public API at all. One-time import, not live sync.
- `factory.py` — provider string to connector class.

### 3.5 `app/scrapers/` — listings data sources
- `base.py` — `ListingsSource` interface.
- `demo_source.py` — deterministic synthetic data generator (seeded by city+state, so repeatable). Default (`LISTINGS_SOURCE=demo`).
- `reso_client.py` — stub for a real, licensed RESO Web API / MLS IDX feed. Requires `RESO_API_BASE_URL`/`RESO_API_TOKEN`. Field mapping in `_normalize()` needs adjusting to your specific MLS provider's actual field names before this is usable — every MLS's RESO implementation varies slightly.
- `factory.py` — `LISTINGS_SOURCE` config value to source class.

### 3.6 `app/api/` — route files (one per resource, all registered in `main.py`)
Full endpoint reference in section 4. Route files are intentionally thin —
see section 2 above.

### 3.7 `app/prompts/` — every LLM system prompt, kept separate from services
Prompts are versioned/edited independently of the logic that calls them.
When tuning behavior, edit here first before touching service code.

### 3.8 `app/schemas/` — Pydantic request/response models
Convention: every `*Out` schema that's constructed FROM a SQLAlchemy
ORM object needs `model_config = ConfigDict(from_attributes=True)`. Schemas
constructed from plain dicts (e.g. `ContentItemOut`) don't need it. Check
this when adding a new schema — it's the single most common
FastAPI+SQLAlchemy integration bug.

### 3.9 `frontend/` — static HTML/CSS/JS, no build step
- `shared/config.js` — THE ONE FILE TO EDIT for deployment. Sets
  `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `REALTYAI_API_BASE`. Every page loads
  this before anything else. (This used to be copy-pasted into 15 separate
  files — that was the most likely cause of "some pages work, some don't"
  bugs before this review; it's now centralized. If you see any page with
  an inline `window.SUPABASE_URL = ...` block instead of loading
  `config.js`, that's a regression — fix it back to loading the shared file.)
- `shared/supabase-client.js` — Supabase auth wrapper (signUp/signIn/getSession/etc).
- `shared/api.js` — the ONLY place that should call `fetch()` against the backend. Every backend feature needs a corresponding method here, AND a call site somewhere in a page, or it's dead/unreachable code (see section 8.2 for how this was audited).
- `shared/sidebar.js` / `shared/app-shell.css` / `shared/tokens.css` — shared UI shell and design tokens.
- `landing/index.html` — marketing site.
- `app/*.html` — the actual product, one file per screen (dashboard, inbox, voice, alerts, properties, content-studio, documents, opportunities, investment-calculator, compliance, trust, crm-integrations, login, signup).
- `admin/dashboard.html` — platform admin (you), not a customer-facing screen.

### 3.10 `mcp_server/` — standalone compliance MCP server
Self-contained (does NOT import from `app/`) so it can be deployed
independently. `server.py` for Claude Desktop/Code (real MCP protocol).
`deepseek_bridge.py` for DeepSeek specifically, since DeepSeek doesn't
speak MCP but does support OpenAI-style function calling — this is the
integration path for DeepSeek, not the MCP server itself.

---

## 4. Complete API reference

Base path for all routes below: your `REALTYAI_API_BASE`. All routes
except `/health`, `/auth/complete-signup`, and the CRM webhook endpoint
require `Authorization: Bearer <supabase-jwt>`.

| Method | Path | Purpose |
|---|---|---|
| GET | `/health` | No auth. Liveness check. |
| POST | `/auth/complete-signup` | Redeem invite code, create org + profile. Requires a valid Supabase token but not yet a RealtyAI profile. |
| POST | `/auth/admin/invite-codes` | Admin only. Generate an invite code for a plan tier. |
| GET/POST | `/properties`, `/properties/ingest` | List / pull listings from the configured source. |
| GET | `/properties/{id}`, `/properties/{id}/comps` | Detail, comps. |
| POST | `/properties/{id}/compliance-check` | Full LLM-backed fair housing review (vs. the fast scan done automatically at ingest). |
| POST | `/analyze/property` | CMA: deterministic value estimate + LLM narrative. |
| POST | `/analyze/investment/{id}` | Investment narrative (LLM). For real math, use `/portfolio/simulate` instead. |
| GET/POST | `/neighborhood`, `/neighborhood/{id}/score` | Neighborhood list / opportunity scoring. |
| GET/POST | `/inbox`, `/inbox/receive` | Unified inbox list / simulate-inbound-and-generate-drafts. |
| POST | `/inbox/{id}/reply` | Send a chosen draft. Feeds trust ladder + compliance check. |
| GET | `/trust/me` | Current user's trust scores per action type. |
| GET | `/opportunities?city=` | Deal-scoring engine. |
| GET | `/matching/clients/{id}/properties`, `/matching/properties/{id}/clients` | Bidirectional matching. |
| POST | `/portfolio/simulate` | Real investment math. Has a frontend now — see `investment-calculator.html`. |
| POST | `/negotiation/{property_id}` | Negotiation strategy suggestion. |
| GET/POST | `/alerts/rules`, `/alerts/events` | Alert rule management + event feed. |
| GET | `/alerts/events/unread-count` | Sidebar badge count. |
| POST | `/alerts/events/{id}/read` | Mark read. |
| POST | `/voice/converse` | Full voice turn: audio in, transcript+reply+audio out. |
| GET | `/voice/audio/{id}` | Serve synthesized audio. |
| POST | `/voice/synthesize` | Text-to-speech utility, no conversation context. |
| POST | `/voice/telephony/incoming-call`, `/voice/telephony/handle-speech` | Twilio webhooks — NOT called by the frontend, called BY Twilio. |
| POST | `/compliance/screen-listing` | Full two-pass fair housing screen for arbitrary text. |
| GET | `/compliance/disclosure-reference/{jurisdiction}`, `/compliance/aml-overview/{country}` | Reference data. |
| GET | `/content/types` | List available marketing content types. |
| POST | `/content/generate` | Marketing content generation. |
| GET/POST | `/documents`, `/documents/upload`, `/documents/generate` | Document management. |
| POST | `/documents/{id}/score`, `/documents/{id}/rework` | Compliance re-check / auto-rework. |
| GET/POST | `/crm/providers`, `/crm/connections` | CRM connection management. |
| DELETE | `/crm/connections/{id}` | Disconnect. |
| POST | `/crm/connections/{id}/sync` | Manual sync trigger. |
| GET | `/crm/connections/{id}/logs` | Sync history. |
| POST | `/crm/import/csv` | CSV fallback import. |
| POST | `/crm/webhook/{connection_id}/{webhook_secret}` | Called BY the CRM provider, not the frontend. No auth dependency (the URL secret + provider signature check IS the auth). |
| POST | `/chat` | Main chat orchestrator — command fast-path, then LLM intent routing (may delegate to Hermes for `deep_research`). |
| POST | `/agent/delegate` | Explicit Hermes delegation (the "Go Deep" button). |
| GET | `/agent/hermes-status` | Whether Hermes is configured/reachable. |
| GET | `/agent/approvals` | Aggregated pending-human-review items. |
| GET/POST | `/admin/organizations`, `/admin/invite-codes` | Platform admin only. |
| POST | `/admin/organizations/{id}/deactivate` | Platform admin only. |

---

## 5. Hermes Agent integration — setup steps

Hermes (nousresearch.com/hermes-agent) is a separate service, not part of
this repo's dependency tree — it has no published PyPI wheel and can't go
in `requirements.txt`.

1. Install Hermes on its own host (can be the same server, different
   process/port, or a completely separate machine):
   ```bash
   curl -fsSL https://hermes-agent.nousresearch.com/install.sh | bash
   ```
2. Configure a model provider for Hermes itself: `hermes model` (interactive).
3. Enable the API server:
   ```bash
   hermes config set API_SERVER_ENABLED true
   hermes config set API_SERVER_KEY <a-secret-you-generate>
   ```
4. Start the Hermes gateway/server — confirm the exact current start
   command against `hermes --help` or the live docs at
   hermes-agent.nousresearch.com/docs for your installed version. This
   was a fast-moving young project (v0.1 to v0.19 within 5 months) as of
   when this integration was built — don't trust a hardcoded command from
   this doc without verifying it against the current CLI.
5. In this app's `.env`:
   ```
   HERMES_ENABLED=true
   HERMES_API_BASE_URL=http://<hermes-host>:<port>/v1
   HERMES_API_KEY=<same secret as step 3>
   ```
6. Verify: `GET /agent/hermes-status` should return `{"available": true}`.

If any of this isn't configured, `deep_research` chat requests and the "Go
Deep" button return a clear "not connected" message — they do NOT fail
silently or crash.

---

## 6. Step-by-step: standing this up from zero

### 6.1 Prerequisites
- Python 3.11+
- A Supabase project (free tier is fine to start) — provides Postgres + Auth + optionally Storage
- A DeepSeek API key
- Docker (optional, only needed if you want local Postgres instead of Supabase directly)

### 6.2 Backend setup
```bash
cd realtyai
chmod +x init.sh
./init.sh
```
This creates a venv, installs dependencies, copies `.env.example` to
`.env`, and initializes the database schema. You must then edit `.env`
before the app is usable:

```
DEEPSEEK_API_KEY=<your key>
SUPABASE_URL=https://xxxxx.supabase.co
SUPABASE_ANON_KEY=<from Supabase Project Settings -> API>
SUPABASE_SERVICE_ROLE_KEY=<same location — SECRET, backend only>
DATABASE_URL=<Supabase Postgres connection string, Project Settings -> Database>
```

Then:
```bash
source venv/bin/activate
python scripts/init_db.py       # creates all tables — safe to re-run, no-ops if tables exist
uvicorn app.main:app --reload
```

Create your first admin user (this creates BOTH the Supabase auth account
AND the RealtyAI profile row):
```bash
python scripts/create_admin.py you@company.com "Your Name" "a-strong-password"
```

Verify: `curl http://localhost:8000/health` should return
`{"status":"ok","environment":"development"}`.

### 6.3 Frontend setup
1. Edit `frontend/shared/config.js` — this is the ONE file to edit
   (see section 3.9). Set `SUPABASE_URL`, `SUPABASE_ANON_KEY`, and
   `REALTYAI_API_BASE` (point at wherever step 6.2's `uvicorn` is running).
2. Serve the directory: `cd frontend && python3 -m http.server 4000` (or
   `npx serve`, or a real static host in production).
3. Visit `http://localhost:4000/app/login.html`.
4. Log in with the admin credentials from step 6.2.

### 6.4 Optional: Row Level Security
Run `scripts/supabase_rls.sql` in the Supabase SQL editor. Read the
comment at the top of that file first — as long as this backend connects
with the standard Supabase connection string, RLS does NOT restrict the
backend's own queries (Postgres RLS never applies to a table-owning role).
The app-level `org_id` filtering already in every service is the real
tenant-isolation enforcement. RLS matters once/if you add direct
frontend-to-Supabase queries (e.g. Realtime subscriptions) that bypass this
FastAPI backend.

### 6.5 Optional integrations (all degrade gracefully if unconfigured)
- Voice: set `STT_PROVIDER`/`TTS_PROVIDER` + matching API key
  (`OPENAI_API_KEY` or `ELEVENLABS_API_KEY`+`ELEVENLABS_VOICE_ID`).
- Phone calls: additionally set `TWILIO_*` vars + `PUBLIC_BASE_URL`
  (must be internet-reachable — use `ngrok` in dev).
- Real MLS data: set `LISTINGS_SOURCE=reso` + `RESO_API_*` — but first
  adjust the field mapping in `app/scrapers/reso_client.py::_normalize()`
  to your actual MLS provider's schema.
- Hermes Agent: see section 5.
- CRM sync: no env config needed — connections are created per-org
  through the UI (`crm-integrations.html`), credentials encrypted and
  stored per-connection in the database.

---

## 7. Bugs found and fixed in this review pass

Documented here so you know what was already broken and already fixed —
don't re-introduce these.

1. `app/services/alert_service.py` — `params.get("minmatch_score", 70)`
   was a typo for `"min_match_score"`. Any agent-configured threshold for
   new-listing-match alerts was silently ignored, always using the default
   of 70. Fixed.

2. Frontend Supabase config was copy-pasted into 15 separate files,
   each needing identical manual edits on deployment. Missing even one
   left that specific page's auth silently broken while others worked —
   this is almost certainly the actual cause of "lots of stuff isn't
   working" reported after deployment. Fixed by centralizing into
   `frontend/shared/config.js`.

3. 7 backend features had zero frontend access — fully built, tested
   services with no UI path to reach them: `negotiationStrategy`,
   `simulatePortfolio`, `hermesStatus`, `createAlertRule`/`listAlertRules`,
   `getCrmSyncLogs`. Fixed: added a Negotiate button to Opportunities,
   built the missing Investment Calculator page from scratch, wired Hermes
   status into the Go Deep button, added alert rule management to Alerts,
   added sync history to CRM Integrations. (`getComps` remains unreached
   from the UI — left alone deliberately, since comps already surface
   through the CMA analysis flow and a standalone comps view is low value.)

4. Duplicate `httpx==0.27.2` entry in `requirements.txt` (harmless —
   same version both times — but sloppy). Fixed.

5. `sentence-transformers` (a real dependency, needed for local
   embeddings) pulls in `torch`, and an unpinned install commonly resolves
   a full CUDA-enabled build — multiple GB, slow/flaky to download,
   pointless on a CPU-only API server, and a plausible cause of Docker
   build timeouts or out-of-memory failures on smaller deployment tiers.
   Fixed — Dockerfile now explicitly installs CPU-only torch from
   `https://download.pytorch.org/whl/cpu` before the main requirements
   install.

6. Added a `HEALTHCHECK` to the Dockerfile (previously `curl` was
   installed in the image but never actually used for anything).

### Verified correct (not bugs, checked and confirmed sound):
- No circular imports anywhere in `app/` (verified via AST-based cycle
  detection across the full import graph, not just spot-checking).
- Every model file is registered in `init_db()` — no table will silently
  fail to be created.
- Every route file in `app/api/` is registered in `main.py`, and vice
  versa — no orphaned routes, nothing imported that doesn't exist.
- `.env.example` and `config.py`'s `Settings` fields are in exact 1:1
  correspondence (35/35) — no env var silently ignored, nothing documented
  that doesn't actually do anything.
- `app/services/crm_credential_service.py`'s Fernet encryption was
  actually executed (not just read) with the real `cryptography`
  library during this review: encrypt-then-decrypt round-trip confirmed
  correct, and decryption with the wrong key was confirmed to correctly
  raise `InvalidToken` rather than silently succeeding or corrupting data.
- `app/core/supabase_auth.py`'s HS256 JWT verification path was actually
  executed with the real `PyJWT` library: valid tokens decode correctly,
  wrong-audience tokens are correctly rejected, expired tokens are
  correctly rejected.
- `app/services/portfolio_simulator.py`'s investment math was run with
  realistic inputs during original development (see section 8.1) — down
  payment, mortgage payment, cap rate, and cash-on-cash all confirmed
  arithmetically sound.
- `app/crm_connectors/csv_connector.py` was run against a realistic CRM
  export with varied column naming and a deliberately blank-name row —
  confirmed it parses correctly and skips garbage rows rather than
  crashing.

---

## 8. Testing performed, and how to extend it

Important context on testing methodology: this codebase was developed
and reviewed in an environment without network access to PyPI, so `pip
install` of the actual dependencies (fastapi, sqlalchemy, etc.) was never
possible during development. All testing described below is either (a)
pure static analysis, or (b) actual execution of pure-Python logic using
the handful of packages that happened to be pre-installed in that
environment (`cryptography`, `PyJWT`). This means the full
FastAPI+SQLAlchemy+Postgres request/response cycle has never actually been
executed end-to-end before this code reached you. That's the single
biggest reason "stuff isn't working" is plausible even though every static
check passes — static analysis catches syntax errors, import errors, and
logic bugs in isolated functions, but cannot catch: SQLAlchemy relationship
misconfigurations that only surface at query time, Pydantic
validation edge cases against real Postgres data types, FastAPI dependency
injection ordering issues, or async/sync interaction bugs. You have
network access and a real Python environment — running the actual test
suite and manually exercising each endpoint against a real database is the
single highest-value thing you can do next.

### 8.1 What WAS actually executed (not just read) during development/review
- `app/services/portfolio_simulator.py` — run with `purchase_price=400000,
  monthly_rent=2400, hold_years=5`; confirmed down payment = $80,000,
  monthly mortgage payment = $2,128.97, year-1 cap rate = 5.1%, year-1
  cash-on-cash = -5.7% (correctly negative given the rent/price ratio),
  5-year annualized return = 14.11%. Re-run this test after any change to
  that file:
  ```python
  from app.services.portfolio_simulator import SimulationAssumptions, simulate
  a = SimulationAssumptions(purchase_price=400000, monthly_rent=2400, hold_years=5)
  result = simulate(a)
  assert result['down_payment'] == 80000.0
  assert result['year_1_cap_rate_pct'] is not None
  ```
- `app/services/compliance_service.py`'s `keyword_scan` logic — tested
  against both a violation-loaded listing ("no children please... Adults
  only community") and a clean listing ("master bedroom... walk-in closet
  ... growing family") — confirmed it catches real violations and does NOT
  false-positive on normal real estate language.
- `app/crm_connectors/csv_connector.py`'s `parse_csv_contacts` — tested
  against a 3-row CSV with varied column headers ("Full Name", "Email
  Address", etc.) and one deliberately blank-name row — confirmed correct
  parsing and correct skipping.
- `app/services/crm_credential_service.py` — full encrypt/decrypt
  round-trip executed with the real `cryptography` library (see section 7).
- `app/core/supabase_auth.py`'s HS256 path — full JWT
  encode/decode/verify cycle executed with the real `PyJWT` library,
  including negative tests for wrong audience and expiry (see section 7).
- The complete cross-file consistency suite in section 6 (11 checks) — all
  passing as of this document.

### 8.2 What was verified via static analysis only (needs real execution)
- Every POST/PUT request body schema (Pydantic) — never validated
  against an actual FastAPI request/response cycle. Recommended: write a
  `pytest` + `httpx.AsyncClient` (or `TestClient`) test per endpoint that
  POSTs a realistic payload and asserts a 200/201, not just that the
  schema class compiles.
- Every SQLAlchemy relationship and query — never executed against a real
  Postgres instance. Recommended: after `python scripts/init_db.py`
  against a real Supabase database, manually walk through the core flows
  in section 8.3 below.
- The Twilio `VoiceResponse`/`Gather`/`Play` usage in
  `routes_voice_telephony.py` — matches the documented Twilio Python SDK
  API as researched during development, but has never been exercised
  against an actual Twilio account/call.
- The Follow Up Boss and HubSpot connector implementations
  (`app/crm_connectors/`) — match their documented REST APIs as
  researched, but have never made a real HTTP call to either service.

### 8.3 Recommended manual test flow (do this first, in this order)
1. `POST /auth/complete-signup` with a freshly-generated invite code — confirms org/profile creation and Supabase token verification together.
2. `POST /properties/ingest` with `city=Edmonton, state=AB` (demo source, no external creds needed) — confirms the DB write path, price history creation, and compliance auto-screening all work end to end.
3. `POST /analyze/property` on one of the ingested properties — confirms comps retrieval (embedding search) and the LLM call to DeepSeek both work.
4. `POST /inbox/receive` then `POST /inbox/{id}/reply` — confirms draft generation, trust ladder scoring, and the compliance informational check.
5. `POST /portfolio/simulate` — pure math, no external dependencies, should always work if the app boots at all; good smoke test.
6. Only after 1-5 pass: test voice (`POST /voice/converse`, requires `OPENAI_API_KEY` or ElevenLabs), CRM connections (requires real Follow Up Boss/HubSpot credentials), and Hermes delegation (requires a running Hermes instance).

### 8.4 If something fails, check in this order
1. Is `.env` fully filled in? Compare against `.env.example` line by line — 35 variables, all documented in section 6.2/6.5.
2. Did `python scripts/init_db.py` actually run against the database
   `DATABASE_URL` points to? A common failure mode: editing `.env` after
   already running `init_db.py` against a different (e.g. local Docker)
   Postgres — the app then can't find its tables in the new target.
3. Is `frontend/shared/config.js` filled in AND is
   `REALTYAI_API_BASE` reachable from wherever the browser is running?
   Browser dev tools Network tab will show CORS errors or connection
   refused here.
4. Is `ALLOWED_ORIGINS` in `.env` set to include the actual frontend
   origin? FastAPI's CORS middleware will silently block requests from
   an origin not in this list — check the browser console for a CORS
   error, not a 4xx/5xx.
5. For any LLM-backed feature returning empty/error responses: check
   `DEEPSEEK_API_KEY` is valid and has quota. `llm_service.py` uses
   `tenacity` retry (3 attempts) — a persistent failure after retries means
   the key/quota/network is the issue, not application logic.
6. For voice: confirm `STT_PROVIDER`/`TTS_PROVIDER` and the matching
   API key are set — `voice_service.py` raises a clear
   `RuntimeError` with a specific message when not configured, surfaced as
   an HTTP 503 by the route, not a silent failure. Check the response body,
   not just the status code.

---

## 9. Known gaps — real, not hidden

- Alert delivery is in-app only. `AlertEvent` rows are created
  immediately when something fires, but nothing pushes a notification
  (SMS/email/push) — the badge count updates on next page load, nobody's
  phone buzzes. Real-time push is a genuine next feature, not a bug.
- Twilio call routing is single-tenant. `routes_voice_telephony.py`'s
  `_resolve_default_org_and_user` routes every inbound call to the first
  platform admin user — documented as a TODO in that file. Multi-tenant
  phone routing needs either per-org Twilio numbers or an IVR
  agent-selector.
- HubSpot webhooks don't work with Private App tokens (a real HubSpot
  platform limitation, not a bug in this code) — HubSpot sync is
  pull/poll-based only, unlike Follow Up Boss which has real push webhooks.
- Documents can't be hand-edited and saved — the content textarea in
  `documents.html` is read-only; changes flow through "Auto-rework" (an
  LLM rewrite pass) rather than a direct PATCH endpoint. Adding
  `PATCH /documents/{id}` for direct saves is the natural next step if this
  turns out to matter.
- `app/scrapers/reso_client.py`'s field mapping is a template, not a
  finished integration — every MLS's actual RESO Web API implementation
  varies; `_normalize()` needs adjusting to whichever specific MLS/board
  you get a license from.
- No automated test suite runs in CI — `tests/` has two files
  (`test_health.py`, `test_trust_service.py`), a starting point, not
  coverage. Given this is the first time the app can actually be executed
  against real dependencies (see section 8), writing real integration
  tests for the flows in section 8.3 should be a priority.
- The Meridian Company OS-inspired features
  (`command_parser_service.py`, `approvals_service.py`) are a fresh
  implementation of a described pattern, not a port of actual code — the
  linked source repo returned a 404 when originally referenced and was
  never actually read. If you get real access to that repo and want
  something specific ported, treat it as a new task with the real source
  in hand, not an extension of what's here.

---

## 10. If you're DeepSeek (or any coding agent) picking this up

Priority order for continued work, given everything above:

1. Get a real test run working first. Install the actual dependencies
   (`pip install -r requirements.txt` in a real environment with network
   access), stand up against a real Supabase project, and run through
   section 8.3's manual test flow. This will surface real bugs that static
   analysis in a network-isolated environment structurally could not catch.
2. Fix whatever section 8.3 turns up before adding new features — this
   codebase has a lot of surface area already; consolidating correctness
   is higher value than expanding scope right now.
3. Write real `pytest` integration tests for at least the six flows in
   section 8.3, using a real (or dockerized) Postgres test database. This
   closes the single biggest gap in this project's development history.
4. Read the docstring/module comment above any function before "fixing"
   it — this codebase has several deliberate constraints (section 2.4)
   that look like gaps but are safety/legal decisions. If you disagree with
   one, that's a conversation to have explicitly with the project owner,
   not a silent revert.
5. When adding a new feature, check whether it fits an existing pattern
   (adapter for external integrations, service-layer logic with thin
   routes, compliance-strictness-matches-human-review for anything
   autonomous) before inventing a new one.
