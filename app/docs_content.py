"""
The single source of truth for user-facing documentation — served to the
Docs tab (GET /docs) AND used to ground Athena's answers when a user asks
a "how do I..." question in chat (see docs_service.py). One content
source, not duplicated between frontend and backend, so the docs and
Athena's answers about the docs can never drift apart from each other.

Each section: id, category, title, icon, summary (shown in nav/search
results), walkthrough (real step-by-step usage), troubleshooting (common
issues + fixes), keywords (extra search terms beyond the title/content).
"""

DOCS_SECTIONS = [
    {
        "id": "getting-started",
        "category": "Getting Started",
        "title": "Welcome to RealtyAI",
        "icon": "🦉",
        "summary": "What Athena is, and where to start.",
        "walkthrough": [
            "Athena is built around one idea: automate the busywork so you spend your time closing deals and with clients, not doing admin.",
            "Start each day on the Daily Briefing — it's the first thing in the sidebar on purpose. It shows your stats, AI-generated insights about what needs attention, today's calendar, and new messages, all in one glance.",
            "Add your clients on the Clients tab, or connect an existing CRM (Follow Up Boss / HubSpot) or import a CSV under CRM Integrations so you're not starting from zero.",
            "Talk to Athena however's natural — type in Chat with Athena, or use Talk to Athena for voice. She remembers what you tell her (see the Memories tab) and gets more capable to act on her own the more she demonstrates she gets things right (see Trust with Athena).",
        ],
        "troubleshooting": [
            "If the sidebar looks empty or pages won't load, check that frontend/shared/config.js has your real Supabase URL/key filled in — this is the single most common setup issue.",
            "If AI features (chat, briefings, content generation) return errors, your DEEPSEEK_API_KEY may be missing or out of quota.",
        ],
        "keywords": ["start", "welcome", "intro", "onboarding", "overview"],
    },
    {
        "id": "daily-briefing",
        "category": "Daily Workflow",
        "title": "Daily Briefing",
        "icon": "☀️",
        "summary": "Your morning at-a-glance dashboard — stats, AI insights, priorities, calendar, and messages.",
        "walkthrough": [
            "Open Daily Briefing first thing each day — it's always the top item in the sidebar.",
            "The four stat cards show clients (with new-this-week count), hot leads and pipeline value, pending tasks/approvals, and today's events.",
            "AI Insights are individual numbered cards, not a paragraph — each one is a specific judgment call, not just a recap of the numbers you can already see. If something's being let slip (a cold lead, an overdue follow-up), Athena will say so plainly here.",
            "Today's Priorities pulls from everything waiting on you across the whole platform — draft replies, compliance flags, failed syncs — in one list.",
            "Click Refresh any time to regenerate; click any client name to jump straight to their profile.",
        ],
        "troubleshooting": [
            "If AI Insights shows an error message instead of insights, that's the LLM call failing gracefully — check your DeepSeek API key/quota. Every other section on the page still works independently.",
            "History isn't built yet — each briefing is generated fresh from live data, nothing is stored day-to-day.",
        ],
        "keywords": ["morning", "briefing", "dashboard", "insights", "stats"],
    },
    {
        "id": "chat-with-athena",
        "category": "Athena",
        "title": "Chat with Athena",
        "icon": "💬",
        "summary": "Your main conversation with Athena — persistent, never resets unless you ask.",
        "walkthrough": [
            "Type anything — a question, a request to look something up, or 'find listings under $500k' — Athena classifies what you're asking and routes it to the right tool automatically.",
            "Your conversation is saved permanently. Closing the tab, logging out, coming back tomorrow — it's all still there, exactly where you left it.",
            "Use 'Go Deep' for something that genuinely needs sustained research across multiple sources — it hands off to a separate, more thorough research agent and can take a few minutes, so it gets its own loading state rather than looking stuck.",
            "To start fresh, use the 'New conversation' button — your old conversation isn't deleted, just set aside; find it again anytime in Settings > Conversation History.",
        ],
        "troubleshooting": [
            "If Athena gives a generic or unhelpful answer, try being more specific — she works from real data, not guesses, so vague questions get vague answers.",
            "'Go Deep' showing 'not connected' means the separate research agent (Hermes) isn't configured — this is optional infrastructure, not required for normal chat.",
        ],
        "keywords": ["chat", "conversation", "ask athena", "go deep", "hermes"],
    },
    {
        "id": "search",
        "category": "Daily Workflow",
        "title": "Search",
        "icon": "🔍",
        "summary": "One search box across clients, properties, documents, memories, conversations, compliance reference, and the web.",
        "walkthrough": [
            "Type at least 2 characters and results appear live, organized by category, as you type.",
            "Each result links straight to the right place — a client result opens their profile, a property result opens Properties, etc.",
            "Toggle 'Include web results' off if you only want to search inside your own data.",
        ],
        "troubleshooting": [
            "No web results, even with the toggle on, usually means web search isn't configured (WEB_SEARCH_PROVIDER + an API key in .env) — the page says so directly rather than showing nothing unexplained.",
        ],
        "keywords": ["search", "find", "lookup"],
    },
    {
        "id": "clients",
        "category": "CRM",
        "title": "Clients",
        "icon": "👥",
        "summary": "Your full CRM — pipeline stages, lead scoring, tasks, notes, and AI-assisted follow-up.",
        "walkthrough": [
            "Add a client with + New Client, or bring in existing ones via CRM Integrations (Follow Up Boss/HubSpot sync, or a CSV upload).",
            "Every client has a pipeline stage (lead → contacted → qualified → showing → offer → under contract → closed) — use the Pipeline view for a drag-and-drop Kanban board, or the list view for filtering/searching.",
            "Open any client to see their full profile: tags, saved searches, tasks, notes, and — this is the differentiator — a timeline that fills itself. Every email, text, and voice interaction already lands there automatically, no manual logging.",
            "Use 'Catch me up' before a call for an instant AI summary of the whole relationship, or 'What should I do next?' for a concrete, specific suggestion grounded in their actual history.",
            "An engagement score (0-100) reflects how recently/often you've been in touch, weighted with qualification signals like pre-approval and an active saved search.",
        ],
        "troubleshooting": [
            "If a client's timeline looks empty despite real emails/texts, confirm the message was actually linked to that client (client_id set) when it came in — not every inbound message is auto-linked yet.",
            "Duplicate contacts get flagged automatically at the top of the list — click the banner to review and merge with one click, keeping whichever record you choose as primary.",
        ],
        "keywords": ["crm", "contacts", "leads", "pipeline", "kanban", "clients"],
    },
    {
        "id": "calendar",
        "category": "Daily Workflow",
        "title": "Calendar",
        "icon": "📅",
        "summary": "A real month-view calendar, with two-way Google/Outlook sync.",
        "walkthrough": [
            "Click any day to see and add events for that day — showings, closings, calls, meetings.",
            "Connect Google or Outlook under Email, Calendar & Slack to pull your existing calendar in and push new events back out.",
            "Sync isn't automatic yet — use the 'Sync now' button after connecting. A scheduled background sync is a natural next upgrade.",
        ],
        "troubleshooting": [
            "If synced events aren't showing up, trigger a manual sync first — there's no background job running yet.",
            "Editing an existing synced event's time/title doesn't have a form yet in this version — delete and recreate, or edit directly at the source (Google/Outlook) and re-sync.",
        ],
        "keywords": ["calendar", "schedule", "events", "google calendar", "outlook"],
    },
    {
        "id": "voice",
        "category": "Athena",
        "title": "Talk to Athena",
        "icon": "🎙️",
        "summary": "A real voice conversation with Athena — and real phone calls if you connect Twilio.",
        "walkthrough": [
            "Tap the mic and just talk — Athena transcribes, thinks, and replies out loud.",
            "Everything you tell her here feeds the same memory system as everything else — mention a client preference in a voice chat, and it shows up in the Memories tab afterward.",
            "With Twilio configured, real clients can call your business number and have an actual spoken conversation with Athena representing you — a genuinely different, more professional tone than the one she uses with you directly.",
        ],
        "troubleshooting": [
            "Voice requires STT_PROVIDER/TTS_PROVIDER and a matching API key (OpenAI or ElevenLabs) configured — without it you'll get a clear 'not configured' message, not a silent failure.",
            "If a reply sounds generic or gets replaced with a deflection like 'let me have your agent follow up,' that's the fair housing compliance gate catching something — voice sends autonomously with no review step, so this is intentional, not a bug.",
        ],
        "keywords": ["voice", "talk", "phone", "twilio", "microphone"],
    },
    {
        "id": "inbox",
        "category": "Daily Workflow",
        "title": "Inbox",
        "icon": "📥",
        "summary": "One unified inbox for email, SMS, and more — with Athena drafting 4 tone options for every reply.",
        "walkthrough": [
            "Every inbound message, regardless of channel, lands here. Athena generates four draft replies automatically — professional, warm, brief, urgent — pick the one that fits.",
            "Edit any draft inline before sending. The more you send drafts unedited, the more trust Athena earns toward eventually sending routine replies on her own — see Trust with Athena.",
            "A flagged draft (a fair housing warning banner) means the compliance screener caught something — review carefully before sending; it won't block you, but it's telling you why for a reason.",
        ],
        "troubleshooting": [
            "No drafts appearing on an inbound message usually means the draft-generation call failed — check DeepSeek API status.",
            "To actually receive real emails/texts (not just simulated ones), connect Gmail/Outlook and Twilio under their respective integration pages.",
        ],
        "keywords": ["inbox", "email", "sms", "messages", "drafts"],
    },
    {
        "id": "alerts",
        "category": "Daily Workflow",
        "title": "Alerts",
        "icon": "🔔",
        "summary": "Price drops, stale leads, new listing matches, and compliance flags — everything Athena thinks you should know.",
        "walkthrough": [
            "Filter by All / Unread / Compliance. Click 'Mark read' to clear an item.",
            "Set up custom rules — price drop %, long days-on-market, new listing matches for a specific client — under Alert Rules on this page.",
            "Compliance alerts are always on, no setup needed — they fire automatically whenever an outbound message gets flagged.",
        ],
        "troubleshooting": [
            "Stale-lead alerts don't fire automatically on a schedule yet — trigger a check manually from the Clients page ('Check stale leads').",
        ],
        "keywords": ["alerts", "notifications", "price drop", "stale lead"],
    },
    {
        "id": "properties",
        "category": "Listings",
        "title": "Properties",
        "icon": "🏠",
        "summary": "Import listings from your choice of source, browse as cards, and get the full picture in one modal.",
        "walkthrough": [
            "Pick a data source before importing — MLS/RESO, Zillow via Bridge Interactive (the real, official Zillow data path — see the note on this page about why that matters), ATTOM Data, a CSV export, or demo data for testing.",
            "Click any property card to open the full detail modal: photo gallery, a CMA analysis with real comps, an embedded investment calculator pre-filled with the price, the listing agent's real contact info with a one-click AI-drafted outreach message, and edit/delete controls.",
            "A red badge on a card means the fast fair housing scan flagged something in the description — run the deeper AI review from the Details tab for a full second opinion before publishing anything externally.",
        ],
        "troubleshooting": [
            "If a source shows '(not configured)' in the dropdown, it needs an API key in .env — demo data and CSV import always work with zero setup.",
            "Thumbnails showing a generic 'No Photo' placeholder just means that source doesn't provide images (common with public-records-only sources like ATTOM).",
        ],
        "keywords": ["properties", "listings", "mls", "zillow", "bridge interactive", "attom", "import"],
    },
    {
        "id": "content-studio",
        "category": "Marketing",
        "title": "Content Studio",
        "icon": "✍️",
        "summary": "Generate marketing content for any listing — MLS copy, social posts, flyers — all screened automatically.",
        "walkthrough": [
            "Pick a property and one or more content types (MLS description, Instagram caption, Facebook post, 'Just Listed' email, open house flyer, price drop announcement, virtual tour script).",
            "Every generated piece is automatically fair-housing screened before you see it — a warning banner tells you exactly what to review if something's flagged.",
        ],
        "troubleshooting": [
            "Content grounded strictly in the property's actual data on file — if a field is missing (e.g. no description), the generated copy will reflect that gap rather than inventing details.",
        ],
        "keywords": ["marketing", "content", "social media", "flyer", "mls description"],
    },
    {
        "id": "documents",
        "category": "Marketing",
        "title": "Documents",
        "icon": "📄",
        "summary": "Upload or generate business documents — with a real fair housing compliance score and one-click rework.",
        "walkthrough": [
            "Upload a PDF/DOCX/TXT/MD, or generate one from scratch (marketing flyers, buyer/seller guides, disclosure drafts, checklists).",
            "Every document gets a full compliance score. Click 'Auto-rework' to have Athena rewrite specifically to resolve whatever was flagged, keeping everything else intact.",
        ],
        "troubleshooting": [
            "Purchase agreements and listing agreements are deliberately not offered as generate-from-scratch document types — those need real, jurisdiction-specific approved forms and a lawyer, not an AI draft. Use 'Deal Points Worksheets' instead for internal prep.",
            "Direct text editing in the textarea isn't saved yet — use Auto-rework to apply changes.",
        ],
        "keywords": ["documents", "disclosure", "contracts", "checklist", "rework"],
    },
    {
        "id": "opportunities",
        "category": "Listings",
        "title": "Opportunities",
        "icon": "🎯",
        "summary": "Every active listing in a city, scored 0-100 on price position, days-on-market pressure, and real price cuts.",
        "walkthrough": [
            "Search a city to see every active listing ranked by opportunity score — grounded in your own ingested data, nothing scraped or guessed.",
            "Click 'Negotiate' on any listing for a grounded strategy suggestion — an opening offer and a specific lever, based on comps and real price history.",
        ],
        "troubleshooting": [
            "An empty result usually just means you haven't pulled listings for that city yet — go to Properties and import first.",
        ],
        "keywords": ["opportunities", "deals", "undervalued", "negotiation"],
    },
    {
        "id": "investment-calculator",
        "category": "Analysis",
        "title": "Investment Calculator",
        "icon": "📈",
        "summary": "Real amortization math — cap rate, cash-on-cash, and a multi-year projection.",
        "walkthrough": [
            "Enter purchase price, financing assumptions, and expected rent — get year-by-year cash flow, equity growth, and return figures.",
            "This is deterministic math, not an LLM guess — the same calculator is also embedded directly in every property's detail modal, pre-filled with that property's price.",
        ],
        "troubleshooting": [
            "A negative cash-on-cash return is a real, correct result if the rent doesn't cover the mortgage + expenses at that price/down-payment combination — not a bug.",
        ],
        "keywords": ["investment", "calculator", "cap rate", "cash flow", "roi"],
    },
    {
        "id": "compliance",
        "category": "Compliance",
        "title": "Compliance",
        "icon": "⚖️",
        "summary": "Fair housing screening, disclosure reference, and AML overview for US and Canada.",
        "walkthrough": [
            "Paste any text into the Fair Housing Screen to check it before you publish or send it.",
            "Browse general disclosure reference notes by jurisdiction, and an AML overview for the US/Canada.",
        ],
        "troubleshooting": [
            "This is a first-pass assistance tool, not legal advice — every result says so directly. Real estate law is jurisdiction-specific and changes; always confirm anything important with your brokerage's compliance officer or a lawyer.",
        ],
        "keywords": ["compliance", "fair housing", "disclosure", "aml", "legal"],
    },
    {
        "id": "memories",
        "category": "Athena",
        "title": "Memories",
        "icon": "🧠",
        "summary": "Every fact, preference, and insight Athena has stored — as searchable, color-coded cards.",
        "walkthrough": [
            "Every memory is a card — gold for preferences, olive for facts, purple for Athena's own derived insights (like a saved 'next action' suggestion).",
            "Filter by category or search the text, click any card for the full detail in a modal, including exactly when it was learned and what client it's linked to.",
            "'Forget this' removes a memory Athena will no longer draw on in future conversations.",
        ],
        "troubleshooting": [
            "New memories show up automatically as you use voice, chat, and the AI client features — there's no manual 'add a memory' button by design; it's meant to capture what actually happened, not what you think should be remembered.",
        ],
        "keywords": ["memories", "memory", "facts", "preferences", "insights"],
    },
    {
        "id": "crm-integrations",
        "category": "Integrations",
        "title": "CRM Integrations",
        "icon": "🔗",
        "summary": "Sync with your existing CRM — Follow Up Boss, HubSpot, or a CSV export — instead of starting over.",
        "walkthrough": [
            "Connect Follow Up Boss (API key) or HubSpot (Private App token) for real, working sync — pull their contacts in, or push RealtyAI clients out, or both ways.",
            "No API access? Export a CSV from whatever you're using and import it directly — a one-time import, always available with zero setup.",
        ],
        "troubleshooting": [
            "Most brokerage-bundled CRMs (kvCORE/BoldTrail, BoomTown) don't expose a public API at all — CSV export is the realistic path for those.",
            "HubSpot sync is pull-based only (no live webhooks) — a real platform limitation of Private App tokens, not a bug here.",
        ],
        "keywords": ["crm", "follow up boss", "hubspot", "sync", "csv import"],
    },
    {
        "id": "integrations",
        "category": "Integrations",
        "title": "Email, Calendar & Slack",
        "icon": "🔌",
        "summary": "Connect Gmail, Outlook, and Slack.",
        "walkthrough": [
            "Click Connect on Google or Microsoft — you'll go through their real login/consent screen, not a copy-paste API key.",
            "For Slack, create an app at api.slack.com/apps and paste the Bot Token here — lets you message Athena from a channel and get alerts posted there.",
        ],
        "troubleshooting": [
            "Sync is trigger-based ('Sync now'), not automatic yet on a schedule.",
        ],
        "keywords": ["gmail", "outlook", "slack", "email integration", "oauth"],
    },
    {
        "id": "trust",
        "category": "Athena",
        "title": "Trust with Athena",
        "icon": "🤝",
        "summary": "See exactly how much autonomy Athena has earned — an animated gauge, levels, and badges.",
        "walkthrough": [
            "The gauge shows your overall trust score. Five levels (New Partnership through Full Autonomy) map directly to real capability — hitting Limited Trust or Full Autonomy actually changes what Athena's allowed to do on her own, it's not just cosmetic.",
            "Hints tell you exactly how many more unedited sends would reach the next level — editing drafts less (when they're already right) is the fastest way to build trust.",
            "Badges are earned from real activity — quick-draw for 10 unedited sends, a 30-day compliance-clean streak, reaching full autonomy on every channel, and a 'Comeback' badge specifically for recovering from a rejected draft.",
        ],
        "troubleshooting": [
            "Trust only goes up from sending drafts unedited, and drops sharply on a rejection — there's no way to game it other than actually being reliable, by design.",
        ],
        "keywords": ["trust", "autonomy", "badges", "levels", "gamification"],
    },
    {
        "id": "settings",
        "category": "Account",
        "title": "Settings",
        "icon": "⚙️",
        "summary": "Profile, conversation history, and connected services.",
        "walkthrough": [
            "Conversation History is fully searchable — search by title or anything said inside a conversation, click any past one to resume it exactly where you left off.",
            "'Start New Conversation' is the only thing that resets a conversation, and it's explicit and confirmed — your old thread is never deleted, just set aside.",
        ],
        "troubleshooting": [],
        "keywords": ["settings", "profile", "conversation history", "logout"],
    },
]


def get_all_sections() -> list[dict]:
    return DOCS_SECTIONS


def get_section(section_id: str) -> dict | None:
    return next((s for s in DOCS_SECTIONS if s["id"] == section_id), None)


def search_sections(query: str) -> list[dict]:
    q = query.lower()
    results = []
    for s in DOCS_SECTIONS:
        haystack = " ".join([
            s["title"], s["summary"], s["category"],
            " ".join(s["walkthrough"]), " ".join(s["troubleshooting"]), " ".join(s["keywords"]),
        ]).lower()
        if q in haystack:
            results.append(s)
    return results
