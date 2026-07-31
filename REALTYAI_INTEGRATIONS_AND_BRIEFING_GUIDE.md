# RealtyAI — Personality, Daily Briefing, Calendar, Memories & Integrations

**Read `REALTYAI_BUILD_GUIDE.md` first if you haven't** — this document covers
only what changed in this round (personality rewrite, Daily Briefing,
Calendar, Memories browsing, and four new integrations: Gmail, Microsoft,
Slack, Twilio SMS). It assumes everything in the base build guide already
holds (architecture philosophy, existing file map, existing bugs already
fixed, existing gaps already documented) — this is additive, not a replacement.

---

## 1. Athena's personality — what changed and why it's split the way it is

`app/prompts/athena_persona.py` is the new single source of truth for
Athena's character: verbose rather than clipped, thinks in connections and
patterns rather than just retrieving facts, and has two registers —
supportive when the agent needs someone steady in their corner, and
constructively pushy when they're avoiding something they shouldn't be
(a cold lead, an overdue follow-up, a compliance flag). It's imported into:

- `orchestrator_service.py`'s `GENERAL_SYSTEM_PROMPT` (chat)
- `voice_persona.py`'s `AGENT_SYSTEM_PROMPT` (in-app voice)
- `client_ai.py`'s brief and next-action prompts (the CRM AI features)

**The one non-obvious decision here, worth preserving:** `voice_persona.py`
used to have a single `SYSTEM_PROMPT` shared by two completely different
audiences — the agent talking to their own Athena, and real clients calling
the business phone line via Twilio. Giving voice a richer, occasionally
"pushy" personality made that conflation into a real problem: you don't
want Athena being coaching-pushy with an actual prospective buyer who
called in. It's now split into `AGENT_SYSTEM_PROMPT` (full personality,
used by `handle_voice_turn` — the in-app widget) and `CLIENT_SYSTEM_PROMPT`
(warm, professional, explicitly told NOT to use the pushy register — used
by `routes_voice_telephony.py`'s Twilio handler via
`generate_spoken_reply(..., caller_context="client")`). **If you add any
new voice or chat surface, decide explicitly which audience it's for and
pick the right prompt — don't default to whichever one is already imported
in the file you're editing.**

Inbox email/SMS drafts (`inbox_service.py`) were deliberately left
unchanged — those are content Athena drafts for the agent to send to
*their* clients, so they stay professional/appropriate for an external
audience rather than picking up the richer internal-facing voice.

---

## 2. Daily Briefing — now at the top of the sidebar

`app/services/daily_briefing_service.py` aggregates, in one call:
active client count, stale leads (14+ days no contact), hot leads,
today's calendar events, overdue tasks (across every client), pending
approvals (reusing `approvals_service.py`), and pipeline value in play —
then makes ONE LLM call for the "AI Insights" section specifically, using
the new persona, because that's the one part where judgment matters more
than raw numbers (the stat cards already show the numbers; the insights
should say what the numbers *mean*, and this is where the "constructively
pushy" register gets used if something's genuinely being let slip).

Route: `GET /briefing`. Frontend: `frontend/app/daily-briefing.html`,
placed first in the sidebar nav (`NAV_ITEMS` in `sidebar.js`) per the
explicit request that this be the first thing an agent sees.

**Design note inherited from the reference screenshot you shared earlier
in this build:** stat-card row → AI insights → priorities/tasks →
calendar/leads sidebar. Kept that shape rather than inventing a new
layout, since it's a proven pattern from the product this is meant to
feel like a real upgrade from.

**If the LLM call fails** (bad API key, network issue, etc.), the briefing
still loads — `daily_briefing_service.py` catches the exception and shows
`"(AI insights unavailable right now: {error})"` instead of failing the
whole page. Every other section is pure database aggregation with no LLM
dependency, so a DeepSeek outage degrades one section, not the whole tab.

---

## 2b. Daily Briefing — revised against the actual reference screenshot

The first version of this page (described in section 2) was built from
memory of screenshots shared much earlier in the conversation. Once the
actual reference screenshot was shared again, several concrete gaps showed
up and were fixed:

- **AI Insights are now individual numbered cards, not a paragraph.**
  `daily_briefing_service.py`'s `_generate_insights()` parses the LLM's
  `"1. ... / 2. ..."` output into a real `list[str]` (tested against both
  a well-formatted response and a fallback case where the model ignores
  the numbering instruction — the fallback still returns something
  sensible instead of an empty section or a crash). The prompt in
  `daily_briefing.py` was tightened to explicitly demand that format.
- **Real mini-calendar widget** — a compact month grid with a dot on any
  day that has an event and today highlighted, matching the reference,
  instead of a plain text list of today's events. Reuses the existing
  `GET /calendar/events` endpoint for the current month.
- **New Messages panel** — pulls the 5 most recent inbound `Message` rows
  (any channel), added to `get_daily_briefing()`'s return payload.
- **History / Refresh buttons** on the hero banner. Refresh re-fetches
  everything (cheap, since the briefing has no server-side caching to
  invalidate). **History is a stub** — it tells the user plainly that past
  briefings aren't stored anywhere, rather than pretending to show
  something that doesn't exist. Every briefing is generated fresh from
  live data on each load; there's no `DailyBriefingSnapshot` table. Adding
  one (write a snapshot row each morning, or each time the page loads) is
  the natural next step if looking back at past briefings turns out to
  matter.
- **Stat cards restyled** to match the reference's icon-square +
  top-right-metadata + big-number + label layout, and remapped to the
  four stats actually shown in the reference (Clients w/ "N new (7d)",
  Hot Leads w/ pipeline $ value, Pending Tasks combining overdue tasks +
  approvals w/ high-priority count, Today's Events w/ new-message count) —
  these aren't a 1:1 field mapping from the old Athena product (this
  platform's data model is different — pipeline stages, engagement
  scores, etc. didn't exist in the reference), but the visual *shape* now
  matches closely.

Verified: re-ran the insight-parsing logic directly (not just read) against
both a correctly-numbered LLM response and an unformatted one — both
produce sensible output, confirmed via `assert`.

---

## 3. Calendar — local model + two-way external sync

### Local calendar (works with zero external configuration)
`app/models/calendar_event.py`'s `CalendarEvent` — full CRUD via
`calendar_service.py` and `routes_calendar.py`. Frontend:
`frontend/app/calendar.html`, a real month-view grid (not a stub) with a
day-detail panel for viewing/adding/deleting events. **Not built:** week
and day views, and editing an existing event's time/title (only add/delete
exist in the UI right now — `PATCH /calendar/events/{id}` exists on the
backend and is fully functional, it just has no edit form in the frontend
yet). Also not built: an inline edit form on `client-detail.html` for
general client profile fields (name/email/phone/budget) — `PATCH
/clients/{id}` works, there's just no UI for it beyond the specific fields
already covered (stage, tags, status).

### External sync (Google Calendar + Microsoft/Outlook Calendar)
`app/calendar_connectors/` (adapter pattern, same shape as
`app/crm_connectors/`) + `app/services/calendar_sync_service.py`
(orchestrates pull/push). **Polling-based, not push notifications** — see
section 5 below for why, and what upgrading to push would require.

Sync direction is per-connection (`import_only` / `export_only` /
`two_way`, stored on `CalendarConnection.sync_direction`, default
`two_way`). Two-way sync logic: pull remote events in a rolling window
(7 days back, 60 days forward by default) and upsert by `external_id`;
push any local `CalendarEvent` with `sync_pending=True` (set automatically
by `calendar_service.update_event()` whenever a previously-synced event is
edited locally) to the remote calendar, then clear the flag.

**Trigger sync manually** via `POST /integrations/calendar/{connection_id}/sync`
(wired to a "Sync now" button on `integrations.html` once connected) — **there
is no scheduled/automatic sync job**. Wiring this to a cron or Celery beat
task calling `sync_connection()` periodically (e.g. every 15 minutes) for
every active `CalendarConnection` is the natural next step for real
"it just stays in sync" behavior instead of requiring a manual click.

---

## 4. Memories tab — exactly as specified

Card grid, one card per memory, filterable by category and free-text
search, click a card to open a modal with the full memory (text, category,
linked client, created timestamp, memory ID) and a "Forget this" delete
action.

**What had to be added to support this**, since the memory system
previously only supported semantic search for internal context-injection,
not human browsing:
- `app/memory/vector_store.py` — added `created_at` timestamps on every
  stored memory (previously untracked), a `list_all()` method for
  browsing (vs. `search()`'s top-K semantic matching), a `get()` by ID, and
  a `delete()`.
- **Deletion is soft-delete, not physical removal from the FAISS index** —
  read the docstring at the top of `vector_store.py` for why (FAISS's flat
  index doesn't support cheap arbitrary removal without an ID-mapped index
  wrapper and a rebuild). Deleted entries are flagged `is_deleted: true`
  and filtered out of every read path. Fine at the scale this is built
  for; if the deleted fraction grows large over time, add a periodic
  compaction job that rebuilds the index from only non-deleted entries.
- `app/services/memory_browse_service.py` + `app/api/routes_memory.py` —
  the actual browse/filter/delete API the frontend calls.

---

## 5. The four integrations — what's real, what's polling vs. push, what's not built

Researched before building (Gmail API, Microsoft Graph, Slack Events API,
Twilio) — the single most important finding that shaped this whole section:
**Gmail push notifications (Pub/Sub watch) expire every 7 days, and
Microsoft Graph subscriptions expire roughly every 3 days — both need a
renewal cron in production, or the integration silently stops receiving
events with no error.** Given the scope already covered in this build, push
notifications are **not implemented** — every connector here uses reliable
polling instead (manually triggered via a "Sync now" button, or ready to be
wired to a scheduled job). This is a deliberate, documented trade-off, not
an oversight: polling is less "real-time," but it can't silently die the
way an unrenewed watch subscription does.

### Gmail (`app/email_connectors/gmail.py`)
Real API (`gmail.googleapis.com/gmail/v1`), OAuth2. Note on quota:
`messages.list` returns IDs only — each message needs a separate
`messages.get` call, which is why `list_new_messages()` caps how many
messages it pulls per call rather than draining a whole mailbox in one
request. Incremental sync uses Gmail's `historyId` cursor (stored on
`EmailConnection.history_id`), falling back to a plain recent-messages pull
on first connection when there's no cursor yet.

### Microsoft/Outlook (`app/email_connectors/microsoft.py`)
Real API (Microsoft Graph `v1.0`), OAuth2 via Entra ID app registration.
Simpler than Gmail here — `/me/messages` (or the delta variant) returns
full message content directly, no separate per-message fetch needed.
Incremental sync uses Graph's `$deltaToken` (stored as
`EmailConnection.delta_link` — Graph returns the *next full URL* to call,
not just a token, which is why it's stored as a full link, not a bare
cursor value).

### Google Calendar / Microsoft Calendar (`app/calendar_connectors/`)
Same OAuth grant as Gmail for Google (one consent screen covers both Mail
and Calendar scopes — see `routes_integrations.py`'s `/google/callback`,
which creates both an `EmailConnection` and a `CalendarConnection` row from
a single authorization). Microsoft is the same pattern with its own scopes.

### Slack (`app/services/slack_service.py`)
Deliberately minimal scope, matching what was actually asked for: chat
with Athena from a channel or DM, and system notifications posted to a
configured channel — not a full Slack app with slash commands or
interactive components. Inbound requests are verified via Slack's
documented HMAC v0 signing process (`verify_slack_signature()`) before
anything is processed, including replay protection (rejects requests
timestamped more than 5 minutes old). Connection is via manually pasting a
Bot User OAuth Token (from a Slack app you create at api.slack.com/apps)
rather than a full OAuth install flow — the simpler, faster-to-ship path
for a single-workspace-per-org integration; a public multi-workspace Slack
App Directory listing would need the full OAuth flow instead, a
meaningfully bigger undertaking (app review, distribution, etc.) not
attempted here.

**Routing caveat, same pattern as the existing Twilio voice telephony
code:** an inbound Slack event resolves to "the first non-admin user in
that org" (`routes_integrations.py`'s `slack_events` handler) — fine for a
single-agent org, not real for a multi-agent team where you'd want the
message routed to a specific person. Flagged with the same honesty as the
existing Twilio voice single-tenant-routing TODO.

### Twilio SMS (`POST /integrations/twilio/sms`)
Straightforward extension of the existing voice telephony pattern (same
file structure, same "first admin user" routing caveat). Inbound texts
land in the unified `Message` table exactly like inbound emails, and
`generate_drafts()` runs automatically — **the webhook responds with an
empty TwiML `<Response></Response>`, deliberately not auto-replying**,
because auto-sending would bypass the trust ladder and compliance-informational
check entirely. SMS replies go through the normal Inbox draft-review flow,
same as everything else.

---

## 6. Full verification performed on this round

Same 11-point suite from the base build guide, re-run on every file
touched in this round, all passing as of this document:

1. All Python compiles (`py_compile` across `app/`, `cli/`, `scripts/`, `tests/`)
2. MCP server syntax
3. No circular imports (AST-based full dependency graph cycle detection)
4. Every route file registered in `main.py`, and vice versa
5. Every model file registered in `init_db()`, and vice versa
6. `.env.example` and `config.py`'s `Settings` fields in exact 1:1 correspondence
7. No duplicate `requirements.txt` entries
8. All shared JS files (`api.js`, `sidebar.js`, `admin-nav.js`,
   `supabase-client.js`) pass `node --check`
9. Every inline `<script>` block across all 26 HTML pages passes `node --check`
10. Zero pages with the old inline Supabase config placeholder (fully
    centralized in `config.js`, as established in the earlier review pass)
11. **API-method usage audit** — every method in `api.js` cross-referenced
    against every `.html`/`.js` file to catch backend features with no
    frontend access point (the same audit that caught the Investment
    Calculator and several other gaps in the prior review round). Started
    this round at 11 unused methods after adding all the new API surface;
    fixed 6 of them (duplicate-merge UI, saved-search creation form,
    stale-lead check button, calendar event delete, and sync-now buttons
    on the integrations page). **5 remain, honestly**:
    - `getComps`, `getMemory`, `todaysCalendarEvents` — not real gaps,
      each is covered through a different path already in the UI (comps
      via the CMA flow, memory detail via the already-loaded list data,
      today's events via the Daily Briefing endpoint)
    - `updateCalendarEvent` — backend fully works, no edit-event form in
      `calendar.html` yet (only add/delete)
    - `updateClient` — backend fully works, no general profile-field edit
      form in `client-detail.html` beyond the specific fields already
      editable (stage, tags, status)

---

## 7. Setup checklist for this round's features

Beyond everything in the base build guide's `.env` setup:

```
# Google (Gmail + Calendar) — console.cloud.google.com
GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=
GOOGLE_REDIRECT_URI=https://your-api-domain/integrations/google/callback

# Microsoft (Outlook Mail + Calendar) — entra.microsoft.com app registration
MICROSOFT_CLIENT_ID=
MICROSOFT_CLIENT_SECRET=
MICROSOFT_TENANT_ID=common
MICROSOFT_REDIRECT_URI=https://your-api-domain/integrations/microsoft/callback

# Slack — api.slack.com/apps
SLACK_SIGNING_SECRET=
```

Then in the app itself: visit `/app/integrations.html`, click Connect on
Google/Microsoft (redirects to their real OAuth consent screen), or paste
a Slack Bot Token to connect Slack. Twilio SMS needs no new config beyond
the `TWILIO_*` vars already required for voice telephony in the base setup
— once those are set and the webhook URL is pointed at
`/integrations/twilio/sms` in your Twilio console, inbound texts flow in
automatically.

## 8. Priority order for continued work

1. **Wire scheduled sync** — email and calendar sync currently require a
   manual "Sync now" click. A cron/Celery beat job calling
   `email_sync_service.sync_connection()` and
   `calendar_sync_service.sync_connection()` for every active connection
   every few minutes is the highest-value next addition for making these
   integrations feel automatic rather than manual.
2. **Multi-tenant routing for Slack and Twilio** — both currently route to
   "the first admin/non-admin user in the org," fine for single-agent
   testing, not real for a team. Needs either per-user Twilio
   numbers/Slack channel mapping, or an explicit selector.
3. **Push notifications** (Gmail Pub/Sub, Graph subscriptions,
   Google Calendar watch) if polling latency becomes a real complaint —
   requires building the renewal-cron infrastructure flagged throughout
   this document as the reason it wasn't attempted in this round.
4. The two remaining edit-form gaps from section 6 (`updateCalendarEvent`,
   `updateClient` UI).
5. Real integration testing against actual Google/Microsoft/Slack/Twilio
   accounts — like the rest of this project, these connectors were built
   against documented API behavior but never executed against a live
   account (see the base build guide's section 8 for the full explanation
   of why, and what "real testing" should look like once you have network
   access to the actual provider APIs).

---

## 9. Memories taxonomy + Trust gamification rework (later addition)

### Memories — real category variety, not a fake taxonomy
Before this addition, every memory was hardcoded to `category="fact"` at
its one real write site (`voice_conversation_service.py`'s auto-capture)
— the Memories tab technically supported filtering by category, but there
was only ever one category actually present in the data. Fixed properly,
not just cosmetically:

- **`memory_service.classify_memory_category()`** — a keyword heuristic
  (`wants`, `prefers`, `looking for`, `budget`, `deal-breaker`, etc.) that
  auto-classifies captured statements as `preference` vs `fact`. Tested
  against 5 realistic statements (all correct) before wiring in.
  `voice_conversation_service.py`'s auto-remember call no longer hardcodes
  a category — it lets the classifier decide.
- **`insight` is a real third category now**, not just a taxonomy entry
  with no writer. `client_ai_service.suggest_next_action()` now stores its
  own generated suggestion as a linked "insight" memory — Athena's own
  judgment calls become searchable later, not just shown once and
  forgotten. Click "What should I do next?" on a client, and that
  suggestion is now sitting in the Memories tab under Insights.
- **Taxonomy (label/color/icon) lives server-side**
  (`memory_browse_service.MEMORY_CATEGORIES`, exposed via
  `GET /memory/categories`) so the frontend never hardcodes a mapping that
  could drift from what the backend actually writes. `memories.html`
  fetches this on load and renders the category filter dropdown, card
  left-border color, and badge icon all from the same source of truth.

### Trust with Athena — full rework
`app/services/trust_gamification_service.py` is new — levels, badges, and
hints, all computed from real `TrustScore`/`TrustEvent`/compliance data,
nothing fabricated for effect (the whole point of gamifying this is that
it has to be honest to be motivating).

**Levels are aligned to real autonomy thresholds, on purpose.** The 5
levels (New Partnership → Building Rapport → Limited Trust Earned → Strong
Trust → Full Autonomy) use `settings.TRUST_THRESHOLD_LIMITED` (40) and
`settings.TRUST_THRESHOLD_AUTONOMOUS` (75) as two of the five breakpoints —
so "reaching a new level" always corresponds to something Athena can
actually now do differently, never a cosmetic number with no real meaning
behind it. Verified the boundary logic directly: score=39 vs 40 correctly
land in different levels, 74.9 vs 75 correctly land in different levels.

**Badges** (`BADGE_DEFINITIONS`, 8 total) are awarded by
`evaluate_and_award_badges()`, called on every load of the gamification
endpoint (cheap — a handful of queries) and persisted to a new
`TrustBadge` table so `earned_at` is stable and a badge won't flicker in
and out if a stat hovers right at a threshold. Includes a "Comeback" badge
specifically for recovering from a rejected draft to reach Limited
Autonomy or higher — a deliberately encouraging badge, not just
achievement-for-volume ones.

**Hints** (`get_hints()`) compute a real "about N more unedited sends to
reach the next level" estimate using the actual `SCORE_DELTAS` from
`trust_service.py` (not a guessed number) — verified the ceiling-division
math directly (a gap of 40 points at +3/action correctly computes to 14
actions needed, not 13 or 15).

**The animated gauge** (`frontend/app/trust.html`) is a real SVG circular
progress ring, not a CSS trick or an image — computed from
`circumference = 2πr` and `stroke-dashoffset = circumference × (1 - score/100)`,
verified the math directly for scores 0/25/50/75/100 (a 50-point score
fills exactly 50% of the ring, confirmed to the decimal). The animation
plays because the offset is set to "full" (0% visible) in the initial
render, then updated to the real target value inside a
`requestAnimationFrame` callback on the next paint — setting the final
value in the same paint as the CSS transition wouldn't animate at all,
worth knowing if you touch this code.

**Field-naming note, not hidden:** the old `GET /trust/me` endpoint (raw
per-action `TrustScore` rows) is kept for backward compatibility, but
nothing in the frontend calls it anymore — `trust.html` was fully rebuilt
around the new `GET /trust/gamification` endpoint instead, which returns
everything in one call (scores + level + badges + hints). If you're
looking for where trust data comes from now, `/trust/gamification` is the
one that matters.

### What's NOT built in this addition
- **No badge-earned notification/toast.** A newly-earned badge shows a
  "NEW" tag on the badge card, but only the next time the Trust page
  loads — nothing fires the moment a badge is actually earned (e.g. right
  when a 10th unedited send happens). Wiring `evaluate_and_award_badges()`
  into the same places that already call `trust_service.record_outcome()`
  (inbox send, voice turn) and pushing an `AlertEvent` when something new
  comes back would close this gap — straightforward, given the alert
  system already exists.
- **No leaderboard or team comparison** — badges/levels are per-user only,
  no cross-agent comparison within an org. Not asked for, but a natural
  extension of the gamification framing if a team wants that competitive
  element later.
- **No inline edit-in-place for calendar events or general client profile
  fields** — same two gaps flagged in section 6, still open.

---

## 10. Properties tab — source selection, real card/modal system, and the honest answer on Zillow

### Where properties actually come from (read this before promising a customer "Zillow data")
Researched directly because it changes the recommendation: **Zillow retired
its public Web Services API in 2021.** What's marketed today as "Zillow
API" access on RapidAPI, Apify, and similar marketplaces are unofficial
wrappers around scraping, not anything Zillow sanctions — using one
doesn't remove the legal exposure direct scraping would create (see the
base build guide's section 2.4 for why that matters for every customer of
this platform), it just adds a middleman that can get cut off or shut down
by Zillow at any time, silently breaking the integration for everyone
relying on it.

**The actual legitimate path to Zillow-adjacent data is Bridge
Interactive** — Zillow Group's own official, RESO-standard developer
program (`bridgeinteractive.com/developers`). Free if you qualify as an
MLS-affiliated brokerage or approved technology partner; approval can take
weeks and isn't guaranteed for independent developers. Because it's
RESO-standard, `app/scrapers/bridge_interactive.py` is structurally almost
identical to the existing `reso_client.py` — same auth pattern, same query
shape, different base URL. **One real limitation documented directly in
that file:** actual listing photos come through Bridge's separate Media
resource (a second API call per listing), which this connector stubs as
empty rather than pretending to fetch — wire that in once real Bridge
access is live and you can see the actual response shape.

### The full option set now (user-selectable, not hardcoded)
`app/scrapers/factory.py`'s `SOURCE_META` + `list_available_sources()` —
exposed via `GET /properties/sources`, which the frontend calls to build
the source dropdown with real configured/not-configured status per option
(so an agent sees immediately which sources are actually usable, not just
which exist in code):

1. **Bridge Interactive** (`bridge`) — the legitimate Zillow path, above.
2. **MLS / RESO Web API** (`reso`) — already existed, direct feed from any
   licensed MLS.
3. **ATTOM Data** (`attom`) — `app/scrapers/attom_source.py`, a licensed,
   paid nationwide public-records provider — real alternative when Bridge
   approval isn't feasible. Note its real limitation: it's public-records
   data, not a live listing feed, so it has no listing agent info and no
   marketing description — documented directly in the connector rather
   than silently returning empty fields with no explanation.
4. **CSV import** (`csv`) — `app/services/property_csv_service.py`, same
   pattern as the CRM CSV fallback. Tested against realistic column-name
   variants and price formatting (`"$450,000"` → `450000.0`) before
   shipping.
5. **Demo data** (`demo`) — unchanged, but now generates real placeholder
   photos (picsum.photos, a genuinely free-to-use placeholder image
   service — not copyrighted listing photography) and realistic listing
   agent contact info, specifically so the new card/modal/agent-outreach
   features have something real to demo against without needing any API
   keys configured.

`POST /properties/ingest` now takes an explicit `source` field (falls back
to `LISTINGS_SOURCE` in `.env` if omitted) — this is the actual
"let the user decide" mechanism requested, not just a config default.

### The card + modal system
`frontend/app/properties.html` was fully rebuilt: a card grid with real
thumbnail images (not placeholders-as-final-state — every source either
provides a real `thumbnail_url` or the UI shows an honest "No Photo"
placeholder rather than a broken image), each card showing price/address/
specs/compliance risk badge. Click a card, it opens a full modal:

- **Photo gallery** — main image + clickable thumbnail strip
- **CMA & Comps tab** — runs the existing `/analyze/property` and
  `/properties/{id}/comps` endpoints on demand
- **Investment Calculator tab** — the portfolio simulator
  (`/portfolio/simulate`) embedded directly in the modal, pre-filled with
  a rent estimate derived from the property's price, so an agent doesn't
  need to leave the property to run real numbers on it
- **Listing Agent tab** — shows the actual listing agent's contact info
  (name/brokerage/email/phone) from the property record, with a purpose
  selector (request showing / ask a question / submit buyer interest) that
  drafts a real LLM-generated message via
  `POST /properties/{id}/draft-agent-message`
  (`app/services/agent_outreach_service.py`), editable inline, with a real
  Send button (`POST /properties/{id}/send-agent-message`) that records
  the sent message as an outbound `Message` row — so agent-to-agent
  correspondence shows up in the same message history system as
  everything else, not a disconnected one-off action.
- **Details tab** — MLS #, lot size, days on market, full description,
  plus an on-demand trigger for the full LLM-backed fair housing review
  (the deep pass, vs. the fast keyword scan already reflected in the card
  badge).

### What's NOT built in this addition
- **No pagination on the card grid** — `GET /properties` still caps at 200
  results with no page controls in the UI. Fine for a demo/small dataset,
  will need real pagination once an agent has hundreds of active listings.
- **Bridge Interactive's Media resource isn't wired** (see above) — photos
  from a real Bridge connection will come back empty until that second API
  call is added.
- **No map view** — cards/modal only, no geographic visualization even
  though `latitude`/`longitude` fields already exist on `Property`. A
  natural next feature if that's wanted.

---

## 11. Persistent conversations, property CRUD, and the Search tab

### Persistent conversations — the architectural fix
Before this addition, "Chat with Athena" was **completely stateless** —
every message lived only in a JS array in the browser tab, gone on
refresh. Fixed with a real persistence model:

- **`Conversation`/`ConversationMessage`** (`app/models/conversation.py`) —
  one conversation is "active" per (user, context) at a time. Every `POST
  /chat` call now persists both the user turn and the assistant reply.
- **The only reset mechanism in the entire system** is
  `conversation_service.start_new_conversation()` — called exclusively
  from an explicit user action (the "New conversation" button on the
  dashboard, or "Start New Conversation" in Settings). It doesn't delete
  the old conversation, just deactivates it — fully preserved, searchable,
  resumable later.
- **The admin's "god mode" Athena was refactored onto the same system** —
  it used to bounce a client-side history array back and forth on every
  request (fragile: lost on tab close, no cross-device continuity).
  `admin_agent_service.run_admin_chat()` now loads history from the
  persisted conversation server-side. `AdminChatRequest`/`AdminChatResponse`
  schemas simplified accordingly (no more `history`/`messages` array
  fields — just `message` in, `reply` + `conversation_id` out).
- **Search** (`conversation_service.list_conversations`, exposed via
  `GET /conversations?search=`) matches both the conversation title and
  any message buried anywhere in the thread — a term from message 40 of a
  long conversation still surfaces that conversation.
- **`frontend/app/settings.html`** — the comprehensive settings menu
  requested: Profile, a full Conversation History tab (search, resume by
  clicking any past conversation, the reset button with an explicit
  confirmation dialog explaining nothing is deleted), links out to
  Trust/Integrations/CRM management, and Account (logout, explicitly
  worded to reassure that logging out doesn't reset anything).

**One thing worth knowing if you extend this:** conversation history for
voice (in-app or Twilio) isn't wired into this same system yet — voice
turns are still only reflected in the unified `Message` table (which
already gives them a timeline on the relevant Client), not in a
`Conversation` thread the way chat now is. Extending voice to use
`conversation_service` too is a natural next step if "one continuous
relationship with Athena across every channel" should include voice.

### Property CRUD — was read/import-only before this
Added `PATCH`/`DELETE`/manual `POST /properties` endpoints and wired
Edit/Delete directly into the existing detail modal (edit form inline,
delete with a confirmation naming the specific address). **Caught a real
bug before it shipped**: naively deleting a `Property` would throw a
foreign-key violation the moment it had any price history (every ingested
listing has one) or appeared as a comp for another property — none of
those FKs cascade-delete. Fixed by explicitly cleaning up
`PriceHistory`/`Comparable`/`AlertEvent` rows referencing the property
before the delete. **Known gap**: no manual "add a single property from
scratch" form in the UI yet (`POST /properties` works, creation currently
flows through import/CSV/edit-existing only) — `api.createProperty` is
unused for that reason, consistent with how every other unused-method gap
in this project has been tracked and disclosed rather than hidden.

### Search tab — genuinely comprehensive, one query hits everything
`app/services/universal_search_service.py` fans a single query out across
seven sources in parallel, each independently try/excepted so one slow or
broken source (most likely the web search API) never breaks the rest:
clients, properties, documents, memories (reusing the browse service from
the Memories tab work), past conversations, the static compliance
reference data (disclosure requirements, AML overview), and the live web.

**Web search provider research, done before building, not assumed:**
Bing's Search API was retired in August 2025 — not an option regardless of
preference. **Brave Search API** is the default here: an independent
index (not a Google/Bing wrapper), cheap (~$0.005/query), no tracking,
widely adopted for exactly this kind of agent use case in 2026.
**Tavily** is wired in as a pluggable alternative
(`WEB_SEARCH_PROVIDER=tavily`) for when citation-grounded, pre-extracted
content matters more than raw cost — worth knowing Tavily was acquired by
Nebius in February 2026, a live platform-consolidation risk if you're
picking for the long term rather than just today. Same adapter pattern as
every other pluggable integration in this codebase
(`app/services/web_search_service.py`).

`frontend/app/search.html` — one search box, live results as you type
(debounced), categorized sections each linking straight to the right
detail page, a toggle to exclude web results entirely (useful if
`WEB_SEARCH_PROVIDER` isn't configured yet — the section just says so
honestly instead of silently showing nothing).

### Corrections made during this pass, not hidden
While adding the web search config, found and fixed a **stray duplicated
comment fragment** left over from an earlier edit in `config.py`
(`SLACK_SIGNING_SECRET`'s comment had an unrelated Hermes-related sentence
accidentally appended to it — harmless to runtime, but a real sign of
sloppy prior editing worth catching). Flagging this because it's exactly
the kind of small drift that's worth scanning for anytime you're editing a
file that's been through many rounds of `str_replace` calls.
