"""
Athena's real "god mode" for the regular (non-admin) chat — full read
access to everything in the platform (briefing, clients, properties,
calendar, alerts, trust, memories, documents, opportunities), and write
access to real actions, gated by the SAME server-enforced two-step
confirmation pattern as the admin agent (see admin_agent_service.py for
the full explanation of why a confirmation_token, not a prompt
instruction, is the actual guardrail).

This exists because the fixed-intent orchestrator (orchestrator_service.py)
can only answer questions it has an explicit if/elif branch for — ask it
anything not on that list ("tell me about my daily briefing") and it falls
through to a generic LLM reply with no real data access. This service is
the fix: genuine tool-calling, not a longer if/elif chain.
"""
import json
import secrets
import time

from sqlalchemy.orm import Session

from app.models.org import User
from app.services import conversation_service
from app.services.llm_service import llm_service

_PENDING_CONFIRMATIONS: dict[str, dict] = {}
_CONFIRMATION_TTL_SECONDS = 300
DESTRUCTIVE_ACTIONS = {"delete_property", "delete_client", "delete_calendar_event", "delete_reminder", "send_message_to_client"}

SYSTEM_PROMPT_TEMPLATE = """{persona}

You have real, direct access to this agent's entire platform through tools
— their daily briefing, clients, properties, calendar, alerts, trust
scores, memories, documents, and opportunities. When asked about any of
these, USE THE TOOL rather than saying you can't access it or guessing —
you genuinely can look it up.

For anything that changes or sends something real (deleting a record,
sending a message to a client), the tool will return a confirmation_token
instead of acting the first time — tell the agent plainly what you're
about to do, wait for them to explicitly agree, then call the same tool
again with that token. Never skip this for a destructive action."""


def _build_system_prompt(response_style: str = "verbose") -> str:
    from app.prompts.athena_persona import build_persona_for_style
    return SYSTEM_PROMPT_TEMPLATE.format(persona=build_persona_for_style(response_style))

TOOL_SCHEMAS = [
    {"type": "function", "function": {"name": "get_daily_briefing", "description": "Get the agent's full daily briefing — stats, AI insights, priorities, today's calendar, hot/stale leads.", "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {"name": "list_clients", "description": "List/search clients, optionally filtered by pipeline stage. Returns temperature, engagement score, and last-contacted date for each — use these to judge who needs attention, not just who exists.", "parameters": {"type": "object", "properties": {"search": {"type": "string"}, "pipeline_stage": {"type": "string"}}}}},
    {"type": "function", "function": {"name": "get_client_detail", "description": "Full detail on one client including recent timeline.", "parameters": {"type": "object", "properties": {"client_id": {"type": "string"}}, "required": ["client_id"]}}},
    {"type": "function", "function": {"name": "list_properties", "description": "List/search properties.", "parameters": {"type": "object", "properties": {"city": {"type": "string"}}}}},
    {"type": "function", "function": {"name": "get_calendar_events", "description": "Get calendar events in a date range.", "parameters": {"type": "object", "properties": {"days_ahead": {"type": "integer", "description": "How many days from today, default 7"}}}}},
    {"type": "function", "function": {"name": "get_alerts", "description": "Get pending/unread alerts.", "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {"name": "get_trust_status", "description": "Get the agent's own trust/autonomy levels and badges.", "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {"name": "search_memories", "description": "Search Athena's stored memories about clients/preferences.", "parameters": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}}},
    {"type": "function", "function": {"name": "get_opportunities", "description": "Get scored deal opportunities in a city.", "parameters": {"type": "object", "properties": {"city": {"type": "string"}}, "required": ["city"]}}},
    {"type": "function", "function": {"name": "create_client_task", "description": "Create a follow-up task for a client. Not destructive — no confirmation needed.", "parameters": {"type": "object", "properties": {"client_id": {"type": "string"}, "title": {"type": "string"}}, "required": ["client_id", "title"]}}},
    {"type": "function", "function": {"name": "delete_property", "description": "Permanently delete a property. DESTRUCTIVE — requires confirmation.", "parameters": {"type": "object", "properties": {"property_id": {"type": "string"}, "confirmation_token": {"type": "string"}}, "required": ["property_id"]}}},
    # ── Client CRUD ──
    {"type": "function", "function": {"name": "create_client", "description": "Create a new client record.", "parameters": {"type": "object", "properties": {"name": {"type": "string"}, "email": {"type": "string"}, "phone": {"type": "string"}, "client_type": {"type": "string"}, "pipeline_stage": {"type": "string"}, "budget_min": {"type": "number"}, "budget_max": {"type": "number"}}, "required": ["name"]}}},
    {"type": "function", "function": {"name": "update_client", "description": "Update fields on an existing client (name, email, phone, stage, budget, tags).", "parameters": {"type": "object", "properties": {"client_id": {"type": "string"}, "updates": {"type": "object"}}, "required": ["client_id", "updates"]}}},
    {"type": "function", "function": {"name": "delete_client", "description": "Permanently delete a client. DESTRUCTIVE — requires confirmation.", "parameters": {"type": "object", "properties": {"client_id": {"type": "string"}, "confirmation_token": {"type": "string"}}, "required": ["client_id"]}}},
    {"type": "function", "function": {"name": "add_client_note", "description": "Add a note to a client record.", "parameters": {"type": "object", "properties": {"client_id": {"type": "string"}, "body": {"type": "string"}}, "required": ["client_id", "body"]}}},
    {"type": "function", "function": {"name": "change_client_stage", "description": "Move a client to a new pipeline stage.", "parameters": {"type": "object", "properties": {"client_id": {"type": "string"}, "new_stage": {"type": "string"}}, "required": ["client_id", "new_stage"]}}},
    {"type": "function", "function": {"name": "add_client_tag", "description": "Add a tag to a client.", "parameters": {"type": "object", "properties": {"client_id": {"type": "string"}, "tag": {"type": "string"}}, "required": ["client_id", "tag"]}}},
    # ── Property CRUD ──
    {"type": "function", "function": {"name": "create_property", "description": "Create a property record manually.", "parameters": {"type": "object", "properties": {"address": {"type": "string"}, "city": {"type": "string"}, "state": {"type": "string"}, "price": {"type": "number"}, "beds": {"type": "integer"}, "baths": {"type": "number"}, "sqft": {"type": "number"}, "property_type": {"type": "string"}}, "required": ["address", "city", "state"]}}},
    {"type": "function", "function": {"name": "update_property", "description": "Update fields on a property (price, status, beds, baths, sqft).", "parameters": {"type": "object", "properties": {"property_id": {"type": "string"}, "updates": {"type": "object"}}, "required": ["property_id", "updates"]}}},
    # ── Calendar CRUD ──
    {"type": "function", "function": {"name": "create_calendar_event", "description": "Create a calendar event (showing, meeting, call, closing).", "parameters": {"type": "object", "properties": {"title": {"type": "string"}, "start_at": {"type": "string"}, "end_at": {"type": "string"}, "event_type": {"type": "string"}, "client_id": {"type": "string"}}, "required": ["title", "start_at", "end_at"]}}},
    {"type": "function", "function": {"name": "update_calendar_event", "description": "Update a calendar event.", "parameters": {"type": "object", "properties": {"event_id": {"type": "string"}, "updates": {"type": "object"}}, "required": ["event_id", "updates"]}}},
    {"type": "function", "function": {"name": "delete_calendar_event", "description": "Delete a calendar event. DESTRUCTIVE — requires confirmation.", "parameters": {"type": "object", "properties": {"event_id": {"type": "string"}, "confirmation_token": {"type": "string"}}, "required": ["event_id"]}}},
    {"type": "function", "function": {"name": "create_reminder", "description": "Create a quick reminder (note + date/time).", "parameters": {"type": "object", "properties": {"note": {"type": "string"}, "remind_at": {"type": "string"}, "client_id": {"type": "string"}}, "required": ["note", "remind_at"]}}},
    {"type": "function", "function": {"name": "complete_reminder", "description": "Mark a reminder as completed.", "parameters": {"type": "object", "properties": {"reminder_id": {"type": "string"}}, "required": ["reminder_id"]}}},
    {"type": "function", "function": {"name": "delete_reminder", "description": "Delete a reminder. DESTRUCTIVE — requires confirmation.", "parameters": {"type": "object", "properties": {"reminder_id": {"type": "string"}, "confirmation_token": {"type": "string"}}, "required": ["reminder_id"]}}},
    # ── Documents ──
    {"type": "function", "function": {"name": "list_documents", "description": "List documents in the workspace.", "parameters": {"type": "object", "properties": {"status": {"type": "string"}}}}},
    {"type": "function", "function": {"name": "generate_document", "description": "Generate a document (offer, listing, contract) via AI.", "parameters": {"type": "object", "properties": {"title": {"type": "string"}, "doc_type": {"type": "string"}, "instructions": {"type": "string"}}, "required": ["title", "doc_type"]}}},
    {"type": "function", "function": {"name": "score_document", "description": "Re-score/review a document for quality.", "parameters": {"type": "object", "properties": {"document_id": {"type": "string"}}, "required": ["document_id"]}}},
    # ── Alerts ──
    {"type": "function", "function": {"name": "mark_alert_read", "description": "Mark an alert as read.", "parameters": {"type": "object", "properties": {"event_id": {"type": "string"}}, "required": ["event_id"]}}},
    {"type": "function", "function": {"name": "create_alert_rule", "description": "Create an alert rule (e.g. notify when a new listing matches).", "parameters": {"type": "object", "properties": {"name": {"type": "string"}, "trigger_type": {"type": "string"}, "config": {"type": "object"}}, "required": ["name", "trigger_type"]}}},
    # ── Messages / conversations ──
    {"type": "function", "function": {"name": "send_message_to_client", "description": "Send a real message (email/SMS) to a client. DESTRUCTIVE — requires confirmation.", "parameters": {"type": "object", "properties": {"client_id": {"type": "string"}, "body": {"type": "string"}, "confirmation_token": {"type": "string"}}, "required": ["client_id", "body"]}}},
    {"type": "function", "function": {"name": "list_conversations", "description": "List conversation threads.", "parameters": {"type": "object", "properties": {}}}},
]


def _request_confirmation(action: str, params: dict, description: str) -> dict:
    token = secrets.token_urlsafe(16)
    _PENDING_CONFIRMATIONS[token] = {"action": action, "params": params, "expires_at": time.time() + _CONFIRMATION_TTL_SECONDS}
    return {"status": "confirmation_required", "confirmation_token": token, "message": description}


def _check_confirmation(token: str | None, action: str) -> bool:
    if not token:
        return False
    pending = _PENDING_CONFIRMATIONS.get(token)
    if not pending or pending["action"] != action or time.time() > pending["expires_at"]:
        return False
    del _PENDING_CONFIRMATIONS[token]
    return True


def _dispatch_tool(db: Session, user: User, name: str, args: dict) -> dict:
    org_id, user_id = str(user.org_id), str(user.id)

    if name == "get_daily_briefing":
        from app.services.daily_briefing_service import get_daily_briefing
        return get_daily_briefing(db, org_id, user_id, user.full_name)

    if name == "list_clients":
        from app.services import client_service
        clients = client_service.list_clients(db, org_id, search=args.get("search"), pipeline_stage=args.get("pipeline_stage"))
        return {"clients": [
            {
                "id": str(c.id), "name": c.name, "stage": c.pipeline_stage, "budget": c.budget_max,
                "deal_value": c.deal_value, "temperature": c.lead_temperature, "engagement_score": c.engagement_score,
                "last_contacted_at": c.last_contacted_at.isoformat() if c.last_contacted_at else "never",
            }
            for c in clients[:20]
        ]}

    if name == "get_client_detail":
        from app.services import client_service
        from app.services.client_timeline_service import get_client_timeline
        c = client_service.get_client(db, args["client_id"])
        if not c:
            return {"error": "Client not found"}
        timeline = get_client_timeline(db, args["client_id"], limit=10)
        return {"name": c.name, "stage": c.pipeline_stage, "budget": c.budget_max, "recent_activity": [t["summary"] for t in timeline]}

    if name == "list_properties":
        from app.models.property import Property
        query = db.query(Property).filter(Property.org_id == org_id)
        if args.get("city"):
            query = query.filter(Property.city == args["city"])
        props = query.limit(20).all()
        return {"properties": [{"id": str(p.id), "address": p.address, "price": p.price, "source": p.source} for p in props]}

    if name == "get_calendar_events":
        from datetime import datetime, timedelta
        from app.services import calendar_service
        days = args.get("days_ahead", 7)
        events = calendar_service.list_events(db, org_id, datetime.now(), datetime.now() + timedelta(days=days))
        return {"events": [{"title": e.title, "start_at": e.start_at.isoformat()} for e in events]}

    if name == "get_alerts":
        from app.models.alert import AlertEvent, AlertRule
        events = db.query(AlertEvent).join(AlertRule).filter(AlertRule.org_id == org_id, AlertEvent.is_read == False).limit(10).all()  # noqa: E712
        return {"alerts": [{"headline": a.headline, "detail": a.detail} for a in events]}

    if name == "get_trust_status":
        from app.services.trust_gamification_service import get_gamification_summary
        return get_gamification_summary(db, user_id)

    if name == "search_memories":
        from app.services import memory_browse_service
        memories = memory_browse_service.list_memories(org_id, search=args["query"])
        return {"memories": [{"text": m["text"], "category": m.get("category")} for m in memories[:10]]}

    if name == "get_opportunities":
        from app.services.opportunity_service import score_opportunities
        opps = score_opportunities(db, org_id, args["city"], min_score=50, limit=10)
        return {"opportunities": opps}

    if name == "create_client_task":
        from app.services import client_service
        task = client_service.create_task(db, args["client_id"], user_id, args["title"])
        return {"status": "done", "task_id": str(task.id)}

    if name == "create_client":
        from app.services import client_service
        fields = {k: v for k, v in args.items() if v is not None}
        name = fields.pop("name")
        client = client_service.create_client(db, org_id, user_id, name=name, **fields)
        return {"status": "done", "client_id": str(client.id), "name": client.name}

    if name == "update_client":
        from app.services import client_service
        updates = args.get("updates", {})
        if not isinstance(updates, dict) or not updates:
            return {"error": "No updates provided"}
        client = client_service.update_client(db, args["client_id"], updates)
        return {"status": "done", "client_id": str(client.id), "name": client.name}

    if name == "delete_client":
        params = {"client_id": args["client_id"]}
        if not _check_confirmation(args.get("confirmation_token"), "delete_client"):
            return _request_confirmation("delete_client", params, f"About to permanently delete client {args['client_id']} and all their data. Confirm to proceed.")
        from app.models.client import Client
        from app.models.message import Message
        from app.models.calendar_event import CalendarEvent
        from app.models.document import Document
        c = db.query(Client).filter(Client.id == args["client_id"], Client.org_id == org_id).first()
        if not c:
            return {"error": "Client not found"}
        db.query(Message).filter(Message.client_id == c.id).delete()
        db.query(CalendarEvent).filter(CalendarEvent.client_id == c.id).delete()
        db.query(Document).filter(Document.client_id == c.id).delete()
        db.delete(c)
        db.commit()
        return {"status": "done"}

    if name == "add_client_note":
        from app.services import client_service
        note = client_service.add_note(db, args["client_id"], user_id, args["body"])
        return {"status": "done", "note_id": str(note.id)}

    if name == "change_client_stage":
        from app.services import client_service
        client = client_service.change_pipeline_stage(db, args["client_id"], user_id, args["new_stage"])
        return {"status": "done", "stage": client.pipeline_stage}

    if name == "add_client_tag":
        from app.services import client_service
        client = client_service.add_tag(db, args["client_id"], user_id, args["tag"])
        return {"status": "done", "tags": client.tags or []}

    if name == "create_property":
        from app.models.property import Property
        fields = {k: v for k, v in args.items() if v is not None}
        prop = Property(org_id=org_id, **fields)
        db.add(prop)
        db.commit()
        db.refresh(prop)
        return {"status": "done", "property_id": str(prop.id), "address": prop.address}

    if name == "update_property":
        from app.models.property import Property
        updates = args.get("updates", {})
        if not isinstance(updates, dict) or not updates:
            return {"error": "No updates provided"}
        prop = db.query(Property).filter(Property.id == args["property_id"], Property.org_id == org_id).first()
        if not prop:
            return {"error": "Property not found"}
        for k, v in updates.items():
            setattr(prop, k, v)
        db.commit()
        db.refresh(prop)
        return {"status": "done", "property_id": str(prop.id)}

    if name == "create_calendar_event":
        from app.services import calendar_service
        event = calendar_service.create_event(db, org_id, user_id, **{k: v for k, v in args.items() if v is not None})
        return {"status": "done", "event_id": str(event.id), "title": event.title}

    if name == "update_calendar_event":
        from app.services import calendar_service
        event = calendar_service.update_event(db, args["event_id"], args.get("updates", {}))
        return {"status": "done", "event_id": str(event.id)}

    if name == "delete_calendar_event":
        params = {"event_id": args["event_id"]}
        if not _check_confirmation(args.get("confirmation_token"), "delete_calendar_event"):
            return _request_confirmation("delete_calendar_event", params, f"About to delete calendar event {args['event_id']}. Confirm to proceed.")
        from app.services import calendar_service
        calendar_service.delete_event(db, args["event_id"])
        return {"status": "done"}

    if name == "create_reminder":
        from app.services import calendar_service
        from datetime import datetime
        remind_at = datetime.fromisoformat(args["remind_at"].replace("Z", "+00:00")) if "Z" in args["remind_at"] or "+" in args["remind_at"] else datetime.fromisoformat(args["remind_at"])
        reminder = calendar_service.create_reminder(db, org_id, user_id, args["note"], remind_at, args.get("client_id"))
        return {"status": "done", "reminder_id": str(reminder.id)}

    if name == "complete_reminder":
        from app.services import calendar_service
        reminder = calendar_service.complete_reminder(db, args["reminder_id"])
        return {"status": "done", "reminder_id": str(reminder.id)}

    if name == "delete_reminder":
        params = {"reminder_id": args["reminder_id"]}
        if not _check_confirmation(args.get("confirmation_token"), "delete_reminder"):
            return _request_confirmation("delete_reminder", params, f"About to delete reminder {args['reminder_id']}. Confirm to proceed.")
        from app.services import calendar_service
        calendar_service.delete_reminder(db, args["reminder_id"])
        return {"status": "done"}

    if name == "list_documents":
        from app.models.document import Document
        query = db.query(Document).filter(Document.org_id == org_id)
        if args.get("status"):
            query = query.filter(Document.status == args["status"])
        docs = query.limit(20).all()
        return {"documents": [{"id": str(d.id), "title": d.title or "Untitled", "status": d.status, "doc_type": d.doc_type} for d in docs]}

    if name == "generate_document":
        from app.services import document_service
        doc = document_service.generate_document(db, org_id, user_id, args["title"], args["doc_type"], args.get("instructions"))
        return {"status": "done", "document_id": str(doc.id), "title": doc.title}

    if name == "score_document":
        from app.services import document_service
        doc = document_service.score_document(db, args["document_id"])
        return {"status": "done", "document_id": str(doc.id), "score": doc.score if hasattr(doc, "score") else None}

    if name == "mark_alert_read":
        from app.models.alert import AlertEvent
        ev = db.query(AlertEvent).filter(AlertEvent.id == args["event_id"]).first()
        if ev:
            ev.is_read = True
            db.commit()
            return {"status": "done"}
        return {"error": "Alert not found"}

    if name == "create_alert_rule":
        from app.models.alert import AlertRule
        rule = AlertRule(org_id=org_id, name=args["name"], trigger_type=args["trigger_type"], config=args.get("config") or {})
        db.add(rule)
        db.commit()
        db.refresh(rule)
        return {"status": "done", "rule_id": str(rule.id)}

    if name == "send_message_to_client":
        params = {"client_id": args["client_id"], "body": args["body"]}
        if not _check_confirmation(args.get("confirmation_token"), "send_message_to_client"):
            return _request_confirmation("send_message_to_client", params, "About to send this message to client {}: {!r}. Confirm to send.".format(args['client_id'], args['body'][:60]))
        from app.services import inbox_service
        from app.models.client import Client
        c = db.query(Client).filter(Client.id == args["client_id"], Client.org_id == org_id).first()
        if not c:
            return {"error": "Client not found"}
        msg = inbox_service.send_new_message(db, org_id, user_id, channel="email", to_address=c.email or "", body=args["body"], client_id=str(c.id))
        return {"status": "sent", "message_id": str(msg.id) if hasattr(msg, "id") else None}

    if name == "list_conversations":
        from app.services import conversation_service
        convs = conversation_service.list_conversations(db, user_id, context="chat")
        return {"conversations": [{"id": str(c.id), "context": c.context} for c in convs[:10]]}

    if name == "delete_property":
        params = {"property_id": args["property_id"]}
        if not _check_confirmation(args.get("confirmation_token"), "delete_property"):
            return _request_confirmation("delete_property", params, f"About to permanently delete property {args['property_id']}. Confirm to proceed.")
        from app.models.property import Property
        from app.models.price_history import PriceHistory
        from app.models.comparable import Comparable
        prop = db.query(Property).filter(Property.id == args["property_id"], Property.org_id == org_id).first()
        if not prop:
            return {"error": "Property not found"}
        db.query(PriceHistory).filter(PriceHistory.property_id == prop.id).delete()
        db.query(Comparable).filter((Comparable.subject_property_id == prop.id) | (Comparable.comp_property_id == prop.id)).delete()
        db.delete(prop)
        db.commit()
        return {"status": "done"}

    return {"error": f"Unknown tool: {name}"}


def run_athena_chat(db: Session, user: User, conversation_id: str, user_message: str) -> dict:
    conversation_service.add_message(db, conversation_id, "user", user_message)
    history = conversation_service.get_conversation_messages(db, conversation_id)

    full_messages = [{"role": "system", "content": _build_system_prompt(user.response_style)}]
    for m in history[-30:]:  # cap context window growth on very long-running conversations
        entry = {"role": m.role.value, "content": m.content}
        if m.tool_calls:
            entry["tool_calls"] = m.tool_calls
        if m.tool_call_id:
            entry["tool_call_id"] = m.tool_call_id
        full_messages.append(entry)

    for _ in range(5):
        response = llm_service.complete_with_tools(full_messages, TOOL_SCHEMAS)
        tool_calls = response.get("tool_calls")

        if not tool_calls:
            conversation_service.add_message(db, conversation_id, "assistant", response["content"])
            return {"reply": response["content"]}

        full_messages.append({"role": "assistant", "content": response.get("content"), "tool_calls": tool_calls})
        conversation_service.add_message(db, conversation_id, "assistant", response.get("content"), tool_calls=tool_calls)

        for call in tool_calls:
            args = json.loads(call["function"]["arguments"])
            result = _dispatch_tool(db, user, call["function"]["name"], args)
            tool_content = json.dumps(result, default=str)
            full_messages.append({"role": "tool", "tool_call_id": call["id"], "content": tool_content})
            conversation_service.add_message(db, conversation_id, "tool", tool_content, tool_call_id=call["id"])

    return {"reply": "I've made several tool calls but haven't reached a final answer yet — try rephrasing or breaking this into a smaller question."}
