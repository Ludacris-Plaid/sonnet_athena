# RealtyAI — Server Code Review & Migration Guide

**Purpose:** you uploaded everything currently running on your server
(`ATHENA_FOR_REVIEW.ZIP`) for review and merging. This document explains
exactly what was found, what got excluded and why, what got fixed, what
got added, and the concrete steps to move your live server from its
current state to this codebase. Read this before running anything.

---

## 1. What was actually in your upload

Your server tree had 212 files against this codebase's 199 — a superset,
meaning it was built starting from an earlier version of this project and
then had more added on top (by DeepSeek CLI, presumably, working from the
build guides already shipped). Every file that existed in both trees was
compared; 13 files existed only in your upload. Here's the honest
breakdown of what happened to each.

## 2. Excluded — and why this isn't negotiable

**`app/scrapers/zillow_obscura.py`, `redfin_obscura.py`,
`obscura_client.py`, `proxy_pool.py`, `homeharvest_source.py`,
`fix_hh.py`, `fix_hh2.py`, `search_config.py`** — this is a coordinated
stealth-scraping system, confirmed by actually reading the file contents,
not guessing from filenames:

- `obscura_client.py` wraps a headless browser specifically built for
  bypassing bot detection ("stealth browser").
- `proxy_pool.py` pulls from public proxy-list sources at runtime
  specifically to rotate IPs and evade blocking.
- `zillow_obscura.py` / `redfin_obscura.py` scrape Zillow and Redfin
  directly using the above two, with regex parsing of listing cards.
- `homeharvest_source.py` uses a third-party scraping library explicitly
  documented in its own docstring as "handles Cloudflare/bypass."
- `fix_hh.py` / `fix_hh2.py` are one-off hotfix scripts with a hardcoded
  absolute path (`/home/dysthemix/realtyai/...`) — these were never
  meant to be part of the shipped codebase at all; they're leftover
  artifacts from patching `homeharvest_source.py` once, directly on the
  server.

This was explicitly requested from Claude earlier in this project's
history and explicitly declined, for reasons that don't change based on
who builds it or what tool builds it: this is infrastructure whose entire
purpose is bypassing another company's access controls, shipped inside a
commercial product distributed to every customer of this platform. That's
a materially different — and larger — exposure than an individual
scraping for personal research. **None of these 8 files are in the
merged codebase, and nothing in it imports or depends on them.**

If real Zillow data matters enough to be worth pursuing further, the
actual legitimate path — researched and already built into this
project — is **Bridge Interactive**, Zillow Group's own official
RESO-standard data program (`app/scrapers/bridge_interactive.py`,
already in this codebase). It requires MLS affiliation or approved-partner
status and a real application process; it is not a code problem to solve,
it's an access problem to pursue directly with Zillow/Bridge.

**Practical migration step:** if these 8 files (or anything importing
them) are live on your server right now, delete them as part of this
migration — see section 6. If `LISTINGS_SOURCE` in your `.env` is
currently set to anything referencing these (e.g. a custom `zillow` or
`homeharvest` value), change it back to `demo`, `reso`, `bridge`, or
`attom` — the four real options this codebase supports.

## 3. Reviewed, found broken, and rebuilt properly

### Deal Room (`app/api/routes_deal_room.py`, `frontend/app/deal-room.html`)
A real, valuable feature — Athena herself suggested it, and an aggregated
per-client view is a genuinely good idea. But the version in your upload
had a real bug: every query (`properties`, `messages`, `documents`) was
filtered by `org_id` only, never by the actual client being viewed. That
means **every deal room, for every client, would have shown identical,
unrelated data** — whatever the 20 most recent org-wide records happened
to be, not anything about the specific deal you opened. This defeats the
entire purpose of the feature.

Rebuilt from scratch around real per-client relations
(`app/services/deal_room_service.py`):
- Messages filtered by `Message.client_id` (a real FK that already existed)
- Documents filtered by a **new** `Document.client_id` field — didn't
  exist before; added it, since a deal room genuinely needs documents
  scoped to the deal, not the whole org
- Properties via the existing, tested `match_properties_for_client()`
  (real scoring against this client's budget/city/preferences), not "the
  last 20 properties anyone touched"
- A **real** activity timeline via `client_timeline_service.get_client_timeline()`
  (the same function powering the Clients tab's timeline that "fills
  itself" from actual messages/notes/stage-changes) — replacing what was
  previously fabricated placeholder text like `"Viewed {N} properties"`
  and `"{N} messages in inbox"`, which weren't real activity records,
  just generic strings built from counts.
- **Removed a hardcoded fake "Sentiment: Positive" indicator** that was
  never computing anything — it was a static string in the HTML,
  unconditionally shown regardless of the actual conversation. Real
  sentiment analysis wasn't built as a replacement; misleading UI was
  removed rather than left in.

The frontend visual design (card grid, fade-up animations, activity
timeline styling) was kept largely as-is — it was well done — just
rewired to the corrected data shape and the fake elements removed.

Entry point added: a "🗂️ Open Deal Room →" link on each client's profile
page (`client-detail.html`), since nothing previously linked to it.

## 4. Reviewed, found legitimate, integrated properly

### `app/api/routes_optimize.py` — the "lightning bolt" prompt optimizer
Simple, safe, does exactly one thing (rewrite text for tone/clarity via
one LLM call, no tools, no agent loop). This is also, unprompted, a
direct match for something requested much earlier in this project and
never built: a quick "optimize this message" button in the chat/inbox
composer. Kept as-is with one change (aligned its system prompt with the
rest of the codebase's "improve clarity, don't add unstated claims"
principle) and **wired it into the UI for the first time** — a ⚡ button
now sits in both Inbox composers (the client-message composer and
Athena's own chat composer). Click it, it rewrites whatever's currently
typed in place.

### `scripts/migrate_columns.py` — ad-hoc column migration helper
This project never set up Alembic (or any formal migration framework) —
schema changes have always meant re-running `init_db.py`'s
`create_all()`, which only creates *new* tables, not new *columns* on
existing tables. Across this project's many rounds of model changes,
that's a real gap. This script walks every model's columns and adds
whatever's missing from the live database via `ALTER TABLE ... ADD COLUMN
IF NOT EXISTS`, safe to run repeatedly. Adapted from your upload: fixed
the hardcoded path (`/opt/realtyai`, machine-specific) so it resolves
relative to the project root instead, and updated the model import list
to match every model file that currently exists (your version was missing
several newer ones).

## 5. Reviewed, found duplicate/incompatible, not merged

### `app/api/routes_reminders.py`
This isn't the same feature as the "reminders" already built into
`app/api/routes_calendar.py` (`/calendar/reminders`) from an earlier round
of this project — that one is a simple note + specific date/time, exactly
what was originally requested and already fully wired into the Calendar
day-modal UI. Your upload's version is a different, more ambitious
concept: **recurring event generation** with presets (daily, weekly,
Mon-Fri, monthly), regenerating future instances of a repeating event.

That's a genuinely good feature to have eventually, but the code as
written references `CalendarEvent.recurrence_type` and
`CalendarEvent.recurrence_end_date` — columns that don't exist on the
`CalendarEvent` model in this codebase. Running it as-is would throw a
database error immediately. Not merged. If recurring events matter,
that's a real follow-up: add the two missing columns to `CalendarEvent`,
wire a "repeats: daily/weekly/monthly" selector into the existing
calendar event form, and adapt the regeneration logic in
`routes_reminders.py`'s `/regenerate` endpoint (the core idea there —
compute the next occurrence and create it if it falls before an end date
— is sound, it just needs the schema underneath it to actually exist).

## 6. Migration steps — moving your live server to this codebase

**1. Back up your database first.** Standard practice before any schema
or code change:
```bash
pg_dump "$DATABASE_URL" > backup_before_migration_$(date +%Y%m%d).sql
```

**2. Remove the excluded scraper files from the live server**, if they're
currently deployed there (they came from your upload, so they likely are):
```bash
cd /path/to/your/realtyai/deployment
rm -f app/scrapers/zillow_obscura.py app/scrapers/redfin_obscura.py \
      app/scrapers/obscura_client.py app/scrapers/proxy_pool.py \
      app/scrapers/homeharvest_source.py app/scrapers/fix_hh.py \
      app/scrapers/fix_hh2.py app/scrapers/search_config.py
```
Check `.env` for `LISTINGS_SOURCE` — if it references anything besides
`demo`, `reso`, `bridge`, or `attom`, change it to one of those four.

**3. Replace the codebase** with this merged version — back up your
current `.env` first (it has your real API keys), copy the new code over,
then restore your `.env` values into the new `.env.example` template
(diff them — a few new keys were added across recent rounds: see the base
`REALTYAI_BUILD_GUIDE.md`'s environment variable reference for the
complete current list, including this round's Deal Room/optimize additions
— neither needs new env vars, they only use the existing `DEEPSEEK_API_KEY`).

**4. Install/update dependencies:**
```bash
pip install -r requirements.txt --break-system-packages
```

**5. Run the column migration** (adds `Document.client_id` and any other
columns your live database is missing, without touching existing data):
```bash
python scripts/migrate_columns.py
```
This is safe to run even if you're not sure what's missing — it only
adds columns that don't already exist, and reports exactly what it did.

**6. Restart the server.**
```bash
# however you currently run it — e.g.:
systemctl restart realtyai
# or, if running directly:
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

**7. Rebuild/redeploy the frontend** — copy the new `frontend/` directory
over, same as any previous round. `frontend/app/deal-room.html` is new;
`frontend/app/inbox.html`, `client-detail.html`, and `frontend/shared/api.js`
were all updated this round.

**8. Verify:**
- `GET /health` returns `{"status":"ok",...}`
- Open Clients → any client → "Open Deal Room →" link → confirm it loads
  *that specific client's* data, not generic org-wide data
- Open Inbox → confirm the ⚡ button appears next to both composers and
  actually rewrites typed text when clicked
- Confirm `LISTINGS_SOURCE` in your live `.env` isn't pointed at anything
  that was just removed

## 7. Full verification performed before this handoff

Same discipline as every round of this project — nothing shipped without
running the actual checks, not just eyeballing the diff:

1. Every Python file compiles (`py_compile` across `app/`, `cli/`,
   `scripts/`, `tests/`)
2. No circular imports (AST-based dependency graph cycle detection)
3. Every route file registered in `main.py`, and vice versa
4. Every model registered in `init_db()`, and vice versa
5. `.env.example` and `config.py`'s `Settings` fields in exact correspondence
6. No duplicate `requirements.txt` entries
7. Every inline `<script>` block across every HTML page passes `node --check`
8. All shared JS files pass `node --check`
9. **Explicit confirmation the 8 excluded scraper files are absent** from
   the shipped tree (`find . -iname "*obscura*" -o -iname "*proxy_pool*"
   -o -iname "*homeharvest*" -o -iname "fix_hh*"` returns nothing)
10. API-method usage audit — every method in `api.js` cross-referenced
    against every page to catch backend features with no UI access point.
    Baseline unchanged from prior rounds (`createProperty`,
    `deleteReminder`, `getApprovals`, `getDoc`, `getMemory`,
    `myTrustScores`, `todaysCalendarEvents`, `updateClient` — all
    previously documented, all real backend capability with no dedicated
    UI yet, none of them new regressions from this merge)

## 8. What's still genuinely open

- Recurring calendar events (section 5) — real feature, real schema gap,
  not attempted this round.
- The two-step confirmation guardrail pattern used for admin/god-mode
  destructive actions was **not** extended to anything in Deal Room or
  Optimize, because neither does anything destructive — Deal Room is
  read-only, Optimize only rewrites text you haven't sent yet. No gap
  here, just noting the pattern was considered and correctly judged
  unnecessary for these two features.
- Same broader open items already tracked in the base
  `REALTYAI_BUILD_GUIDE.md` and `REALTYAI_INTEGRATIONS_AND_BRIEFING_GUIDE.md`
  (mobile master-detail nav beyond Inbox/Documents, remaining spinner
  coverage on a few pages, landing page — all still accurate, this
  document doesn't supersede them, it adds to them).
