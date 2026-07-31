from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.database import init_db
from app.api import (
    routes_auth,
    routes_properties,
    routes_analyze,
    routes_neighborhood,
    routes_inbox,
    routes_trust,
    routes_admin,
    routes_chat,
    routes_opportunities,
    routes_matching,
    routes_portfolio,
    routes_negotiation,
    routes_alerts,
    routes_voice,
    routes_voice_telephony,
    routes_compliance,
    routes_content,
    routes_documents,
    routes_crm,
    routes_agent,
    routes_clients,
    routes_calendar,
    routes_briefing,
    routes_memory,
    routes_integrations,
    routes_conversations,
    routes_search,
    routes_me,
    routes_docs,
    routes_settings,
    routes_deal_room,
    routes_optimize,
    routes_reminders,
)

app = FastAPI(
    title="RealtyAI",
    description="Athena: an AI operating partner for realtors.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(routes_auth.router)
app.include_router(routes_properties.router)
app.include_router(routes_analyze.router)
app.include_router(routes_neighborhood.router)
app.include_router(routes_inbox.router)
app.include_router(routes_trust.router)
app.include_router(routes_admin.router)
app.include_router(routes_chat.router)
app.include_router(routes_opportunities.router)
app.include_router(routes_matching.router)
app.include_router(routes_portfolio.router)
app.include_router(routes_negotiation.router)
app.include_router(routes_alerts.router)
app.include_router(routes_voice.router)
app.include_router(routes_voice_telephony.router)
app.include_router(routes_compliance.router)
app.include_router(routes_content.router)
app.include_router(routes_documents.router)
app.include_router(routes_crm.router)
app.include_router(routes_agent.router)
app.include_router(routes_clients.router)
app.include_router(routes_calendar.router)
app.include_router(routes_briefing.router)
app.include_router(routes_memory.router)
app.include_router(routes_integrations.router)
app.include_router(routes_conversations.router)
app.include_router(routes_search.router)
app.include_router(routes_me.router)
app.include_router(routes_docs.router)
app.include_router(routes_settings.router)
app.include_router(routes_deal_room.router)
app.include_router(routes_optimize.router)
app.include_router(routes_reminders.router)


@app.on_event("startup")
def on_startup():
    init_db()


@app.get("/health")
def health():
    return {"status": "ok", "environment": settings.ENVIRONMENT}
